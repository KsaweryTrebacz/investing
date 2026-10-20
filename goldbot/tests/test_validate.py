from oanda import demo_candles, demo_daily, demo_macro
from pipeline import prepare
from validate import walk_forward


def test_walk_forward_returns_four_blocks():
    m15 = demo_candles(30000)
    d1 = demo_daily(m15)
    df = prepare(m15, d1, *demo_macro(d1))
    res = walk_forward(df, split=0.7)
    assert set(res) == {"in_sample", "out_of_sample", "in_sample_bez_rezimu", "out_of_sample_bez_rezimu"}
    assert all("trades" in r for r in res.values())


def test_regime_signals_are_subset_of_raw_signals():
    m15 = demo_candles(30000)
    d1 = demo_daily(m15)
    df = prepare(m15, d1, *demo_macro(d1))
    gated = df.signal != 0
    assert (df.signal[gated] == df.signal_raw[gated]).all()
    assert gated.sum() <= (df.signal_raw != 0).sum()
