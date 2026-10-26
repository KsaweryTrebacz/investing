import numpy as np
import pandas as pd

import research.sizing as S


def frame(closes, lows=None, highs=None, spread=0.0):
    idx = pd.date_range("2021-01-04", periods=len(closes), freq="B")
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"o": c, "h": c if highs is None else highs, "l": c if lows is None else lows, "c": c,
                         "spread": spread}, index=idx)


def test_daily_rebalanced_leverage():
    d = frame([100.0, 101.0, 102.01])
    eq = S.simulate(d, np.ones(3), np.full(3, 2.0), long_rate=0.0)
    assert abs(eq.iloc[1] - 1.02) < 1e-12 and abs(eq.iloc[2] - 1.02 * 1.02) < 1e-9   # dźwignia 2 przeliczana codziennie


def test_liquidation_and_zero_floor():
    d = frame([100.0, 100.0, 100.0], lows=[100.0, 98.0, 100.0])
    eq = S.simulate(d, np.ones(3), np.full(3, 50.0), long_rate=0.0)
    assert 0.49 < eq.iloc[1] < 0.5                                             # likwidacja przy ~-1%
    d = frame([100.0, 80.0], lows=[100.0, 80.0])
    d.loc[d.index[1], "o"] = 80.0
    assert S.simulate(d, np.ones(2), np.full(2, 10.0), long_rate=0.0).iloc[-1] == 0.0   # luka -20% przy 10x


def test_short_and_flat_positions():
    d = frame([100.0, 99.0, 99.0])
    eq = S.simulate(d, np.array([-1.0, 0.0, 0.0]), np.full(3, 5.0), short_rate=0.0)
    assert abs(eq.iloc[1] - 1.05) < 1e-12 and eq.iloc[2] == eq.iloc[1]


def test_vol_leverage_and_fresh_window():
    d = frame(100 * np.exp(np.cumsum(np.tile([0.01, -0.01], 30))))
    lev = S.vol_leverage(d, 0.16, window=20)
    assert lev[:20].max() == 0.0 and abs(lev[-1] - 0.16 / (0.01 * np.sqrt(252) * np.sqrt(20 / 19))) < 0.05
    w = S.wealth(d, np.ones(len(d)), np.ones(len(d)), d.index[10], d.index[12], (0.0, 0.0))
    assert abs(w - d["c"].iloc[11] / d["c"].iloc[9]) < 1e-9                     # świeży rachunek od dnia przed oknem
