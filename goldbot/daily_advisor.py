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
    pct_prefix = ("ret_", "dist_", "brk_", "mom_", "dd_from", "run_from", "ema_slope", "gap_pct", "body_pct")
    if name.startswith(pct_prefix) or name in ("vol20", "atr_pct", "atr_trend", "vol_ratio"):
        return f"{pl} {100 * value:+.1f}%"
    if name.startswith("reg_"):
        return f"{pl} {'+' if value > 0 else '-' if value < 0 else '0'}"
    return f"{pl} {value:.2f}"


def make_daily_verdict(last_row: pd.Series, p_up: float, thr: float, has_edge: bool, edge_text: str,
                       open_v: dict | None, drivers: list, stats: dict, warnings: list,
                       horizon: int = 10, stop_atr: float = STOP_ATR, mode: str = "long",
                       trail_atr=None, peak: float | None = None, armed: bool = True) -> dict:
    """last_row: ostatni wiersz cech (index=time) z kolumnami close, atr, bid_c, ask_c, regime.

    mode "long": w złocie (p_up >= próg) albo w gotówce; wyjście, gdy p_up spada pod próg albo gdy
                 zamknięcie spada o `trail_atr` ATR poniżej szczytu od wejścia (stop kroczący, jak w backteście).
                 Po stopie kroczącym nowe wejście dopiero, gdy sygnał zgaśnie i wróci (`armed`).
    mode "ls":   długa / krótka ze stałym stopem; wyjście, gdy prognoza przejdzie na przeciwną stronę progu.
    peak: najwyższe zamknięcie od wejścia (łącznie z dzisiejszym), potrzebne przy otwartej radzie w trybie long.
    """
    t = last_row.name
    regime = last_row["regime"]
    close, atr_v = float(last_row["close"]), float(last_row["atr"])
    bid, ask = float(last_row["bid_c"]), float(last_row["ask_c"])
    atr_pct = atr_v / close
    lines = [f"Model: prawdopodobieństwo wzrostu w {horizon} sesji {100 * p_up:.0f}% (próg rady {100 * thr:.0f}%)."]
    if drivers:
        lines.append("Najważniejsze cechy: " + ", ".join(_fmt_feature(n, v) for n, v in drivers) + ".")
    lines.append(f"Reżim dzienny: {REGIME_PL[regime]} ({regime_text(last_row)}).")

    verdict, entry, sl, close_open = "CZEKAJ", None, None, False
    want_long = p_up >= thr
    want_short = (p_up <= 1 - thr) if mode == "ls" else False
    exit_long = (p_up < thr) if mode == "long" else (p_up <= 1 - thr)
    use_trail = mode == "long" and trail_atr is not None
    new_armed = True if not want_long else armed  # sygnał pod progiem uzbraja ponownie

    if not has_edge:
        lines.insert(0, edge_text + ". Rady handlowe wstrzymane; prognoza tylko informacyjnie.")
    elif open_v is not None:
        side = 1 if open_v["verdict"] == "KUP" else -1
        still = p_up > 0.5 if side == 1 else p_up < 0.5
        level = None
        if use_trail and side == 1:
            pk = max(peak if peak is not None else close, close)
            level = pk * (1 - trail_atr * atr_pct)
        if use_trail and side == 1 and close < level:
            verdict, close_open, new_armed = "ZAMKNIJ", True, False
            lines.append(f"Stop kroczący: zamknięcie {close:.2f} spadło pod {level:.2f} ({trail_atr:g} ATR od szczytu "
                         f"{pk:.2f}). Zamknij radę KUP z {open_v['time'][:10]} po ok. {bid:.2f} (do gotówki). "
                         "Nowe wejście dopiero, gdy sygnał zgaśnie i wróci.")
        elif (side == 1 and exit_long) or (side == -1 and want_long):
            verdict, close_open = "ZAMKNIJ", True
            lines.append(f"Prognoza spadła pod próg: zamknij radę {open_v['verdict']} "
                         f"z {open_v['time'][:10]} po ok. {bid if side == 1 else ask:.2f} (do gotówki).")
        elif level is not None:
            verdict, sl = "TRZYMAJ", max(level, float(open_v["sl"] or level))
            lines.append(f"Otwarta rada KUP z {open_v['time'][:10]} (wejście {open_v['entry']:.2f}) nadal nad progiem. "
                         f"Stop kroczący teraz {sl:.2f}.")
        elif still:
            verdict = "TRZYMAJ"
            lines.append(f"Otwarta rada {open_v['verdict']} z {open_v['time'][:10]} (wejście {open_v['entry']:.2f}, "
                         f"stop {open_v['sl']:.2f}) nadal zgodna z prognozą.")
        else:
            verdict = "TRZYMAJ"
            lines.append(f"Prognoza osłabła, ale nie przeszła progu; rada {open_v['verdict']} z {open_v['time'][:10]} "
                         "zostaje do stopu albo końca horyzontu.")
    elif want_long and use_trail and not armed:
        lines.append("Prognoza nad progiem, ale po ostatnim stopie kroczącym czekamy, aż sygnał zgaśnie i wróci.")
    elif want_long and regime != REGIME_SELL:
        verdict, entry = "KUP", ask
        if use_trail:
            sl = close * (1 - trail_atr * atr_pct)
            lines.append(f"Wejście po ask ok. {entry:.2f}, stop kroczący {sl:.2f} ({trail_atr:g} ATR od szczytu zamknięć), "
                         "wyjście także gdy prognoza spadnie pod próg.")
        else:
            sl = entry - stop_atr * atr_v
            lines.append(f"Wejście po ask ok. {entry:.2f}, stop {sl:.2f} ({stop_atr:g} ATR), horyzont {horizon} sesji.")
    elif want_short and regime != REGIME_BUY:
        verdict, entry = "SPRZEDAJ", bid
        sl = entry + stop_atr * atr_v
        lines.append(f"Wejście po bid ok. {entry:.2f}, stop {sl:.2f} ({stop_atr:g} ATR), horyzont {horizon} sesji.")
    elif want_long or want_short:
        lines.append("Prognoza przekroczyła próg, ale reżim dzienny jest przeciwny; bez rady handlowej.")
    elif mode == "long":
        lines.append("Prognoza pod progiem: według modelu nie opłaca się teraz być w złocie; zostajemy w gotówce.")
    else:
        lines.append("Prognoza w strefie niepewności; czekamy.")

    if stats.get("trades"):
        lines.append(f"Dotychczasowe rady dzienne: {stats['trades']}, trafność {stats['win_rate_%']}%, "
                     f"średnio {stats['avg_R']:+.2f}R.")
    lines += warnings
    return {"time": pd.Timestamp(t).isoformat(), "verdict": verdict, "regime": regime, "entry": entry, "sl": sl,
            "tp": None, "atr": atr_v, "reasoning": " ".join(lines),
            "status": "OPEN" if verdict in TRADE else "NONE", "kind": KIND, "p_up": float(p_up),
            "horizon": horizon, "close_open": close_open, "armed": new_armed,
            "close_px": bid if open_v and open_v["verdict"] == "KUP" else ask}


def resolve_daily(v: dict, gold: pd.DataFrame, horizon: int = 10):
    """(status, outcome_r, iso_time) albo None. Stop po low/high dnia, inaczej po `horizon` sesjach po zamknięciu.
    Używane w trybie długa/krótka; w trybie long wyjścia robi cykl (sygnał albo stop kroczący)."""
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


def peak_since(gold: pd.DataFrame, since_iso: str) -> float:
    """Najwyższe zamknięcie (mid) od otwarcia rady, łącznie z ostatnią świecą."""
    t0 = pd.Timestamp(since_iso)
    part = gold[gold["time"] >= t0]
    mid = (part["bid_c"] + part["ask_c"]) / 2
    return float(mid.max()) if len(mid) else float("nan")


def close_at_market(v: dict, px: float, when) -> tuple:
    side = 1 if v["verdict"] == "KUP" else -1
    risk = abs(v["entry"] - v["sl"]) or 1e-9
    return "CLOSED", side * (px - v["entry"]) / risk, pd.Timestamp(when).isoformat()
