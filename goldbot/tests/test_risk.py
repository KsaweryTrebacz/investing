import json

import pandas as pd

from config import Account, Config, Costs, Instrument
from risk import fx_rate, load_positions, plan_trade, portfolio_check, position_risk

NOW = pd.Timestamp("2026-01-05 10:00", tz="UTC")  # poniedziałek, przed rolloverem
HOLD = {"hours": 1.0, "n": 0, "max_hours": 48, "basis": "test"}
FX = {"rate": 4.0, "source": "test", "as_of": None}


def instr(**costs):
    base = dict(commission_per_unit=0.0, slippage_atr=0.15, margin_rate=0.05)
    return Instrument(group="metale", costs=Costs(**{**base, **costs}))


BUY = {"verdict": "KUP", "entry": 2000.0, "sl": 1990.0, "tp": 2020.0, "atr": 10 / 1.5}
SELL = {"verdict": "SPRZEDAJ", "entry": 2000.0, "sl": 2010.0, "tp": 1980.0, "atr": 10 / 1.5}
ACC = Account(currency="PLN", capital=10_000)


def test_plan_long_in_account_currency():
    p = plan_trade(BUY, instr(), ACC, FX, HOLD, NOW)
    assert abs(p["loss_per_unit"] - 11.0) < 1e-9       # 10 do SL + poślizg 1
    assert p["budget"] == 50.0 and p["units"] == 1      # 50 PLN / (11 USD * 4)
    assert abs(p["loss"] - 44.0) < 1e-9 and abs(p["gain"] - 80.0) < 1e-9
    assert abs(p["notional"] - 8000.0) < 1e-9 and abs(p["margin"] - 400.0) < 1e-9
    assert p["exact"] and p["missing"] == [] and "nie gwarantuje" in p["note"]


def test_plan_short_is_symmetric():
    p = plan_trade(SELL, instr(), ACC, FX, HOLD, NOW)
    assert p["side"] == "SHORT" and p["units"] == 1 and abs(p["loss"] - 44.0) < 1e-9


def test_loss_never_exceeds_budget():
    p = plan_trade(BUY, instr(units_step=0.01), Account(currency="PLN", capital=123_456), FX, HOLD, NOW)
    assert p["loss"] <= p["budget"] + 1e-9 and p["budget"] - p["loss"] < 0.01 * 11 * 4


def test_too_small_account_gives_zero_units():
    assert plan_trade(BUY, instr(), Account(currency="PLN", capital=100), FX, HOLD, NOW)["units"] == 0


def test_missing_data_is_reported_and_blocks_sizing():
    p = plan_trade(BUY, Instrument(), Account(currency="PLN"), None, HOLD, NOW)
    assert p["units"] is None and not p["exact"]
    for m in ("prowizja", "poślizg na SL", "depozyt (stopa depozytu)", "kurs USD/PLN", "kapitał rachunku"):
        assert m in p["missing"]


def test_dividend_adjustment():
    i = instr(dividend_share=0.85)
    long_ = plan_trade(BUY, i, ACC, FX, HOLD, NOW, dividend={"amount": 1.0})
    short = plan_trade(SELL, i, ACC, FX, HOLD, NOW, dividend={"amount": 1.0})
    assert abs(long_["gain_per_unit"] - 20.85) < 1e-9 and abs(short["loss_per_unit"] - 11.85) < 1e-9
    assert "korekta dywidendowa" in plan_trade(BUY, i, ACC, FX, HOLD, NOW, dividend={"amount": None})["missing"]


def cfg(currency="USD", capital=10_000, **fx):
    c = Config(account=Account(currency=currency, capital=capital), fx_rates=fx)
    c.instruments = {"XAU_USD": Instrument(group="metale"), "SPX500_USD": Instrument(name="SPX500_USD", group="indeksy")}
    return c


def test_fx_rate_sources():
    c = cfg("PLN", USDPLN={"rate": 4.0, "source": "NBP"})
    assert fx_rate(c, "USD")["rate"] == 4.0 and fx_rate(c, "PLN")["rate"] == 1.0
    assert fx_rate(c, "USD", {"USDPLN": {"rate": 3.9, "source": "OANDA"}})["source"] == "OANDA"
    assert abs(fx_rate(cfg("PLN", PLNUSD={"rate": 0.25}), "USD")["rate"] - 4.0) < 1e-12
    assert fx_rate(c, "EUR") is None and fx_rate(cfg(None), "USD") is None


POS = {"as_of": "2026-01-05T09:00:00Z", "positions": [
    {"instrument": "XAU_USD", "side": "LONG", "units": 2, "entry": 2000, "sl": 1980},
    {"instrument": "SPX500_USD", "side": "LONG", "units": 1, "entry": 5000, "sl": 4950}]}


