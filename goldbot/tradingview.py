"""Świece z eksportu CSV wykresu TradingView ("Export chart data"). TradingView nie ma publicznego API danych.

Eksport ma jedną cenę, bez bid/ask, więc bid i ask są przybliżone typowym spreadem z konfiguracji.
Ostatnia świeca w eksporcie bywa jeszcze niezamknięta, więc świece, które trwają, są pomijane.
"""
import pandas as pd

TF = {"M15": pd.Timedelta(minutes=15), "D": pd.Timedelta(days=1)}


def load_csv(path: str, spread: float | None, granularity: str, now=None) -> pd.DataFrame:
    if spread is None:
        raise ValueError("Import z TradingView wymaga typowego spreadu (csv.spread w konfiguracji instrumentu).")
    raw = pd.read_csv(path)
    cols = {c.strip().lower(): c for c in raw.columns}
    missing = [c for c in ("time", "open", "high", "low", "close") if c not in cols]
    if missing:
        raise ValueError(f"{path}: brak kolumn {missing} (eksport TradingView: time, open, high, low, close).")
    t = raw[cols["time"]]
    time = pd.to_datetime(t, unit="s", utc=True) if pd.api.types.is_numeric_dtype(t) else pd.to_datetime(t, utc=True)
    out = pd.DataFrame({"time": time})
    half = spread / 2
    for k, name in zip("ohlc", ("open", "high", "low", "close")):
        px = raw[cols[name]].astype(float)
        out[f"bid_{k}"], out[f"ask_{k}"] = px - half, px + half
    if "volume" in cols:
        out["volume"] = raw[cols["volume"]].astype(float)
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    out = out[out["time"] + TF[granularity] <= now]
    return out.drop_duplicates("time").sort_values("time").reset_index(drop=True)
