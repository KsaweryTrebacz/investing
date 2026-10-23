"""Magazyn SQLite: świece, werdykty i ostatni werdykt cyklu."""
import json
import sqlite3

import numpy as np
import pandas as pd

PRICE_COLS = [f"{s}_{k}" for s in ("bid", "ask") for k in "ohlc"]
VERDICT_COLS = ["time", "verdict", "regime", "entry", "sl", "tp", "atr", "reasoning", "status", "decision", "report"]
RESOLVED = "status IN ('TP','SL','EXPIRED')"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS candles (
    granularity TEXT NOT NULL, time TEXT NOT NULL,
    {", ".join(c + " REAL NOT NULL" for c in PRICE_COLS)},
    PRIMARY KEY (granularity, time));
CREATE TABLE IF NOT EXISTS verdicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT UNIQUE NOT NULL,
    verdict TEXT NOT NULL, regime TEXT NOT NULL,
    entry REAL, sl REAL, tp REAL, atr REAL, reasoning TEXT,
    status TEXT NOT NULL, outcome_r REAL, resolved_time TEXT);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
# Kolumny dodane później. Starsze bazy dostają je przy otwarciu (ALTER TABLE).
MIGRATIONS = {"candles": {"volume": "REAL"},
              "verdicts": {"decision": "TEXT", "report": "TEXT", "cost_r": "REAL"}}


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        with self.db:
            for table, cols in MIGRATIONS.items():
                have = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
                for col, typ in cols.items():
                    if col not in have:
                        self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")

    # --- świece ---
    def upsert_candles(self, granularity: str, df: pd.DataFrame):
        """Zapisuje świece; wolumen (tickowy) jest opcjonalny."""
        vol = df["volume"] if "volume" in df else pd.Series(np.nan, index=df.index)
        rows = [(granularity, t.isoformat(), *(float(r[c]) for c in PRICE_COLS), None if pd.isna(v) else float(v))
                for t, r, v in zip(df["time"], df.to_dict("records"), vol)]
        cols = ["granularity", "time", *PRICE_COLS, "volume"]
        with self.db:
            self.db.executemany(f"INSERT OR REPLACE INTO candles ({', '.join(cols)}) "
                                f"VALUES ({','.join('?' * len(cols))})", rows)

    def load_candles(self, granularity: str, limit: int) -> pd.DataFrame:
        cur = self.db.execute(
            f"SELECT time, {', '.join(PRICE_COLS)}, volume FROM candles WHERE granularity=? "
            "ORDER BY time DESC LIMIT ?", (granularity, limit))
        rows = [dict(r) for r in cur.fetchall()][::-1]
        df = pd.DataFrame(rows, columns=["time", *PRICE_COLS, "volume"])
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df["volume"] = df["volume"].astype(float)
        return df

    # --- werdykty ---
    def add_verdict(self, v: dict) -> int:
        vals = [json.dumps(v.get(c), default=str) if c == "report" and v.get(c) is not None else v.get(c)
                for c in VERDICT_COLS]
        with self.db:
            cur = self.db.execute(
                f"INSERT INTO verdicts ({', '.join(VERDICT_COLS)}) VALUES ({','.join('?' * len(VERDICT_COLS))})", vals)
        return cur.lastrowid

    def _one(self, sql, args=()):
        r = self.db.execute(sql, args).fetchone()
        return dict(r) if r else None

    def last_verdict(self):
        return self._one("SELECT * FROM verdicts ORDER BY time DESC LIMIT 1")

    def recent_verdicts(self, n: int):
        return [dict(r) for r in self.db.execute("SELECT * FROM verdicts ORDER BY time DESC LIMIT ?", (n,))]

    def open_verdicts(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM verdicts WHERE status='OPEN' ORDER BY time")]

    def resolved_verdicts(self, n: int):
        """Ostatnie rozliczone rady (do szacunku czasu utrzymania)."""
        return [dict(r) for r in self.db.execute(
            f"SELECT time, resolved_time, outcome_r FROM verdicts WHERE {RESOLVED} ORDER BY time DESC LIMIT ?", (n,))]

    def close_verdict(self, vid: int, status: str, outcome_r: float, resolved_time: str, cost_r: float | None = None):
        with self.db:
            self.db.execute("UPDATE verdicts SET status=?, outcome_r=?, resolved_time=?, cost_r=? WHERE id=?",
                            (status, float(outcome_r), resolved_time, cost_r, vid))

    def realized_r_since(self, since_iso: str) -> float:
        """Suma R rad rozliczonych od `since_iso` (czas rozliczenia)."""
        r = self.db.execute(f"SELECT COALESCE(SUM(outcome_r), 0) FROM verdicts "
                            f"WHERE {RESOLVED} AND resolved_time >= ?", (since_iso,))
        return float(r.fetchone()[0])

    def stats(self) -> dict:
        """Skuteczność rad. R po kosztach (prowizja, finansowanie) tylko, gdy koszty są znane dla wszystkich rad."""
        rows = self.db.execute(f"SELECT outcome_r, cost_r FROM verdicts WHERE {RESOLVED} ORDER BY time").fetchall()
        if not rows:
            return {"trades": 0}
        r = np.array([x[0] for x in rows])
        cum = np.cumsum(r)
        peak = np.maximum.accumulate(np.r_[0.0, cum])[1:]
        costs = [x[1] for x in rows]
        net = None if any(c is None for c in costs) else round(float((r - np.array(costs)).sum()), 3)
        return {"trades": int(len(r)), "win_rate_%": round(100 * float((r > 0).mean()), 1),
                "avg_R": round(float(r.mean()), 3), "total_R": round(float(cum[-1]), 3),
                "max_drawdown_R": round(float((cum - peak).min()), 3), "total_R_net": net}

    # --- ostatni werdykt cyklu (także niezapisany w historii) ---
    def set_current(self, v: dict):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES ('current', ?)", (json.dumps(v, default=str),))

    def get_current(self):
        r = self.db.execute("SELECT value FROM state WHERE key='current'").fetchone()
        return json.loads(r[0]) if r else None
