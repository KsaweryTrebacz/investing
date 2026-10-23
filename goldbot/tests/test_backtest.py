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


def test_gap_through_stop_is_worse_than_minus_1R():
    df = pd.DataFrame([bar(0, 100, 100.5, 99.5, 100, signal=1), bar(1, 100, 100.5, 99.5, 100),
                       bar(2, 97, 97.2, 96.5, 97), bar(3, 97, 97, 97, 97)])
    t, _ = backtest.run(df, Params())
    assert t.iloc[0].reason == "SL" and t.iloc[0].R < -1.0  # wyjście po otwarciu 96,9 zamiast SL 98,6


def test_costs_reduce_result():
    from config import Costs
    c = Costs(commission_per_unit=0.15, financing_long_rate=0.0, slippage_atr=0.0)
    t, _ = backtest.run(tp_frame(), Params(), costs=c)
    assert abs(t.iloc[0].R - (2.0 - 0.3 / 1.5)) < 1e-9


def test_position_expires_like_live_advice():
    rows = [bar(0, 100, 100.5, 99.5, 100, signal=1)] + [bar(t, 100, 100.5, 99.5, 100) for t in range(1, 200)]
    t, _ = backtest.run(pd.DataFrame(rows), Params())
    assert t.iloc[0].reason == "EXPIRED"
    assert t.iloc[0].exit_time - t.iloc[0].entry_time == pd.Timedelta(hours=48)
    assert backtest.run(pd.DataFrame(rows), Params(), expire_hours=None)[0].iloc[0].reason == "END"
