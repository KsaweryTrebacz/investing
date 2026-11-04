import numpy as np
import pandas as pd

from momentum import TrendParams
from research.paper_trend import paper_trade, summarize


def d1_frame(closes, low_drop=0.0):
    t = pd.date_range("2025-01-05 22:00", periods=len(closes), freq="D", tz="UTC")
    c = np.array(closes, dtype=float)
    d = {"time": t}
    for side, off in (("bid", -0.05), ("ask", 0.05)):
        d.update({f"{side}_o": c + off, f"{side}_h": c + 1 + off, f"{side}_l": c * (1 - low_drop) - 1 + off,
                  f"{side}_c": c + off})
    return pd.DataFrame(d)


def wiggly(n, drift):
    return 1000 * np.exp(np.cumsum(drift + 0.01 * np.tile([1.0, -1.0], n // 2 + 1)[:n]))


def test_paper_trade_follows_advice_in_uptrend():
    curve, log = paper_trade(d1_frame(wiggly(260, 0.003)), TrendParams(), "2025-01-01", 10_000.0, long_rate=0.0)
    assert log["action"].iloc[0] == "OTWÓRZ LONG" and curve.iloc[-1] > 10_000
    assert set(log["action"]) <= {"OTWÓRZ LONG", "ZWIĘKSZ", "ZMNIEJSZ", "ZAMKNIJ"}
    s = summarize(curve, log, 10_000.0)
    assert s["mnoznik"] > 1 and s["transakcje"]["OTWÓRZ LONG"] == 1


def test_paper_trade_liquidates_on_deep_intraday_drop():
    curve, log = paper_trade(d1_frame(wiggly(260, 0.003), low_drop=0.5), TrendParams(), "2025-01-01", 10_000.0,
                             long_rate=0.0)
    assert "LIKWIDACJA" in set(log["action"]) and curve.min() < 10_000


def test_no_position_in_downtrend():
    curve, log = paper_trade(d1_frame(wiggly(260, -0.003)), TrendParams(), "2025-01-01", 10_000.0)
    assert log.empty and curve.iloc[-1] == 10_000.0
