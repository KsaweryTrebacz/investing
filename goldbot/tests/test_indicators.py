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


def test_vwap_resets_each_utc_day():
    from indicators import vwap
    t = pd.to_datetime(["2026-01-05 10:00", "2026-01-05 10:15", "2026-01-06 00:00"], utc=True)
    df = pd.DataFrame({"time": t, "volume": [1.0, 3.0, 2.0]})
    for s in ("bid", "ask"):
        for k in "hlc":
            df[f"{s}_{k}"] = [10.0, 20.0, 30.0]
    assert vwap(df).tolist() == [10.0, 17.5, 30.0]
    assert vwap(df.drop(columns=["volume"])).isna().all()


def test_volume_ratio():
    from indicators import volume_ratio
    r = volume_ratio(pd.Series([1.0, 1.0, 1.0, 3.0]), n=2)
    assert r.isna().iloc[0] and r.iloc[1] == 1.0 and r.iloc[3] == 1.5
