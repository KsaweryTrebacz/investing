import pandas as pd

from oanda import demo_candles
from store import Store


def verdict(t, v="KUP", regime="SPRZYJA_KUPNIE", status="OPEN"):
    return {"time": t, "verdict": v, "regime": regime, "entry": 2000.0, "sl": 1990.0, "tp": 2020.0,
            "atr": 6.0, "reasoning": "x", "status": status}


def test_candles_roundtrip_and_upsert():
    s = Store()
    df = demo_candles(10)
    s.upsert_candles("M15", df)
    s.upsert_candles("M15", df)  # drugi zapis nie dubluje
    out = s.load_candles("M15", 100)
    assert len(out) == 10
    assert out["time"].is_monotonic_increasing
    assert abs(out["bid_c"].iloc[-1] - df["bid_c"].iloc[-1]) < 1e-9
    assert len(s.load_candles("M15", 3)) == 3
    assert s.load_candles("D", 10).empty


def test_verdict_lifecycle():
    s = Store()
    vid = s.add_verdict(verdict("2026-01-05T10:00:00+00:00"))
    assert [v["id"] for v in s.open_verdicts()] == [vid]
    s.close_verdict(vid, "TP", 2.0, "2026-01-05T12:00:00+00:00")
    assert s.open_verdicts() == []
    assert s.last_verdict()["status"] == "TP"
    assert s.recent_verdicts(5)[0]["outcome_r"] == 2.0


def test_wait_verdicts_are_not_open():
    s = Store()
    s.add_verdict(verdict("2026-01-05T10:00:00+00:00", v="CZEKAJ", status="NONE"))
    assert s.open_verdicts() == []


def test_stats():
    s = Store()
    for i, r in enumerate([2.0, -1.0, -1.0, 2.0]):
        vid = s.add_verdict(verdict(f"2026-01-0{i + 1}T10:00:00+00:00"))
        s.close_verdict(vid, "TP" if r > 0 else "SL", r, f"2026-01-0{i + 1}T11:00:00+00:00")
    st = s.stats()
    assert st["trades"] == 4 and st["win_rate_%"] == 50.0
    assert st["total_R"] == 2.0 and st["max_drawdown_R"] == -2.0


def test_stats_empty():
    assert Store().stats() == {"trades": 0}


def test_current_roundtrip():
    s = Store()
    assert s.get_current() is None
    s.set_current({"verdict": "CZEKAJ", "entry": None})
    assert s.get_current() == {"verdict": "CZEKAJ", "entry": None}


def test_volume_roundtrip_and_optional():
    s = Store()
    df = demo_candles(5).assign(volume=[10, 20, 30, 40, 50])
    s.upsert_candles("M15", df)
    assert s.load_candles("M15", 10)["volume"].tolist() == [10, 20, 30, 40, 50]
    s.upsert_candles("D", demo_candles(3).drop(columns=["volume"], errors="ignore"))
    assert s.load_candles("D", 10)["volume"].isna().all()


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    path = str(tmp_path / "stara.db")
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE candles (granularity TEXT NOT NULL, time TEXT NOT NULL, bid_o REAL NOT NULL,
            bid_h REAL NOT NULL, bid_l REAL NOT NULL, bid_c REAL NOT NULL, ask_o REAL NOT NULL,
            ask_h REAL NOT NULL, ask_l REAL NOT NULL, ask_c REAL NOT NULL, PRIMARY KEY (granularity, time));
        CREATE TABLE verdicts (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT UNIQUE NOT NULL,
            verdict TEXT NOT NULL, regime TEXT NOT NULL, entry REAL, sl REAL, tp REAL, atr REAL, reasoning TEXT,
            status TEXT NOT NULL, outcome_r REAL, resolved_time TEXT);
        INSERT INTO verdicts (time, verdict, regime, status) VALUES ('2026-01-01T00:00:00+00:00', 'CZEKAJ', 'NEUTRALNY', 'NONE');
    """)
    old.close()
    s = Store(path)
    assert s.last_verdict()["decision"] is None and "cost_r" in s.last_verdict()
    s.upsert_candles("M15", demo_candles(3))
    assert len(s.load_candles("M15", 10)) == 3


def test_report_and_net_stats():
    s = Store()
    v = {**verdict("2026-01-05T10:00:00+00:00"), "decision": "MOZLIWA_TRANSAKCJA", "report": {"a": 1}}
    vid = s.add_verdict(v)
    s.close_verdict(vid, "TP", 2.0, "2026-01-05T12:00:00+00:00", cost_r=0.1)
    assert s.stats()["total_R_net"] == 1.9
    assert s.resolved_verdicts(5)[0]["resolved_time"] == "2026-01-05T12:00:00+00:00"
    vid = s.add_verdict(verdict("2026-01-06T10:00:00+00:00"))
    s.close_verdict(vid, "SL", -1.0, "2026-01-06T11:00:00+00:00")
    assert s.stats()["total_R_net"] is None  # koszt jednej rady nieznany
