"""Model predykcyjny: gradient boosting uczony walk-forward, ocena poza próbą i bramka przewagi."""
import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score

from features import FEATURES, HORIZON

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "model.joblib")
REPORT_PATH = os.path.join(HERE, "model_report.json")

MIN_TRAIN = 1260          # ~5 lat sesji przed pierwszą prognozą
STEP = 63                 # przeuczanie co kwartał
SPLIT_DATE = "2020-12-31"  # próg wybierany tylko na prognozach do tej daty
GRID = (0.55, 0.58, 0.60, 0.65)
MIN_AUC = 0.52
MIN_TSTAT = 1.65          # jednostronny test 5%: średni dzienny zwrot strategii > 0


def make_model(seed: int = 0) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                          l2_regularization=1.0, min_samples_leaf=50, random_state=seed)


def walk_forward(feat: pd.DataFrame, min_train: int = MIN_TRAIN, step: int = STEP,
                 horizon: int = HORIZON, fit=None) -> pd.Series:
    """Prognoza p_up dla każdego dnia poza próbą. Model w dniu t uczy się tylko na wierszach,
    których cel (t+horizon) był znany przed t, czyli na indeksach < t - horizon."""
    X = feat[FEATURES].to_numpy(dtype=float)
    y = feat["y"].to_numpy(dtype=float)
    n = len(feat)
    p = np.full(n, np.nan)
    fit = fit or (lambda Xa, ya: make_model().fit(Xa, ya))
    start = min_train
    while start < n:
        tr = slice(0, start - horizon)
        mask = ~np.isnan(y[tr])
        if mask.sum() >= 200 and len(np.unique(y[tr][mask])) == 2:
            m = fit(X[tr][mask], y[tr][mask])
            end = min(start + step, n)
            p[start:end] = m.predict_proba(X[start:end])[:, 1]
        start += step
    return pd.Series(p, index=feat.index, name="p_up")


def positions(p_up: pd.Series, thr: float) -> pd.Series:
    pos = pd.Series(0.0, index=p_up.index)
    pos[p_up >= thr] = 1.0
    pos[p_up <= 1 - thr] = -1.0
    return pos


def strategy_returns(p_up: pd.Series, ret_1_fwd: pd.Series, cost: pd.Series, thr: float) -> pd.Series:
    """Zwrot dzienny: pozycja ustalona na zamknięciu t razy zwrot t->t+1, minus spread/2 przy zmianie pozycji."""
    pos = positions(p_up, thr)
    flips = pos.diff().abs().fillna(pos.abs())
    return pos * ret_1_fwd - flips * cost / 2


def metrics(p_up: pd.Series, y: pd.Series, ret_1_fwd: pd.Series, cost: pd.Series, thr: float) -> dict:
    ok = p_up.notna() & ret_1_fwd.notna()
    p, r1, c = p_up[ok], ret_1_fwd[ok], cost[ok]
    if len(p) < 50:
        return {"n": int(len(p))}
    yy = y[ok]
    lab = yy.notna()
    auc = float(roc_auc_score(yy[lab], p[lab])) if lab.sum() > 50 and yy[lab].nunique() == 2 else float("nan")
    acc = float(((p[lab] >= 0.5) == (yy[lab] == 1)).mean()) if lab.sum() else float("nan")
    sr = strategy_returns(p, r1, c, thr)
    eq = np.exp(sr.cumsum())
    dd = float((eq / eq.cummax() - 1).min())
    std = float(sr.std())
    sharpe = float(sr.mean() / std * np.sqrt(252)) if std > 0 else 0.0
    tstat = float(sr.mean() / std * np.sqrt(len(sr))) if std > 0 else 0.0
    pos = positions(p, thr)
    return {
        "n": int(len(p)), "accuracy": round(acc, 4), "auc": round(auc, 4),
        "return_%": round(100 * float(np.exp(sr.sum()) - 1), 2), "sharpe": round(sharpe, 3),
        "tstat": round(tstat, 2),
        "max_dd_%": round(100 * dd, 2), "flips": int(pos.diff().abs().fillna(pos.abs()).gt(0).sum()),
        "days_long_%": round(100 * float((pos > 0).mean()), 1),
        "days_short_%": round(100 * float((pos < 0).mean()), 1),
        "bh_return_%": round(100 * float(np.exp(r1.sum()) - 1), 2),
        "from": str(p.index[0].date()), "to": str(p.index[-1].date()),
    }


def _ret_1_fwd(feat: pd.DataFrame) -> pd.Series:
    return np.log(feat["close"]).shift(-1) - np.log(feat["close"])


def choose_threshold(p_up: pd.Series, feat: pd.DataFrame, split: str = SPLIT_DATE, grid=GRID) -> float:
    ins = p_up.index <= pd.Timestamp(split, tz="UTC")
    r1 = _ret_1_fwd(feat)
    best, best_s = grid[0], -np.inf
    for thr in grid:
        m = metrics(p_up[ins], feat["y"][ins], r1[ins], feat["cost"][ins], thr)
        s = m.get("sharpe", -np.inf)
        if s > best_s:
            best, best_s = thr, s
    return float(best)


def _period_ok(m: dict) -> bool:
    return m.get("n", 0) >= 250 and m["auc"] > MIN_AUC and m["sharpe"] > 0 and m["return_%"] > 0


