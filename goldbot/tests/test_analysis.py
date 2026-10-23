import copy

import pandas as pd

from analysis import checks, direction, ema_stack, market_facts, strength
from oanda import demo_candles, demo_daily, demo_macro
from pipeline import prepare

M15 = demo_candles(6000)
D1 = demo_daily(M15)
FACTS = market_facts(prepare(M15, D1, *demo_macro(D1)), D1)


def test_ema_stack_order():
    up = pd.Series(range(300), dtype=float)
    assert ema_stack(up)["order"] == "wzrostowe" and ema_stack(up[::-1].reset_index(drop=True))["order"] == "spadkowe"
    assert ema_stack(up[:50])["order"] is None


def test_facts_cover_required_indicators():
    for k in ("ema20", "ema50", "ema200", "rsi", "macd_hist", "atr", "vwap", "volume_ratio", "structure"):
        assert k in FACTS["m15"], k
    assert {"ema20", "ema50", "ema200", "structure"} <= set(FACTS["d1"])
    assert FACTS["m15"]["vwap"] is not None and FACTS["change_24h"] is not None


def test_checks_list_names_and_strength():
    rows = checks(FACTS, 1)
    names = [r["name"] for r in rows]
    for n in ("Reżim dzienny", "EMA 20/50/200 D1", "EMA 20/50/200 M15", "RSI 14 (M15)", "Histogram MACD (M15)",
              "Wolumen tickowy (M15)", "Cena vs VWAP sesji UTC", "Wybicie i retest (M15)", "Dolar (szeroki indeks)"):
        assert n in names, n
    s = strength(rows)
    assert 0 <= s["confirm"] <= s["known"] <= len(rows) and "z" in s["text"]
    assert "Dolar (szeroki indeks)" not in [r["name"] for r in checks(FACTS, 1, macro=False)]


def test_no_direction_gives_no_verdicts():
    assert all(r["ok"] is None for r in checks(FACTS, 0))


def test_long_and_short_are_mirrored_for_directional_checks():
    long_ = {r["name"]: r["ok"] for r in checks(FACTS, 1)}
    short = {r["name"]: r["ok"] for r in checks(FACTS, -1)}
    for n in ("Histogram MACD (M15)", "Cena M15 vs EMA 200"):
        assert long_[n] is not None and long_[n] != short[n]


def test_resistance_before_tp_is_a_contradiction():
    f = copy.deepcopy(FACTS)
    f["m15"]["structure"]["resistance"] = f["price"] + 1
    row = [r for r in checks(f, 1, tp=f["price"] + 5) if r["name"] == "Przestrzeń do TP"][0]
    assert row["ok"] is False and "przed TP" in row["value"]


def test_direction():
    base = {"signal_raw": 0, "regime": "NEUTRALNY", "components": {"trend": None}}
    assert direction({**base, "signal_raw": -1}) == -1
    assert direction({**base, "regime": "SPRZYJA_KUPNIE"}) == 1
    assert direction({**base, "components": {"trend": -1.0}}) == -1
    assert direction(base) == 0
