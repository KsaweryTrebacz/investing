"""Werdykt KUP / SPRZEDAJ / CZEKAJ z uzasadnieniem w języku polskim."""
import pandas as pd

from regime import REGIME_PL
from strategy import Params

TRADE = ("KUP", "SPRZEDAJ")


def _component(name, v, up, down, flat):
    if pd.isna(v):
        return f"{name}: brak danych"
    return f"{name}: " + (up if v > 0 else down if v < 0 else flat)


def regime_text(row, macro: bool = True) -> str:
    if not macro:
        return _component("trend D1", row["trend"], "wzrostowy", "spadkowy", "boczny")
    return "; ".join([
        _component("trend złota", row["trend"], "wzrostowy", "spadkowy", "boczny"),
        _component("dolar", row["dollar"], "słabnie, sprzyja złotu", "umacnia się, szkodzi złotu", "boczny"),
        _component("realne rentowności", row["yields"], "spadają, sprzyja złotu",
                   "rosną, szkodzą złotu", "boczne"),
    ])


def make_verdict(df: pd.DataFrame, p: Params = Params(), macro: bool = True) -> dict:
    """Werdykt na podstawie ostatniej ZAMKNIĘTEJ świecy ramki z pipeline.prepare."""
    last = df.iloc[-1]
    spread = float(last["ask_c"] - last["bid_c"])
    atr_v = float(last["atr"])
    sig, raw = int(last["signal"]), int(last["signal_raw"])
    lines = [f"Reżim dzienny: {REGIME_PL[last['regime']]} ({regime_text(last, macro)})."]

    verdict, entry, sl, tp, blocked = "CZEKAJ", None, None, None, []
    if sig != 0 and spread > p.max_spread_atr * atr_v:
        blocked.append("spread")
        lines.append(f"Sygnał M15 odrzucony: spread {spread:.2f} przekracza {p.max_spread_atr:.0%} ATR.")
    elif sig != 0:
        verdict = "KUP" if sig == 1 else "SPRZEDAJ"
        entry = float(last["ask_c"] if sig == 1 else last["bid_c"])
        sl = entry - sig * p.sl_atr * atr_v
        tp = entry + sig * p.tp_atr * atr_v
        lines.append("Sygnał M15: powrót RSI z korekty i przecięcie MACD zgodne z reżimem. "
                     f"SL {p.sl_atr} ATR, TP {p.tp_atr} ATR (stosunek zysku do ryzyka 1:{p.tp_atr / p.sl_atr:g}).")
    elif raw != 0:
        lines.append("Sygnał M15 został zablokowany, bo reżim dzienny jest neutralny lub przeciwny.")
    else:
        lines.append("Brak sygnału M15: czekamy na korektę RSI i przecięcie MACD.")

    out = {"time": last["time"].isoformat(), "verdict": verdict, "regime": last["regime"],
           "entry": entry, "sl": sl, "tp": tp, "atr": atr_v, "reasoning": " ".join(lines),
           "status": "OPEN" if verdict in TRADE else "NONE", "signal_raw": raw}
    if blocked:
        out["blocked"] = blocked
    return out
