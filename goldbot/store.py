"""Magazyn SQLite: świece, werdykty i ostatni werdykt cyklu."""
import json
import sqlite3

import numpy as np
import pandas as pd

PRICE_COLS = [f"{s}_{k}" for s in ("bid", "ask") for k in "ohlc"]
VERDICT_COLS = ["time", "verdict", "regime", "entry", "sl", "tp", "atr", "reasoning", "status"]

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS candles (
    granularity TEXT NOT NULL, time TEXT NOT NULL,
    {", ".join(c + " REAL NOT NULL" for c in PRICE_COLS)},
    PRIMARY KEY (granularity, time));
CREATE TABLE IF NOT EXISTS verdicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT UNIQUE NOT NULL,
    verdict TEXT NOT NULL, regime TEXT NOT NULL,
    entry REAL, sl REAL, tp REAL, atr REAL, reasoning TEXT,
    status TEXT NOT NULL, outcome_r REAL, resolved_time TEXT,
    kind TEXT NOT NULL DEFAULT 'M15', p_up REAL, horizon INTEGER);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
MIGRATIONS = ["ALTER TABLE verdicts ADD COLUMN kind TEXT NOT NULL DEFAULT 'M15'",
              "ALTER TABLE verdicts ADD COLUMN p_up REAL",
              "ALTER TABLE verdicts ADD COLUMN horizon INTEGER"]
OPTIONAL_COLS = ["kind", "p_up", "horizon"]
CLOSED = "('TP','SL','EXPIRED','CLOSED')"


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        have = {r[1] for r in self.db.execute("PRAGMA table_info(verdicts)")}
        for sql in MIGRATIONS:  # stare bazy bez nowych kolumn
            if sql.split(" ADD COLUMN ")[1].split()[0] not in have:
                self.db.execute(sql)
        self.db.commit()

    @staticmethod
    def _kind_clause(kind):
        return ("", ()) if kind is None else (" AND kind=?", (kind,))

    # --- świece ---
    def upsert_candles(self, granularity: str, df: pd.DataFrame):
        rows = [(granularity, t.isoformat(), *(float(r[c]) for c in PRICE_COLS))
                for t, r in zip(df["time"], df.to_dict("records"))]
        marks = ",".join("?" * (2 + len(PRICE_COLS)))
        with self.db:
            self.db.executemany(f"INSERT OR REPLACE INTO candles VALUES ({marks})", rows)

    def load_candles(self, granularity: str, limit: int) -> pd.DataFrame:
        cur = self.db.execute(
            f"SELECT time, {', '.join(PRICE_COLS)} FROM candles WHERE granularity=? "
            "ORDER BY time DESC LIMIT ?", (granularity, limit))
        rows = [dict(r) for r in cur.fetchall()][::-1]
        df = pd.DataFrame(rows, columns=["time", *PRICE_COLS])
        df["time"] = pd.to_datetime(df["time"], utc=True)
        return df

    # --- werdykty ---
    def add_verdict(self, v: dict) -> int:
        cols = VERDICT_COLS + OPTIONAL_COLS
        marks = ",".join("?" * len(cols))
        with self.db:
            cur = self.db.execute(
                f"INSERT INTO verdicts ({', '.join(cols)}) VALUES ({marks})",
                [v[c] for c in VERDICT_COLS] + [v.get("kind", "M15"), v.get("p_up"), v.get("horizon")])
        return cur.lastrowid

    def _one(self, sql, args=()):
        r = self.db.execute(sql, args).fetchone()
        return dict(r) if r else None

    def last_verdict(self, kind=None):
        k, a = self._kind_clause(kind)
        return self._one(f"SELECT * FROM verdicts WHERE 1=1{k} ORDER BY time DESC LIMIT 1", a)

    def recent_verdicts(self, n: int, kind=None):
        k, a = self._kind_clause(kind)
        return [dict(r) for r in self.db.execute(
            f"SELECT * FROM verdicts WHERE 1=1{k} ORDER BY time DESC LIMIT ?", (*a, n))]

    def open_verdicts(self, kind=None):
        k, a = self._kind_clause(kind)
        return [dict(r) for r in self.db.execute(
            f"SELECT * FROM verdicts WHERE status='OPEN'{k} ORDER BY time", a)]

    def update_verdict_sl(self, vid: int, sl: float):
        with self.db:
            self.db.execute("UPDATE verdicts SET sl=? WHERE id=?", (float(sl), vid))

    def close_verdict(self, vid: int, status: str, outcome_r: float, resolved_time: str):
        with self.db:
            self.db.execute("UPDATE verdicts SET status=?, outcome_r=?, resolved_time=? WHERE id=?",
                            (status, float(outcome_r), resolved_time, vid))

    def realized_r_since(self, since_iso: str) -> float:
        """Suma R rad rozliczonych od `since_iso` (czas rozliczenia)."""
        r = self.db.execute("SELECT COALESCE(SUM(outcome_r), 0) FROM verdicts "
                            f"WHERE status IN {CLOSED} AND resolved_time >= ?", (since_iso,))
        return float(r.fetchone()[0])

    def stats(self, kind=None) -> dict:
        k, a = self._kind_clause(kind)
        r = np.array([x[0] for x in self.db.execute(
            f"SELECT outcome_r FROM verdicts WHERE status IN {CLOSED}{k} ORDER BY time", a)])
        if len(r) == 0:
            return {"trades": 0}
        cum = np.cumsum(r)
        peak = np.maximum.accumulate(np.r_[0.0, cum])[1:]
        return {"trades": int(len(r)), "win_rate_%": round(100 * float((r > 0).mean()), 1),
                "avg_R": round(float(r.mean()), 3), "total_R": round(float(cum[-1]), 3),
                "max_drawdown_R": round(float((cum - peak).min()), 3)}

    # --- ostatni werdykt cyklu (także niezapisany w historii) ---
    def set_current(self, v: dict, key: str = "current"):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, json.dumps(v, default=str)))

    def get_current(self, key: str = "current"):
        r = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else None
