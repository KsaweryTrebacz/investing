import pandas as pd

from oanda import demo_candles, demo_daily, demo_macro
from pipeline import prepare
from regime import REGIME_BUY, REGIME_NEUTRAL, REGIME_SELL
from strategy import gate_by_regime


def test_gate_keeps_only_signals_matching_regime():
    df = pd.DataFrame({
        "signal": [1, 1, -1, -1],
        "regime": [REGIME_BUY, REGIME_NEUTRAL, REGIME_SELL, REGIME_BUY]})
    out = gate_by_regime(df)
    assert out.signal.tolist() == [1, 0, -1, 0]
    assert out.signal_raw.tolist() == [1, 1, -1, -1]


def test_prepare_with_demo_data():
    m15 = demo_candles(30000)
    d1 = demo_daily(m15)
    usd, yld = demo_macro(d1)
    df = prepare(m15, d1, usd, yld)
    assert {"signal", "signal_raw", "regime", "atr"} <= set(df.columns)
    assert set(df.signal.unique()) <= {-1, 0, 1}
    assert len(df) == len(m15)


def test_prepare_without_macro_never_signals():
    m15 = demo_candles(30000)
    df = prepare(m15, demo_daily(m15), None, None)
    assert (df.signal == 0).all()
    assert (df.regime == REGIME_NEUTRAL).all()
