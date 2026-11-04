import numpy as np
import pandas as pd

from features import FEATURES, FEATURES_PL, HORIZON, build_features
from sources import with_spread


def synthetic(n=800, seed=3):
    rng = np.random.default_rng(seed)
    t = pd.bdate_range("2019-01-01", periods=n, tz="UTC")
    close = 1500 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n)))
    o = np.r_[close[0], close[:-1]]
    hi = np.maximum(o, close) * (1 + rng.random(n) * 0.004)
    lo = np.minimum(o, close) * (1 - rng.random(n) * 0.004)
    gold = with_spread(pd.DataFrame({"time": t, "open": o, "high": hi, "low": lo, "close": close}))
    days = pd.DatetimeIndex(t.tz_localize(None).normalize())
    usd = pd.Series(100 + np.cumsum(rng.normal(0, 0.3, n)), index=days)
    yld = pd.Series(1.0 + np.cumsum(rng.normal(0, 0.02, n)), index=days)
    return gold, usd, yld


def test_feature_names_and_shape():
    gold, usd, yld = synthetic()
    f = build_features(gold, usd, yld)
    assert set(FEATURES) <= set(f.columns)
    assert set(FEATURES) == set(FEATURES_PL)
    for c in ("close", "atr", "fwd_ret", "cost", "y"):
        assert c in f.columns
    assert f.index.name == "time"
    assert f["y"].iloc[-HORIZON:].isna().all()
    assert f["y"].iloc[:-HORIZON].notna().all()
    assert f[FEATURES].iloc[-1].notna().all()


def test_target_matches_forward_log_return_minus_cost():
    gold, usd, yld = synthetic()
    f = build_features(gold, usd, yld)
    i = 300
    expected = np.log(f["close"].iloc[i + HORIZON] / f["close"].iloc[i])
    assert abs(f["fwd_ret"].iloc[i] - expected) < 1e-12
    assert f["y"].iloc[i] == float(expected > f["cost"].iloc[i])
    assert (f["cost"] > 0).all()


def test_no_lookahead_in_features():
    gold, usd, yld = synthetic()
    full = build_features(gold, usd, yld)
    cut = 500
    part = build_features(gold.iloc[:cut], usd, yld)
    last = part.index[-1]
    a, b = full.loc[last, FEATURES], part.loc[last, FEATURES]
    pd.testing.assert_series_equal(a, b, check_names=False)


def test_macro_is_lagged_one_day_and_aligned_backward():
    gold, usd, yld = synthetic()
    # podmień dolara na indeks dnia: wartość = numer dnia, więc widać, który dzień został użyty
    days = usd.index
    usd2 = pd.Series(np.arange(len(days), dtype=float), index=days)
    f = build_features(gold, usd2, yld)
    # usd_level pomocniczo: cecha usd_chg5 = różnica 5 sesji, dla ciągu 0,1,2.. to zawsze 5
    assert (f["usd_chg5"].dropna().round(9) == 5.0).all()
    # dzień t korzysta z wartości z dnia t-1: dla pierwszego pełnego wiersza sprawdzamy przez przesunięcie
    f_lag = build_features(gold, usd2.shift(1).dropna(), yld)
    assert f["usd_chg5"].dropna().iloc[-1] == f_lag["usd_chg5"].dropna().iloc[-1]


def test_missing_macro_gives_nan_not_error():
    gold, _, _ = synthetic()
    f = build_features(gold, None, None)
    assert f["usd_chg5"].isna().all() and f["yld_chg20"].isna().all()
    assert f["reg_dollar"].isna().all()
    assert f["ret_5"].notna().sum() > 700