def test_position_risk():
    c = cfg()
    assert position_risk(POS["positions"][0], c) == 40.0
    assert position_risk({"instrument": "XAU_USD", "side": "SHORT", "units": 1, "entry": 2000, "sl": 2010}, c) == 10.0
    assert position_risk({"instrument": "XAU_USD", "side": "LONG", "units": 1, "entry": 2000, "sl": 2010}, c) == 0.0
    assert position_risk({"instrument": "XAU_USD", "side": "LONG", "units": 1, "entry": 2000}, c) is None


def test_portfolio_within_limits():
    r = portfolio_check(50.0, "XAU_USD", cfg(), POS)
    assert r["ok"] and r["total"] == 90.0 and r["group_total"] == 40.0 and r["count"] == 2


def test_portfolio_group_limit():
    r = portfolio_check(70.0, "XAU_USD", cfg(), POS)  # 40 + 70 > 1% z 10 000
    assert r["exceeded"] and not r["ok"] and "metale" in r["reasons"][0]


def test_portfolio_total_limit():
    r = portfolio_check(150.0, "SPX500_USD", cfg(capital=20_000), POS)  # 240 <= 400, grupa 200 <= 200
    assert r["ok"]
    r = portfolio_check(120.0, "SPX500_USD", cfg(), POS)  # 210 > 200
    assert r["exceeded"] and any("Łączne ryzyko" in x for x in r["reasons"])


def test_portfolio_unknown_and_missing():
    pos = {"positions": [{"instrument": "XAU_USD", "side": "LONG", "units": 1, "entry": 2000}]}
    r = portfolio_check(10.0, "XAU_USD", cfg(), pos)
    assert r["unknown"] and not r["ok"] and not r["exceeded"]
    r = portfolio_check(10.0, "XAU_USD", cfg(), None)
    assert not r["available"] and r["ok"] is None and "Brak pliku" in r["reasons"][0]


def test_load_positions(tmp_path):
    p = tmp_path / "positions.json"
    p.write_text(json.dumps({"as_of": "x"}), encoding="utf-8")
    assert load_positions(str(p)) == {"as_of": "x", "positions": []}
    assert load_positions(str(tmp_path / "brak.json")) is None


def test_liquidation_price_long_short_and_other_margin():
    from risk import liquidation_price
    # 1 jedn. po 100, kapitał 2 (dźwignia 50:1), depozyt 2%, likwidacja przy 50% depozytu
    p = liquidation_price(1, 100.0, 1.0, 2.0, 0.02, 0.5)
    assert abs((2.0 + (p - 100.0)) - 0.5 * 0.02 * p) < 1e-9 and 98.9 < p < 99.0
    p = liquidation_price(-1, 100.0, 1.0, 2.0, 0.02, 0.5)
    assert abs((2.0 - (p - 100.0)) - 0.5 * 0.02 * p) < 1e-9 and 100.9 < p < 101.0
    assert liquidation_price(1, 100.0, 1.0, 2.0, 0.02, 0.5, other_margin=1.0) > p - 2  # inne pozycje przybliżają likwidację


def test_plan_reports_leverage_and_liquidation_at_1_to_50():
    i = instr(margin_rate=0.02)
    p = plan_trade(BUY, i, ACC, FX, HOLD, NOW)
    assert abs(p["leverage"] - 0.8) < 1e-9 and p["max_leverage"] == 50 and abs(p["margin"] - 160.0) < 1e-9
    assert p["liquidation_move"] < -0.5 and not p["sl_beyond_liquidation"]  # przy ryzyku 0,5% likwidacja jest daleko
    big = plan_trade(BUY, i, Account(currency="PLN", capital=10_000, risk_per_trade=0.9), FX, HOLD, NOW)
    assert big["leverage"] > 50 and big["free_margin"] < 0       # 90% ryzyka: pozycja większa niż pozwala depozyt


def test_sl_beyond_liquidation_is_detected():
    far = {"verdict": "KUP", "entry": 2000.0, "sl": 1900.0, "tp": 2200.0, "atr": 100 / 1.5}
    p = plan_trade(far, instr(margin_rate=0.02), Account(currency="USD", capital=10_000, risk_per_trade=0.95),
                   {"rate": 1.0, "source": "t", "as_of": None}, HOLD, NOW)
    assert p["leverage"] < 50 and p["sl_beyond_liquidation"] and p["liquidation_price"] > 1900.0


def test_positions_margin():
    from risk import positions_margin
    c = cfg()
    c.instruments["XAU_USD"].costs = Costs(margin_rate=0.02)
    total, unknown = positions_margin(c, POS)
    assert abs(total - 2 * 2000 * 0.02) < 1e-9 and unknown == ["SPX500_USD"]
