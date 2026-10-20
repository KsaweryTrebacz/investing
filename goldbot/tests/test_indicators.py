import numpy as np
import pandas as pd

from indicators import atr, ema, macd_hist, rsi


def test_ema_of_constant_is_constant():
    assert np.allclose(ema(pd.Series([5.0] * 50), 10), 5.0)


def test_rsi_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert rsi(up).iloc[-1] == 100
    assert rsi(up[::-1].reset_index(drop=True)).iloc[-1] < 1


def test_macd_hist_of_constant_is_zero():
    assert np.allclose(macd_hist(pd.Series([100.0] * 80)), 0.0)


def test_atr_of_constant_range():
    h, l, c = (pd.Series([v] * 30) for v in (102.0, 100.0, 101.0))
    assert np.allclose(atr(h, l, c, 14), 2.0)
