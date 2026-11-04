"""Jeden cykl dzienny: dane -> kontrola -> rozliczenie -> prognoza -> werdykt -> zapis -> powiadomienie."""
import pandas as pd

from daily_advisor import KIND, TRADE, close_at_market, make_daily_verdict, peak_since, resolve_daily
from features import build_features
from guards import DataError, validate_candles
from model import predict_last, top_drivers
from regime import build_regime
from sources import DailyData, is_daily_stale

MIN_D1 = 300
ARMED_KEY = "daily_armed"


def latest_row(data: DailyData) -> pd.Series:
    """Ostatni wiersz cech wzbogacony o reżim i bid/ask zamknięcia (do werdyktu)."""
    feat = build_features(data.gold, data.usd, data.yld)
    reg = build_regime(data.gold[["time", "bid_c", "ask_c"]], data.usd, data.yld).iloc[-1]
    row = feat.iloc[-1].copy()
    for c in ("regime", "trend", "dollar", "yields"):
        row[c] = reg[c]
    row["bid_c"] = float(data.gold["bid_c"].iloc[-1])
    row["ask_c"] = float(data.gold["ask_c"].iloc[-1])
    return feat, row


def should_store_daily(prev, new) -> bool:
    if prev is None:
        return True
    if new["time"] == prev["time"]:
        return False
    return new["verdict"] in TRADE or new["verdict"] == "ZAMKNIJ" or new["verdict"] != prev["verdict"]


def run_daily_cycle(data: DailyData, bundle: dict, report: dict, store, send=None, now=None) -> dict:
    """Rzuca guards.DataError przy uszkodzonych danych; wtedy nic nie jest zapisywane."""
    validate_candles(data.gold, "D1", MIN_D1)
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    mode, trail = bundle.get("mode", "long"), bundle.get("trail_atr")
    warnings = list(data.warnings)
    stale = is_daily_stale(data.gold["time"].iloc[-1], now)
    if stale:
        warnings.append(f"Dane nieaktualne: ostatnia świeca dzienna z {data.gold['time'].iloc[-1]:%Y-%m-%d}.")

    store.upsert_candles("D", data.gold)
    resolved = 0
    if mode != "long":  # w trybie long wyjścia robi werdykt (sygnał albo stop kroczący), bez horyzontu
        for o in store.open_verdicts(KIND):
            res = resolve_daily(o, data.gold, o.get("horizon") or 10)
            if res:
                store.close_verdict(o["id"], *res)
                resolved += 1

    feat, row = latest_row(data)
    p_up = predict_last(bundle, feat)
    open_v = (store.open_verdicts(KIND) or [None])[0]
    peak = peak_since(data.gold, open_v["time"]) if open_v else None
    armed = (store.get_current(ARMED_KEY) or {"armed": True})["armed"]
    v = make_daily_verdict(row, p_up, bundle["threshold"], report["has_edge"], report["edge_text"], open_v,
                           top_drivers(bundle, feat), store.stats(KIND), warnings, horizon=report["horizon"],
                           mode=mode, trail_atr=trail, peak=peak, armed=armed)
    if stale and v["verdict"] in TRADE:
        v.update(verdict="CZEKAJ", entry=None, sl=None, status="NONE",
                 reasoning="Rada handlowa wstrzymana: dane nieaktualne. " + v["reasoning"])
    if v["close_open"] and open_v is not None:
        store.close_verdict(open_v["id"], *close_at_market(open_v, v["close_px"], row.name))
        resolved += 1
    elif v["verdict"] == "TRZYMAJ" and open_v is not None and v["sl"] is not None and v["sl"] != open_v["sl"]:
        store.update_verdict_sl(open_v["id"], v["sl"])
    store.set_current({"armed": bool(v["armed"])}, key=ARMED_KEY)

    prev = store.last_verdict(KIND)
    stored = should_store_daily(prev, v)
    if stored:
        store.add_verdict(v)
        if send and (prev is None or v["verdict"] != prev["verdict"] or v["verdict"] in TRADE):
            from notify import format_daily_message
            send(format_daily_message(v))
    store.set_current(v, key="daily")
    return {"verdict": v, "stored": stored, "resolved": resolved, "p_up": p_up}
