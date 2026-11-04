import numpy as np
import pandas as pd
import pytest

import daily_cycle
from daily_cycle import run_daily_cycle, should_store_daily
from features import FEATURES
from guards import DataError
from sources import DailyData, with_spread
from store import Store


class FakeModel:
    def __init__(self, p):
        self.p = p

    def predict_proba(self, X):
        return np.array([[1 - self.p, self.p]] * len(X))


def bundle(p):
    return {"model": FakeModel(p), "features": FEATURES, "threshold": 0.6,
            "importances": {f: 0.0 for f in FEATURES} | {"ret_20": 1.0, "rsi14": 0.5, "reg_trend": 0.2}}


REPORT_EDGE = {"has_edge": True, "edge_text": "Model ma przewagę poza próbą; x", "horizon": 10}
REPORT_NOEDGE = {"has_edge": False, "edge_text": "Model nie ma udowodnionej przewagi poza próbą; x", "horizon": 10}


def data(n=400, end="2026-11-03", seed=1):
    rng = np.random.default_rng(seed)
    t = pd.bdate_range(end=end, periods=n, tz="UTC")
    close = 3500 * np.exp(np.cumsum(rng.normal(0, 0.008, n)))
    o = np.r_[close[0], close[:-1]]
    gold = with_spread(pd.DataFrame({"time": t, "open": o, "high": np.maximum(o, close) * 1.003,
                                     "low": np.minimum(o, close) * 0.997, "close": close}))
    days = pd.DatetimeIndex(t.tz_localize(None))
    usd = pd.Series(100 + np.cumsum(rng.normal(0, 0.3, n)), index=days)
    yld = pd.Series(1.5 + np.cumsum(rng.normal(0, 0.02, n)), index=days)
    return DailyData(gold, usd, yld, "free", ["ostrzeżenie testowe"])


NOW = pd.Timestamp("2026-11-03 23:30", tz="UTC")


def test_buy_cycle_stores_notifies_and_then_holds():
    store, sent = Store(), []
    r = run_daily_cycle(data(), bundle(0.7), REPORT_EDGE, store, sent.append, now=NOW)
    v = r["verdict"]
    assert v["verdict"] == "KUP" and r["stored"] and len(sent) == 1 and "ostrzeżenie testowe" in v["reasoning"]
    assert v["kind"] == "D1" and store.get_current("daily")["verdict"] == "KUP" and store.get_current() is None
    assert len(store.load_candles("D", 10**6)) == 400
    r2 = run_daily_cycle(data(), bundle(0.7), REPORT_EDGE, store, sent.append, now=NOW)
    assert r2["verdict"]["verdict"] == "TRZYMAJ" and not r2["stored"] and len(sent) == 1


def test_close_on_reversal_next_day():
    store = Store()
    run_daily_cycle(data(), bundle(0.7), REPORT_EDGE, store, now=NOW)
    nxt = data(401, end="2026-11-04")
    r = run_daily_cycle(nxt, bundle(0.2), REPORT_EDGE, store, now=NOW + pd.Timedelta(days=1))
    assert r["verdict"]["verdict"] == "ZAMKNIJ" and r["resolved"] == 1
    assert store.open_verdicts("D1") == [] and store.stats("D1")["trades"] == 1
    assert store.recent_verdicts(1, "D1")[0]["verdict"] == "ZAMKNIJ"


def test_no_edge_never_trades():
    store = Store()
    r = run_daily_cycle(data(), bundle(0.95), REPORT_NOEDGE, store, now=NOW)
    assert r["verdict"]["verdict"] == "CZEKAJ" and store.open_verdicts("D1") == []
    assert r["verdict"]["reasoning"].startswith("Model nie ma")


def test_stale_data_blocks_trade():
    store = Store()
    r = run_daily_cycle(data(), bundle(0.7), REPORT_EDGE, store, now=NOW + pd.Timedelta(days=7))
    assert r["verdict"]["verdict"] == "CZEKAJ" and "nieaktualne" in r["verdict"]["reasoning"]


def test_bad_data_raises_and_stores_nothing():
    store = Store()
    d = data()
    d.gold.loc[10, "ask_c"] = d.gold.loc[10, "bid_c"] - 1
    with pytest.raises(DataError):
        run_daily_cycle(d, bundle(0.7), REPORT_EDGE, store, now=NOW)
    assert store.last_verdict() is None


def test_should_store_daily():
    a = {"time": "t1", "verdict": "CZEKAJ"}
    assert should_store_daily(None, a)
    assert not should_store_daily(a, a)
    assert not should_store_daily(a, {"time": "t2", "verdict": "CZEKAJ"})
    assert should_store_daily(a, {"time": "t2", "verdict": "TRZYMAJ"})
    assert should_store_daily({"time": "t1", "verdict": "KUP"}, {"time": "t2", "verdict": "KUP"})
