import numpy as np
import pandas as pd
import pytest

import momentum as M
from config import Account, Config, Costs, Instrument
from cycle import Context, run_cycle
from oanda import demo_candles, demo_daily, demo_macro
from report import render_text
from store import Store


def d1_frame(closes, start="2025-01-05 22:00"):
    t = pd.date_range(start, periods=len(closes), freq="D", tz="UTC")
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"time": t, **{f"{s}_{k}": c + (0.1 if s == "ask" else -0.1) for s in ("bid", "ask") for k in "ohlc"}})


def wiggly(n, drift):
    return 1000 * np.exp(np.cumsum(drift + 0.01 * np.tile([1.0, -1.0], n // 2 + 1)[:n]))


def test_signal_long_in_uptrend_with_vol_target_leverage():
    s = M.signal(d1_frame(wiggly(200, 0.002)), M.TrendParams(), 0.02)
    assert s["side"] == 1 and s["momentum"] > 0 and s["cap"] == 50
    assert abs(s["leverage"] - min(0.5 / s["vol"], 50)) < 0.2       # zmienność z 20 dni, ten sam wzór co w badaniu
    down = M.signal(d1_frame(wiggly(200, -0.002)), M.TrendParams(), 0.02)
    assert down["side"] == 0 and down["leverage"] == 0.0
    assert M.signal(d1_frame(wiggly(200, -0.002)), M.TrendParams(long_only=False), 0.02)["side"] == -1
    capped = M.signal(d1_frame(wiggly(200, 0.002)), M.TrendParams(max_leverage=2.0), 0.02)
    assert capped["leverage"] == 2.0 and capped["cap"] == 2.0
    with pytest.raises(ValueError, match="Za mało"):
        M.signal(d1_frame(wiggly(100, 0.002)), M.TrendParams(), 0.02)


@pytest.mark.parametrize("side, current, action, verdict", [
    (1, None, "OTWÓRZ LONG", "KUP"), (0, None, "BEZ POZYCJI", "CZEKAJ"), (1, 0.0, "OTWÓRZ LONG", "KUP"),
    (0, 0.0, "BEZ POZYCJI", "CZEKAJ"), (0, 10.0, "ZAMKNIJ", "SPRZEDAJ"), (1, 10.0, "UTRZYMAJ", "CZEKAJ"),
    (1, 5.0, "ZWIĘKSZ", "KUP"), (1, 20.0, "ZMNIEJSZ", "SPRZEDAJ"), (1, -5.0, "ODWRÓĆ", "KUP")])
def test_advise_actions(side, current, action, verdict):
    a = M.advise(side, 4.0, 10_000.0, 1000.0, 4.0, 1.0, current, 0.1)   # cel: 4 x 10 000 / (1000 x 4) = 10 jedn.
    assert (a["action"], a["verdict"]) == (action, verdict)
    if side:
        assert a["target_units"] == 10.0


def test_current_units_from_positions_file():
    pos = {"positions": [{"instrument": "XAU_USD", "side": "LONG", "units": 3}, {"instrument": "XAU_USD", "side": "SHORT", "units": 1},
                         {"instrument": "SPX500_USD", "side": "LONG", "units": 9}]}
    assert M.current_units(pos, "XAU_USD") == 2.0 and M.current_units(None, "XAU_USD") is None


def test_validate_reports_halves_and_buy_and_hold():
    r = M.validate(d1_frame(wiggly(400, 0.001)), M.TrendParams(), 0.02, 0.5, -0.05, -0.01)
    assert {"calosc", "pierwsza_polowa", "druga_polowa", "kup_i_trzymaj_1x"} <= set(r)
    assert r["calosc"]["kapital_x"] > 0 and r["dni_w_pozycji_%"] > 50


# --- cykl w trybie trend_d1 na danych demo ---

FULL = demo_candles(40000)
D1_ALL = demo_daily(FULL)
LONG_AT = int(np.flatnonzero(M.positions(M.daily_frame(D1_ALL), 120) == 1)[-1])


def inputs(i=LONG_AT):
    cut = D1_ALL["time"].iloc[i] + pd.Timedelta(days=1)
    m15 = FULL[FULL["time"] < cut].reset_index(drop=True)
    d1 = D1_ALL.iloc[: i + 1].reset_index(drop=True)
    return m15, d1, m15["time"].iloc[-1] + pd.Timedelta(minutes=16)


def cfg(**costs):
    c = Config(account=Account(currency="PLN", capital=20_000), fx_rates={"USDPLN": {"rate": 3.65, "source": "test"}})
    c.instruments = {"XAU_USD": Instrument(mode="trend_d1", costs=Costs(**{"margin_rate": 0.02, "financing_long_rate": -0.065,
                                                                          **costs}))}
    return c


def run(positions={"positions": []}, config=None, now_shift=pd.Timedelta(0)):
    m15, d1, now = inputs()
    return run_cycle(m15, d1, *demo_macro(d1), Store(), now=now + now_shift,
                     ctx=Context(cfg=config or cfg(), positions=positions))["verdict"]


def test_trend_cycle_opens_long_with_sizing_and_liquidation():
    v = run()
    r = v["report"]
    assert v["decision"] == "MOZLIWA_TRANSAKCJA" and v["verdict"] == "KUP" and v["action"] == "OTWÓRZ LONG"
    p = r["pnl"]
    assert p["leverage"] <= 0.5 / r["trend"]["vol"] + 1e-9 and p["margin"] == pytest.approx(p["notional"] * 0.02)
    assert p["liquidation_price"] < r["plan"]["price"] and p["free_margin"] > 0
    text = render_text(r)
    for i in range(1, 9):
        assert f"\n{i}. " in text, i
    assert "Bez SL i TP" in text and "likwidacja przez brokera" in text and "docs/research" in text


def test_trend_cycle_states():
    assert run(positions=None)["decision"] == "OBSERWACJA"                       # nie wiadomo, ile już jest
    target = run()["report"]["plan"]["target_units"]
    held = {"positions": [{"instrument": "XAU_USD", "side": "LONG", "units": target, "entry": 1800.0}]}
    v = run(positions=held)
    assert v["action"] == "UTRZYMAJ" and v["decision"] == "OBSERWACJA" and v["verdict"] == "CZEKAJ"
    assert run(now_shift=pd.Timedelta(days=6))["decision"] == "BRAK_TRANSAKCJI"  # nieaktualne D1
    no_cap = cfg()
    no_cap.account.capital = None
    assert run(config=no_cap)["decision"] == "OBSERWACJA"


def test_trend_cycle_blocks_without_free_margin():
    c = cfg()
    c.instruments["SPX500_USD"] = Instrument(name="SPX500_USD", costs=Costs(margin_rate=0.05))
    others = {"positions": [{"instrument": "SPX500_USD", "side": "LONG", "units": 80, "entry": 5000.0}]}  # depozyt 73 000 PLN
    v = run(positions=others, config=c)
    assert v["decision"] == "BRAK_TRANSAKCJI" and "wolnego depozytu" in v["decision_reasons"][0]
