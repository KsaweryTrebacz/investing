import pandas as pd

from daily_advisor import close_at_market, make_daily_verdict, resolve_daily
from store import Store

T = pd.Timestamp("2026-11-03", tz="UTC")


def row(regime="NEUTRALNY", close=4000.0, atr=60.0):
    r = pd.Series({"close": close, "atr": atr, "bid_c": close - 0.25, "ask_c": close + 0.25, "regime": regime,
                   "trend": 1.0, "dollar": 0.0, "yields": -1.0, "ret_20": 0.05, "rsi14": 61.0, "reg_trend": 1.0})
    r.name = T
    return r


EDGE = dict(has_edge=True, edge_text="Model ma przewagę poza próbą; x")
NO_EDGE = dict(has_edge=False, edge_text="Model nie ma udowodnionej przewagi poza próbą; x")
DRIVERS = [("ret_20", 0.05), ("rsi14", 61.0), ("reg_trend", 1.0), ("brk_lo20", 0.021)]
STATS = {"trades": 4, "win_rate_%": 50.0, "avg_R": 0.3}


def verdict(p_up, regime="NEUTRALNY", open_v=None, edge=EDGE, stats=STATS, warnings=(), mode="ls"):
    return make_daily_verdict(row(regime), p_up, 0.6, edge["has_edge"], edge["edge_text"], open_v, DRIVERS,
                              stats, list(warnings), mode=mode)


def test_no_edge_blocks_trading_but_shows_forecast():
    v = verdict(0.9, edge=NO_EDGE)
    assert v["verdict"] == "CZEKAJ" and v["status"] == "NONE" and v["entry"] is None
    assert v["reasoning"].startswith("Model nie ma udowodnionej przewagi")
    assert "90%" in v["reasoning"] and v["kind"] == "D1" and v["p_up"] == 0.9


def test_buy_when_above_threshold_and_regime_not_against():
    v = verdict(0.65)
    assert v["verdict"] == "KUP" and v["status"] == "OPEN"
    assert v["entry"] == 4000.25 and v["sl"] == 4000.25 - 120.0 and v["tp"] is None
    assert "zwrot 20 sesji +5.0%" in v["reasoning"] and "RSI 14 61.00" in v["reasoning"]
    assert "odległość od dołka 20 sesji +2.1%" in v["reasoning"]
    assert "Dotychczasowe rady dzienne: 4" in v["reasoning"]


def test_sell_mirrors_buy_and_regime_blocks():
    v = verdict(0.3)
    assert v["verdict"] == "SPRZEDAJ" and v["entry"] == 3999.75 and v["sl"] == 3999.75 + 120.0
    assert verdict(0.3, regime="SPRZYJA_KUPNIE")["verdict"] == "CZEKAJ"
    assert verdict(0.7, regime="SPRZYJA_SPRZEDAZY")["verdict"] == "CZEKAJ"
    assert "reżim dzienny jest przeciwny" in verdict(0.7, regime="SPRZYJA_SPRZEDAZY")["reasoning"]


def test_wait_in_uncertainty_zone_and_warnings_appended():
    v = verdict(0.5, warnings=["Dane z pamięci podręcznej sprzed 1.0 dnia."])
    assert v["verdict"] == "CZEKAJ" and v["reasoning"].endswith("sprzed 1.0 dnia.")


OPEN_BUY = {"time": "2026-10-28T00:00:00+00:00", "verdict": "KUP", "entry": 3950.0, "sl": 3850.0}


def test_hold_and_close_with_open_advice():
    assert verdict(0.62, open_v=OPEN_BUY)["verdict"] == "TRZYMAJ"
    weak = verdict(0.45, open_v=OPEN_BUY)
    assert weak["verdict"] == "TRZYMAJ" and "osłabła" in weak["reasoning"]
    c = verdict(0.35, open_v=OPEN_BUY)
    assert c["verdict"] == "ZAMKNIJ" and c["close_open"] and c["close_px"] == 3999.75
    assert c["status"] == "NONE"
    # z otwartą radą nie otwieramy nowej, nawet gdy prognoza silna po tej samej stronie
    assert verdict(0.9, open_v=OPEN_BUY)["verdict"] == "TRZYMAJ"


