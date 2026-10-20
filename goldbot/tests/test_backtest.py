import pandas as pd

import backtest
from strategy import Params


def bar(t, o, h, l, c, half=0.1, atr=1.0, signal=0):
    d = {"time": pd.Timestamp("2026-01-05", tz="UTC") + pd.Timedelta(minutes=15 * t),
         "atr": atr, "signal": signal}
    for k, v in zip("ohlc", (o, h, l, c)):
        d[f"bid_{k}"], d[f"ask_{k}"] = v - half, v + half
    return d


def tp_frame():
    return pd.DataFrame([bar(0, 100, 100.5, 99.5, 100, signal=1), bar(1, 100, 100.5, 99.5, 100),
                         bar(2, 100, 104, 100, 103), bar(3, 103, 103, 103, 103)])


def test_long_take_profit_is_plus_2R():
    t, s = backtest.run(tp_frame(), Params())
    assert s["trades"] == 1 and t.iloc[0].reason == "TP"
    assert abs(t.iloc[0].R - 2.0) < 1e-9


def test_long_stop_loss_is_minus_1R():
    df = pd.DataFrame([bar(0, 100, 100.5, 99.5, 100, signal=1), bar(1, 100, 100.5, 99.5, 100),
                       bar(2, 100, 100.2, 98, 98.5), bar(3, 98, 98, 98, 98)])
    t, s = backtest.run(df, Params())
    assert t.iloc[0].reason == "SL" and abs(t.iloc[0].R + 1.0) < 1e-9


def test_wide_spread_skips_entry():
    df = pd.DataFrame([bar(0, 100, 100.5, 99.5, 100, half=0.5, signal=1),
                       bar(1, 100, 100.5, 99.5, 100, half=0.5), bar(2, 100, 104, 100, 103, half=0.5)])
    assert backtest.run(df, Params())[1] == {"trades": 0}


def test_stats_are_plain_python_numbers():
    s = backtest.run(tp_frame(), Params())[1]
    assert all(type(v) in (int, float) for v in s.values())
