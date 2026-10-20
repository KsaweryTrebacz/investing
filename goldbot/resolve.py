"""Rozstrzyganie otwartych werdyktów po fakcie: TP, SL albo wygaśnięcie po 48 h."""
import pandas as pd


def resolve(v: dict, candles: pd.DataFrame, expire_hours: int = 48):
    """Zwraca (status, outcome_r, iso_time) albo None, gdy werdykt wciąż otwarty."""
    t0 = pd.Timestamp(v["time"])
    side = 1 if v["verdict"] == "KUP" else -1
    entry, sl, tp = v["entry"], v["sl"], v["tp"]
    risk, reward = abs(entry - sl), abs(tp - entry)
    deadline = t0 + pd.Timedelta(hours=expire_hours)
    for row in candles[candles["time"] > t0].itertuples():
        if side == 1:   # pozycja długa zamykana po BID
            hit_sl, hit_tp = row.bid_l <= sl, row.bid_h >= tp
        else:           # pozycja krótka zamykana po ASK
            hit_sl, hit_tp = row.ask_h >= sl, row.ask_l <= tp
        if hit_sl:      # gdy obie w jednej świecy: konserwatywnie SL
            return "SL", -1.0, row.time.isoformat()
        if hit_tp:
            return "TP", reward / risk, row.time.isoformat()
        if row.time >= deadline:
            px = row.bid_c if side == 1 else row.ask_c
            return "EXPIRED", side * (px - entry) / risk, row.time.isoformat()
    return None