def test_long_mode_never_shorts_and_exits_below_threshold():
    assert verdict(0.3, mode="long")["verdict"] == "CZEKAJ"
    assert "w gotówce" in verdict(0.3, mode="long")["reasoning"]
    assert verdict(0.65, mode="long")["verdict"] == "KUP"
    assert verdict(0.65, open_v=OPEN_BUY, mode="long")["verdict"] == "TRZYMAJ"
    c = verdict(0.55, open_v=OPEN_BUY, mode="long")       # pod progiem 0.6, choć > 0.5
    assert c["verdict"] == "ZAMKNIJ" and c["close_open"]
    assert verdict(0.55, open_v=OPEN_BUY, mode="ls")["verdict"] == "TRZYMAJ"


def gold(rows):
    out = []
    for i, (h, l, c) in enumerate(rows, start=1):
        out.append({"time": T + pd.Timedelta(days=i), "bid_h": h, "bid_l": l, "bid_c": c,
                    "ask_h": h, "ask_l": l, "ask_c": c})
    return pd.DataFrame(out)


BUY = {"time": T.isoformat(), "verdict": "KUP", "entry": 100.0, "sl": 96.0}
SELL = {"time": T.isoformat(), "verdict": "SPRZEDAJ", "entry": 100.0, "sl": 104.0}


def test_resolve_daily_stop_and_expiry():
    assert resolve_daily(BUY, gold([(101, 99, 100), (100, 95.5, 97)]))[0:2] == ("SL", -1.0)
    assert resolve_daily(SELL, gold([(104.5, 99, 103)]))[0:2] == ("SL", -1.0)
    s, r, _ = resolve_daily(BUY, gold([(103, 99, 102)] * 10))
    assert s == "EXPIRED" and r == 0.5
    assert resolve_daily(BUY, gold([(103, 99, 102)] * 9)) is None
    assert resolve_daily(BUY, gold([])) is None


def test_close_at_market_r():
    s, r, t = close_at_market(BUY, 102.0, T)
    assert s == "CLOSED" and r == 0.5 and t == T.isoformat()
    assert close_at_market(SELL, 102.0, T)[1] == -0.5


def test_store_keeps_kinds_apart_and_migrates(tmp_path):
    import sqlite3
    db = str(tmp_path / "old.db")
    con = sqlite3.connect(db)
    con.executescript("""CREATE TABLE verdicts (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT UNIQUE NOT NULL,
        verdict TEXT NOT NULL, regime TEXT NOT NULL, entry REAL, sl REAL, tp REAL, atr REAL, reasoning TEXT,
        status TEXT NOT NULL, outcome_r REAL, resolved_time TEXT);
        INSERT INTO verdicts (time, verdict, regime, status) VALUES ('2026-01-01T00:00:00+00:00','KUP','NEUTRALNY','OPEN');""")
    con.commit(); con.close()
    s = Store(db)
    assert s.open_verdicts()[0]["kind"] == "M15"
    v = verdict(0.65)
    s.add_verdict(v)
    assert len(s.open_verdicts()) == 2 and len(s.open_verdicts("D1")) == 1
    assert s.last_verdict("D1")["p_up"] == 0.65 and s.last_verdict("D1")["horizon"] == 10
    s.close_verdict(s.open_verdicts("D1")[0]["id"], "CLOSED", 0.5, "2026-11-05T00:00:00+00:00")
    assert s.stats("D1")["trades"] == 1 and s.stats("M15")["trades"] == 0
    s.set_current({"a": 1}, key="daily")
    assert s.get_current("daily") == {"a": 1} and s.get_current() is None