def _period_txt(name: str, m: dict) -> str:
    if m.get("n", 0) < 250:
        return f"{name}: za mało prognoz ({m.get('n', 0)})"
    return (f"{name} {m['from']}..{m['to']}: AUC {m['auc']:.3f}, Sharpe {m['sharpe']:.2f}, t {m['tstat']:.2f}, "
            f"zwrot {m['return_%']:+.1f}% (kup i trzymaj {m['bh_return_%']:+.1f}%), obsunięcie {m['max_dd_%']:.1f}%")


def edge_verdict(ins: dict, oos: dict) -> tuple[bool, str]:
    """Przewaga tylko, gdy jest w OBU okresach (strojenia i kontrolnym) i jest istotna statystycznie
    w okresie kontrolnym. Dobry wynik w jednym okresie to za mało: może być hossą, nie umiejętnością."""
    ok = _period_ok(ins) and _period_ok(oos) and oos.get("tstat", 0) > MIN_TSTAT
    txt = _period_txt("okres strojenia", ins) + "; " + _period_txt("okres kontrolny", oos)
    if ok:
        return True, "Model ma przewagę poza próbą; " + txt
    return False, "Model nie ma udowodnionej przewagi poza próbą; " + txt


def regime_baseline(feat: pd.DataFrame, ins) -> tuple[dict, dict]:
    """Punkt odniesienia bez ML: długa gdy suma składników reżimu >= 2, krótka gdy <= -2 (jak regime.py)."""
    total = feat[["reg_trend", "reg_dollar", "reg_yields"]].sum(axis=1, min_count=3)
    pseudo = pd.Series(0.5, index=feat.index)
    pseudo[total >= 2] = 1.0
    pseudo[total <= -2] = 0.0
    r1 = _ret_1_fwd(feat)
    pseudo = pseudo.where(feat["reg_trend"].notna())
    return (metrics(pseudo[ins], feat["y"][ins], r1[ins], feat["cost"][ins], 0.75),
            metrics(pseudo[~ins], feat["y"][~ins], r1[~ins], feat["cost"][~ins], 0.75))


def by_year(p_up: pd.Series, feat: pd.DataFrame, thr: float) -> dict:
    r1 = _ret_1_fwd(feat)
    out = {}
    for yr, idx in p_up.dropna().groupby(p_up.dropna().index.year).groups.items():
        m = metrics(p_up[idx], feat["y"][idx], r1[idx], feat["cost"][idx], thr)
        if "sharpe" in m:
            out[int(yr)] = {k: m[k] for k in ("n", "auc", "return_%", "sharpe", "max_dd_%", "bh_return_%")}
    return out


def evaluate(feat: pd.DataFrame, split: str = SPLIT_DATE) -> tuple[dict, pd.Series]:
    p_up = walk_forward(feat)
    thr = choose_threshold(p_up, feat, split)
    r1 = _ret_1_fwd(feat)
    ins = p_up.index <= pd.Timestamp(split, tz="UTC")
    rep_in = metrics(p_up[ins], feat["y"][ins], r1[ins], feat["cost"][ins], thr)
    rep_out = metrics(p_up[~ins], feat["y"][~ins], r1[~ins], feat["cost"][~ins], thr)
    has_edge, text = edge_verdict(rep_in, rep_out)
    base_in, base_out = regime_baseline(feat, ins)
    report = {"regime_baseline": {"in_sample": base_in, "out_of_sample": base_out},"trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "rows": int(len(feat)), "data_from": str(feat.index[0].date()), "data_to": str(feat.index[-1].date()),
              "split": split, "threshold": thr, "horizon": HORIZON, "features": FEATURES,
              "in_sample": rep_in, "out_of_sample": rep_out, "by_year": by_year(p_up, feat, thr),
              "has_edge": bool(has_edge), "edge_text": text}
    return report, p_up


def fit_final(feat: pd.DataFrame, horizon: int = HORIZON, seed: int = 0):
    """Model produkcyjny na całej historii z znanym celem oraz ważność cech (permutacyjna)."""
    lab = feat["y"].notna()
    X, y = feat.loc[lab, FEATURES].to_numpy(dtype=float), feat.loc[lab, "y"].to_numpy(dtype=float)
    m = make_model(seed).fit(X, y)
    tail = slice(max(0, len(X) - 750), len(X))  # ważność na ostatnich 3 latach
    imp = permutation_importance(m, X[tail], y[tail], n_repeats=5, random_state=seed, scoring="roc_auc")
    importances = {f: float(v) for f, v in zip(FEATURES, imp.importances_mean)}
    return m, importances


def save_model(path: str, model, threshold: float, importances: dict, report: dict):
    joblib.dump({"model": model, "features": FEATURES, "threshold": threshold,
                 "importances": importances, "trained_at": report["trained_at"]}, path)


def load_model(path: str = MODEL_PATH):
    return joblib.load(path) if os.path.exists(path) else None


def save_report(report: dict, path: str = REPORT_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)


def load_report(path: str = REPORT_PATH):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def predict_last(bundle: dict, feat: pd.DataFrame) -> float:
    x = feat[bundle["features"]].iloc[[-1]].to_numpy(dtype=float)
    return float(bundle["model"].predict_proba(x)[0, 1])


def top_drivers(bundle: dict, feat: pd.DataFrame, k: int = 3) -> list[tuple[str, float]]:
    """Cechy o największej ważności wraz z ich bieżącą wartością."""
    imp = sorted(bundle["importances"].items(), key=lambda kv: -kv[1])[:k]
    last = feat.iloc[-1]
    return [(name, float(last[name])) for name, _ in imp]
