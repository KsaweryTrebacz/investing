import numpy as np
import pandas as pd

from patterns import PATTERN_FEATURES, PATTERN_FEATURES_PL, _streak, add_patterns


def test_names_have_polish_labels():
    assert set(PATTERN_FEATURES) == set(PATTERN_FEATURES_PL)


def test_streak_counts_consecutive_true():
    s = pd.Series([True, True, False, True, True, True, False])
    assert _streak(s).tolist() == [1, 2, 0, 1, 2, 3, 0]


def test_patterns_on_handmade_candles():
    n = 300
    t = pd.bdate_range("2024-01-01", periods=n, tz="UTC")
    c = pd.Series(np.linspace(100, 160, n))           # równy trend wzrostowy
    o = c.shift(1).fillna(100.0)
    h, l = c + 0.05, o - 0.05                            # cień mniejszy niż dzienny krok (0,2)
    f = add_patterns(pd.DataFrame(index=range(n)), o, h, l, c, t)
    last = f.iloc[-1]
    assert set(PATTERN_FEATURES) <= set(f.columns)
    assert last["up_streak"] == n - 1 and last["dn_streak"] == 0
    assert last["brk_hi20"] > 0 and last["brk_lo20"] > 0          # nad szczytem i nad dołkiem 20 sesji
    assert last["hh_count20"] == 20 and last["ll_count20"] == 0
    assert last["dd_from_peak250"] == 0 and last["run_from_low250"] > 0
    assert last["mom_250"] > 0 and last["ema_align"] == 1.0 and last["ema_slope50"] > 0
    assert 0.0 <= last["close_pos"] <= 1.0 and 0.0 <= last["upper_wick"] <= 1.0
    assert last["eff_ratio20"] > 0.99                              # ruch bez szumu
    assert last["dow"] in range(5) and 1 <= last["month"] <= 12
