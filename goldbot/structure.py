"""Struktura rynku: szczyty i dołki, wsparcia i opory, wybicia i retesty (bez zaglądania w przyszłość)."""
import pandas as pd

STRUCT_UP, STRUCT_DOWN, STRUCT_MIXED, STRUCT_NA = "wzrostowa", "spadkowa", "mieszana", "za mało danych"


def swing_points(high: pd.Series, low: pd.Series, n: int = 3):
    """Szczyty i dołki fraktalne: high (low) najwyższy (najniższy) w oknie ±n świec.

    Punkt jest potwierdzony dopiero n świec później, więc na ostatnich n świecach go nie ma.
    """
    w = 2 * n + 1
    hi = high == high.rolling(w, center=True).max()
    lo = low == low.rolling(w, center=True).min()
    return hi.fillna(False).astype(bool), lo.fillna(False).astype(bool)


def classify(highs: pd.Series, lows: pd.Series) -> str:
    """Wyższe szczyty i dołki = wzrostowa, niższe = spadkowa, inaczej mieszana."""
    if len(highs) < 2 or len(lows) < 2:
        return STRUCT_NA
    h1, h2, l1, l2 = highs.iloc[-2], highs.iloc[-1], lows.iloc[-2], lows.iloc[-1]
    if h2 > h1 and l2 > l1:
        return STRUCT_UP
    if h2 < h1 and l2 < l1:
        return STRUCT_DOWN
    return STRUCT_MIXED


def _last_break(close: pd.Series, levels: pd.Series, n: int, sign: int):
    """Ostatnie zamknięcie za poziomem swing (sign=+1: ponad szczytem, -1: pod dołkiem): (indeks, poziom)."""
    best = None
    for i, level in levels.items():
        after = close.loc[i + n + 1:]
        crossed = sign * (after - level) > 0
        if crossed.any():
            b = crossed.idxmax()
            if best is None or b > best[0]:
                best = (b, level)
    return best


def analyze(d: pd.DataFrame, atr: float, n: int = 3, lookback: int = 300, recent: int = 20,
            retest_atr: float = 0.25) -> dict:
    """d: kolumny mid_h, mid_l, mid_c. Ocena na ostatnich `lookback` świecach.

    Wybicie liczy się, jeśli nastąpiło w ostatnich `recent` świecach. Retest: po wybiciu cena wróciła
    do poziomu na `retest_atr` ATR i zamknęła się po właściwej stronie.
    """
    d = d.tail(lookback).reset_index(drop=True)
    hi, lo = swing_points(d["mid_h"], d["mid_l"], n)
    highs, lows = d["mid_h"][hi], d["mid_l"][lo]
    price, last = float(d["mid_c"].iloc[-1]), len(d) - 1
    above, below = highs[highs > price], lows[lows < price]
    out = {"structure": classify(highs, lows), "price": price,
           "resistance": float(above.min()) if len(above) else None,
           "support": float(below.max()) if len(below) else None,
           "last_high": float(highs.iloc[-1]) if len(highs) else None,
           "last_low": float(lows.iloc[-1]) if len(lows) else None, "breakout": None}

    events = []
    for sign, levels in ((1, highs), (-1, lows)):
        br = _last_break(d["mid_c"], levels, n, sign)
        if br and last - br[0] <= recent:
            b, level = br
            after = d.loc[b + 1:]
            touch = after["mid_l"] <= level + retest_atr * atr if sign == 1 else after["mid_h"] >= level - retest_atr * atr
            held = sign * (after["mid_c"] - level) > 0
            events.append({"direction": sign, "level": float(level), "bars_ago": int(last - b),
                           "retest": bool((touch & held).any()), "holding": bool(sign * (price - level) > 0)})
    if events:
        out["breakout"] = min(events, key=lambda e: e["bars_ago"])
    return out
