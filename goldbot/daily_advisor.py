"""Werdykt dzienny: KUP / SPRZEDAJ / TRZYMAJ / ZAMKNIJ / CZEKAJ z uzasadnieniem po polsku."""
import pandas as pd

from advisor import regime_text
from features import FEATURES_PL
from regime import REGIME_BUY, REGIME_PL, REGIME_SELL

KIND = "D1"
STOP_ATR = 2.0
TRADE = ("KUP", "SPRZEDAJ")


def _fmt_feature(name: str, value: float) -> str:
    pl = FEATURES_PL.get(name, name)
    if name.startswith("ret_") or name.startswith("dist_") or name in ("vol20", "atr_pct"):
        return f"{pl} {100 * value:+.1f}%"
    if name.startswith("reg_"):
        return f"{pl} {'+' if value > 0 else '-' if value < 0 else '0'}"
    return f"{pl} {value:.2f}"


def make_daily_verdict(last_row: pd.Series, p_up: float, thr: float, has_edge: bool, edge_text: str,
                       open_v: dict | None, drivers: list, stats: dict, warnings: list,
                       horizon: int = 10, stop_atr: float = STOP_ATR) -> dict:
    """last_row: ostatni wiersz cech (index=time) z kolumnami close, atr, bid_c, ask_c, regime."""
    t = last_row.name
    regime = last_row["regime"]
    close, atr_v = float(last_row["close"]), float(last_row["atr"])
    bid, ask = float(last_row["bid_c"]), float(last_row["ask_c"])
    lines = [f"Model: prawdopodobieństwo wzrostu w {horizon} sesji {100 * p_up:.0f}% (próg rady {100 * thr:.0f}%)."]
    if drivers:
        lines.append("Najważniejsze cechy: " + ", ".join(_fmt_feature(n, v) for n, v in drivers) + ".")
    lines.append(f"Reżim dzienny: {REGIME_PL[regime]} ({regime_text(last_row)}).")

    verdict, entry, sl, close_open = "CZEKAJ", None, None, False
    want_long, want_short = p_up >= thr, p_up <= 1 - thr

    if not has_edge:
        lines.insert(0, edge_text + ". Rady handlowe wstrzymane; prognoza tylko informacyjnie.")
    elif open_v is not None:
        side = 1 if open_v["verdict"] == "KUP" else -1
        still = p_up > 0.5 if side == 1 else p_up < 0.5
        if (side == 1 and want_short) or (side == -1 and want_long):
            verdict, close_open = "ZAMKNIJ", True
            lines.append(f"Prognoza przeszła na przeciwną stronę progu: zamknij radę {open_v['verdict']} "
                         f"z {open_v['time'][:10]} po ok. {bid if side == 1 else ask:.2f}.")
        elif still:
            verdict = "TRZYMAJ"
            lines.append(f"Otwarta rada {open_v['verdict']} z {open_v['time'][:10]} (wejście {open_v['entry']:.2f}, "
                         f"stop {open_v['sl']:.2f}) nadal zgodna z prognozą.")
        else:
            verdict = "TRZYMAJ"
            lines.append(f"Prognoza osłabła, ale nie przeszła progu; rada {open_v['verdict']} z {open_v['time'][:10]} "
                         "zostaje do stopu albo końca horyzontu.")
    elif want_long and regime != REGIME_SELL:
        verdict, entry = "KUP", ask
        sl = entry - stop_atr * atr_v
        lines.append(f"Wejście po ask ok. {entry:.2f}, stop {sl:.2f} ({stop_atr:g} ATR), horyzont {horizon} sesji.")
    elif want_short and regime != REGIME_BUY:
        verdict, entry = "SPRZEDAJ", bid
        sl = entry + stop_atr * atr_v
        lines.append(f"Wejście po bid ok. {entry:.2f}, stop {sl:.2f} ({stop_atr:g} ATR), horyzont {horizon} sesji.")
    elif want_long or want_short:
        lines.append("Prognoza przekroczyła próg, ale reżim dzienny jest przeciwny; bez rady handlowej.")
    else:
        lines.append("Prognoza w strefie niepewności; czekamy.")

    if stats.get("trades"):
        lines.append(f"Dotychczasowe rady dzienne: {stats['trades']}, trafność {stats['win_rate_%']}%, "
                     f"średnio {stats['avg_R']:+.2f}R.")
    lines += warnings
    return {"time": pd.Timestamp(t).isoformat(), "verdict": verdict, "regime": regime, "entry": entry, "sl": sl,
            "tp": None, "atr": atr_v, "reasoning": " ".join(lines),
            "status": "OPEN" if verdict in TRADE else "NONE", "kind": KIND, "p_up": float(p_up),
            "horizon": horizon, "close_open": close_open, "close_px": bid if open_v and open_v["verdict"] == "KUP" else ask}


def resolve_daily(v: dict, gold: pd.DataFrame, horizon: int = 10):
    """(status, outcome_r, iso_time) albo None. Stop po low/high dnia, inaczej po `horizon` sesjach po zamknięciu."""
    t0 = pd.Timestamp(v["time"])
    side = 1 if v["verdict"] == "KUP" else -1
    entry, sl = v["entry"], v["sl"]
    risk = abs(entry - sl)
    if gold.empty:
        return None
    later = gold[gold["time"] > t0].reset_index(drop=True)
    for i, row in enumerate(later.itertuples(), start=1):
        if side == 1 and row.bid_l <= sl:
            return "SL", -1.0, row.time.isoformat()
        if side == -1 and row.ask_h >= sl:
            return "SL", -1.0, row.time.isoformat()
        if i >= horizon:
            px = row.bid_c if side == 1 else row.ask_c
            return "EXPIRED", side * (px - entry) / risk, row.time.isoformat()
    return None


def close_at_market(v: dict, px: float, when) -> tuple:
    side = 1 if v["verdict"] == "KUP" else -1
    risk = abs(v["entry"] - v["sl"])
    return "CLOSED", side * (px - v["entry"]) / risk, pd.Timestamp(when).isoformat()
