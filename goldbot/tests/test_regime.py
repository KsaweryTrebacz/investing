import numpy as np
import pandas as pd

from regime import (REGIME_BUY, REGIME_NEUTRAL, REGIME_SELL, apply_hysteresis,
                    attach_regime, build_regime, trend_dir)


def test_trend_dir_up_down_flat():
    up = pd.Series(np.arange(300, dtype=float))
    assert trend_dir(up, 50, 200).iloc[-1] == 1
    assert trend_dir(up[::-1].reset_index(drop=True), 50, 200).iloc[-1] == -1
    assert trend_dir(pd.Series([5.0] * 300), 50, 200).iloc[-1] == 0
    assert trend_dir(up, 50, 200).iloc[:200].isna().all()


def test_hysteresis_needs_two_consecutive_days():
    raw = pd.Series([REGIME_NEUTRAL, REGIME_BUY, REGIME_NEUTRAL, REGIME_BUY, REGIME_BUY, REGIME_BUY])
    out = apply_hysteresis(raw, confirm=2).tolist()
    assert out == [REGIME_NEUTRAL] * 4 + [REGIME_BUY] * 2


def _d1(n=400, start=1800.0, end=2200.0):
    px = np.linspace(start, end, n)
    return pd.DataFrame({"time": pd.date_range("2025-01-01", periods=n, tz="UTC"),
                         "bid_c": px, "ask_c": px})


def test_all_three_components_bullish_gives_buy():
    d1 = _d1()
    idx = pd.date_range("2025-01-01", periods=500)
    usd = pd.Series(np.linspace(120, 100, 500), index=idx)
    yld = pd.Series(np.linspace(2.5, 1.0, 500), index=idx)
    reg = build_regime(d1, usd, yld)
    assert reg.regime.iloc[-1] == REGIME_BUY
    assert reg.total.iloc[-1] == 3
    assert (reg.known_from == reg.time + pd.Timedelta(days=1)).all()


def test_falling_gold_and_bearish_macro_gives_sell():
    d1 = _d1(start=2200.0, end=1800.0)
    idx = pd.date_range("2025-01-01", periods=500)
    usd = pd.Series(np.linspace(100, 120, 500), index=idx)
    yld = pd.Series(np.linspace(1.0, 2.5, 500), index=idx)
    assert build_regime(d1, usd, yld).regime.iloc[-1] == REGIME_SELL


def test_missing_macro_is_always_neutral():
    reg = build_regime(_d1(), None, None)
    assert (reg.regime == REGIME_NEUTRAL).all()
    assert reg.dollar.isna().all()


def test_attach_regime_uses_only_known_days():
    reg = pd.DataFrame({
        "known_from": pd.to_datetime(["2026-01-06 00:00"], utc=True),
        "regime": [REGIME_BUY], "trend": [1.0], "dollar": [1.0], "yields": [1.0], "total": [3.0]})
    df15 = pd.DataFrame({"time": pd.to_datetime(["2026-01-05 23:45", "2026-01-06 00:00"], utc=True)})
    out = attach_regime(df15, reg)
    assert out.regime.tolist() == [REGIME_NEUTRAL, REGIME_BUY]


def test_instrument_without_macro_uses_trend_only():
    from oanda import demo_candles, demo_daily
    d1 = demo_daily(demo_candles(40000))
    gold = build_regime(d1)  # złoto bez danych makro: zawsze neutralny
    other = build_regime(d1, macro=False)
    assert set(gold["regime"]) == {REGIME_NEUTRAL}
    assert {REGIME_BUY, REGIME_SELL} & set(other["regime"])
    assert other["dollar"].isna().all() and (other["total"].dropna() == other["trend"].dropna()).all()


def test_cycle_for_other_instrument():
    from config import Config, Instrument
    from cycle import Context, run_cycle
    from oanda import demo_candles, demo_daily
    from store import Store
    m15 = demo_candles(30000)
    cfg = Config()
    cfg.instruments = {"SPX500_USD": Instrument(name="SPX500_USD", group="indeksy", macro=False)}
    v = run_cycle(m15, demo_daily(m15), None, None, Store(), ctx=Context(cfg=cfg, instrument="SPX500_USD"))["verdict"]
    names = [r["name"] for r in v["report"]["checks"]]
    assert v["report"]["instrument"] == "SPX500_USD" and "Dolar (szeroki indeks)" not in names
    assert "trend D1" in v["reasoning"]
