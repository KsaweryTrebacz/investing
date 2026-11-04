import numpy as np
import pandas as pd

import model as M
from features import FEATURES, HORIZON, build_features
from sources import with_spread


def predictable_gold(n=2200, seed=5):
    """Szereg z silną, sztuczną zależnością: po 20 sesjach spadku przychodzi wzrost (i odwrotnie)."""
    rng = np.random.default_rng(seed)
    r = np.zeros(n)
    for i in range(1, n):
        mom = r[max(0, i - 20):i].sum()
        r[i] = -0.12 * mom + rng.normal(0, 0.004)
    close = 1500 * np.exp(np.cumsum(r))
    t = pd.bdate_range("2012-01-02", periods=n, tz="UTC")
    o = np.r_[close[0], close[:-1]]
    df = pd.DataFrame({"time": t, "open": o, "high": np.maximum(o, close) * 1.002,
                       "low": np.minimum(o, close) * 0.998, "close": close})
    return with_spread(df)


def test_walk_forward_has_nan_before_min_train_and_trains_on_past_only():
    feat = build_features(predictable_gold(), None, None)
    seen = []

    def spy_fit(X, y):
        seen.append(len(X))
        return M.make_model().fit(X, y)

    p = M.walk_forward(feat, min_train=1260, step=63, fit=spy_fit)
    assert p.iloc[:1260].isna().all()
    assert p.iloc[1260:].notna().all()
    # pierwszy model: wiersze 0..1260-HORIZON minus rozgrzewka (NaN w cechach jest OK, ale y musi być znane)
    assert seen[0] <= 1260 - HORIZON
    assert len(seen) == int(np.ceil((len(feat) - 1260) / 63))


def test_walk_forward_finds_planted_signal():
    feat = build_features(predictable_gold(), None, None)
    report, p = M.evaluate(feat, split="2017-12-31")
    assert report["out_of_sample"]["auc"] > 0.6
    assert report["has_edge"] and report["mode"] in M.MODES
    assert report["out_of_sample"]["tstat"] > M.MIN_TSTAT
    assert report["threshold"] in M.GRID
    assert "in_sample" in report["regime_baseline"] and set(report["modes"]) == set(M.MODES)
    assert set(report["by_year"]) >= {2018, 2019}


def test_metrics_on_handmade_series():
    idx = pd.bdate_range("2021-01-01", periods=300, tz="UTC")
    p = pd.Series(np.r_[np.full(150, 0.9), np.full(150, 0.1)], index=idx)
    r1 = pd.Series(np.r_[np.full(150, 0.001), np.full(150, -0.001)], index=idx)  # zawsze zgodnie z pozycją
    y = (r1 > 0).astype(float)
    cost = pd.Series(0.0, index=idx)
    m = M.metrics(p, y, r1, cost, thr=0.6, mode="ls")
    assert m["n"] == 300 and m["flips"] == 2  # wejście w długą, potem zmiana na krótką
    ml = M.metrics(p, y, r1, cost, thr=0.6, mode="long")
    assert ml["flips"] == 2 and ml["days_short_%"] == 0 and abs(ml["return_%"] - 100 * (np.exp(0.15) - 1)) < 0.01
    assert abs(m["return_%"] - 100 * (np.exp(0.3) - 1)) < 0.01  # metryka zaokrąglona do 2 miejsc
    assert m["auc"] == 1.0 and m["max_dd_%"] == 0.0


def test_edge_verdict_requires_both_periods_beating_hold_and_significance():
    base = {"n": 1000, "from": "2021-01-04", "to": "2026-11-03", "bh_return_%": 50.0, "max_dd_%": -10.0,
            "days_long_%": 30.0, "days_short_%": 0.0, "bh_sharpe": 0.5}
    good = {**base, "sharpe": 0.8, "return_%": 12.0, "tstat": 2.1}
    worse_than_hold = {**base, "sharpe": 0.4, "return_%": 5.0, "tstat": 2.1}
    bad_sh = {**base, "sharpe": -0.1, "return_%": -2.0, "tstat": -0.3}
    weak_t = {**good, "tstat": 1.0}
    ok, txt = M.edge_verdict(good, good)
    assert ok and "ma przewagę" in txt and "w gotówce" in txt
    assert not M.edge_verdict(worse_than_hold, good)[0]   # nie bije kup-i-trzymaj w strojeniu
    assert not M.edge_verdict(good, bad_sh)[0]            # słaby okres kontrolny
    assert not M.edge_verdict(good, weak_t)[0]            # nieistotne statystycznie
    ok, txt = M.edge_verdict({"n": 100}, good)
    assert not ok and "za mało" in txt
    assert "długa/krótka" in M.edge_verdict(good, good, "ls")[1]


def test_fit_final_save_load_predict(tmp_path):
    feat = build_features(predictable_gold(1500), None, None)
    m, imp = M.fit_final(feat)
    assert set(imp) == set(FEATURES)
    path = str(tmp_path / "m.joblib")
    M.save_model(path, m, 0.6, imp, {"trained_at": "x"})
    b = M.load_model(path)
    p = M.predict_last(b, feat)
    assert 0.0 <= p <= 1.0
    assert len(M.top_drivers(b, feat)) == 3 and b["mode"] == "long"
    assert M.load_model(str(tmp_path / "none.joblib")) is None
