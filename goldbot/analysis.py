"""Analiza techniczna do raportu: EMA 20/50/200 na D1 i M15, RSI, MACD, ATR, wolumen, VWAP, struktura.

Nie zmienia sygnału ze strategy.py. Daje fakty oraz listę potwierdzeń i sprzeczności dla kierunku.
"""
import pandas as pd

import structure as st
from indicators import atr, ema, volume_ratio, vwap
from regime import REGIME_BUY, REGIME_PL, REGIME_SELL

ORDER_UP, ORDER_DOWN, ORDER_MIXED = "wzrostowe", "spadkowe", "mieszane"
DIRECTION_PL = {1: "LONG (kupno)", -1: "SHORT (sprzedaż)", 0: "brak przewagi"}


def _num(x):
    return None if x is None or pd.isna(x) else float(x)


def with_mid(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(**{f"mid_{k}": (df[f"bid_{k}"] + df[f"ask_{k}"]) / 2 for k in "ohlc"})


def ema_stack(close: pd.Series) -> dict:
    """Ostatnie EMA 20/50/200 i ich ułożenie. Przy historii krótszej niż 200 świec ułożenie = None."""
    e = {n: _num(ema(close, n).iloc[-1]) for n in (20, 50, 200)}
    order = None
    if len(close) >= 200:
        order = ORDER_UP if e[20] > e[50] > e[200] else ORDER_DOWN if e[20] < e[50] < e[200] else ORDER_MIXED
    return {"ema20": e[20], "ema50": e[50], "ema200": e[200], "order": order}


def market_facts(df: pd.DataFrame, d1: pd.DataFrame) -> dict:
    """df: wynik pipeline.prepare (M15 z sygnałami i reżimem), d1: zamknięte świece dzienne."""
    last = df.iloc[-1]
    d1m = with_mid(d1.reset_index(drop=True))
    d1_atr = _num(atr(d1m["mid_h"], d1m["mid_l"], d1m["mid_c"]).iloc[-1])
    vr = volume_ratio(df["volume"]) if "volume" in df else pd.Series(float("nan"), index=df.index)
    day_ago = df[df["time"] <= last["time"] - pd.Timedelta(hours=24)]
    price = float(last["mid_c"])
    return {
        "time": last["time"].isoformat(), "price": price, "spread": float(last["ask_c"] - last["bid_c"]),
        "regime": last["regime"], "signal": int(last["signal"]), "signal_raw": int(last["signal_raw"]),
        "components": {k: _num(last[k]) for k in ("trend", "dollar", "yields")},
        "change_24h": price - float(day_ago["mid_c"].iloc[-1]) if len(day_ago) else None,
        "change_since_d1": price - float(d1m["mid_c"].iloc[-1]),
        "d1_close_time": d1m["time"].iloc[-1].isoformat(),
        "d1": {**ema_stack(d1m["mid_c"]), "atr": d1_atr,
               "structure": st.analyze(d1m, d1_atr or 0.0, lookback=250)},
        "m15": {**ema_stack(df["mid_c"]), "rsi": _num(last["rsi"]), "macd_hist": _num(last["hist"]),
                "atr": _num(last["atr"]), "vwap": _num(vwap(df).iloc[-1]), "volume_ratio": _num(vr.iloc[-1]),
                "structure": st.analyze(df, float(last["atr"]))},
    }


def direction(f: dict) -> int:
    """Kierunek do oceny: surowy sygnał M15, inaczej reżim, inaczej trend D1, inaczej 0."""
    if f["signal_raw"]:
        return f["signal_raw"]
    if f["regime"] in (REGIME_BUY, REGIME_SELL):
        return 1 if f["regime"] == REGIME_BUY else -1
    t = f["components"]["trend"]
    return int(t) if t else 0


def _agree(x, d):
    return None if x is None or d == 0 else x * d > 0


def _ordered(value, d, up, down):
    return None if value is None or d == 0 or value not in (up, down, ORDER_MIXED, st.STRUCT_MIXED) \
        else value == (up if d == 1 else down)


def _comp(v, up, down, flat="boczny"):
    return "brak danych" if v is None else up if v > 0 else down if v < 0 else flat


def checks(f: dict, d: int, macro: bool = True, tp: float | None = None) -> list:
    """Potwierdzenia (ok=True), sprzeczności (ok=False) i fakty bez oceny (ok=None) dla kierunku d."""
    rows = []

    def add(name, value, ok):
        rows.append({"name": name, "value": value, "ok": ok})

    c, d1, m = f["components"], f["d1"], f["m15"]
    want = {1: REGIME_BUY, -1: REGIME_SELL}.get(d)
    add("Reżim dzienny", REGIME_PL[f["regime"]], None if d == 0 else f["regime"] == want)
    add("Trend D1 (EMA 50 vs 200)", _comp(c["trend"], "wzrostowy", "spadkowy"), _agree(c["trend"], d))
    if macro:
        add("Dolar (szeroki indeks)", _comp(c["dollar"], "słabnie", "umacnia się"), _agree(c["dollar"], d))
        add("Realne rentowności 10Y", _comp(c["yields"], "spadają", "rosną", "boczne"), _agree(c["yields"], d))
    for label, x in (("D1", d1), ("M15", m)):
        if x["order"] is None:
            add(f"EMA 20/50/200 {label}", "za krótka historia", None)
        else:
            add(f"EMA 20/50/200 {label}", f"{x['order']}: {x['ema20']:.2f} / {x['ema50']:.2f} / {x['ema200']:.2f}",
                _ordered(x["order"], d, ORDER_UP, ORDER_DOWN))
        add(f"Struktura szczytów i dołków {label}", x["structure"]["structure"],
            _ordered(x["structure"]["structure"], d, st.STRUCT_UP, st.STRUCT_DOWN))
    add("Cena M15 vs EMA 200", f"{f['price']:.2f} vs {m['ema200']:.2f}", _agree(f["price"] - m["ema200"], d))

    rsi = m["rsi"]
    note = " (wykupienie)" if rsi is not None and rsi > 70 else " (wyprzedanie)" if rsi is not None and rsi < 30 else ""
    lo, hi = (40, 70) if d == 1 else (30, 60)
    add("RSI 14 (M15)", "brak danych" if rsi is None else f"{rsi:.1f}{note}",
        None if rsi is None or d == 0 else lo <= rsi <= hi)
    add("Histogram MACD (M15)", "brak danych" if m["macd_hist"] is None else f"{m['macd_hist']:+.3f}",
        _agree(m["macd_hist"], d))
    vr = m["volume_ratio"]
    add("Wolumen tickowy (M15)", "brak danych" if vr is None else f"{vr:.2f}× średniej z 20 świec",
        None if vr is None or d == 0 else vr >= 1.0)
    add("Cena vs VWAP sesji UTC", "brak danych" if m["vwap"] is None else f"VWAP {m['vwap']:.2f}",
        None if m["vwap"] is None else _agree(f["price"] - m["vwap"], d))

    b = m["structure"]["breakout"]
    if b is None:
        add("Wybicie i retest (M15)", "brak świeżego wybicia", None)
    else:
        text = (f"wybicie {'w górę ponad' if b['direction'] == 1 else 'w dół pod'} {b['level']:.2f} "
                f"{b['bars_ago']} świec temu" + (", retest utrzymany" if b["retest"] else "")
                + ("" if b["holding"] else ", cena wróciła za poziom"))
        add("Wybicie i retest (M15)", text, None if d == 0 else b["direction"] == d and b["holding"])

    s = m["structure"]
    if tp is not None and d != 0:
        level = s["resistance"] if d == 1 else s["support"]
        blocked = level is not None and (level < tp if d == 1 else level > tp)
        name = "opór" if d == 1 else "wsparcie"
        add("Przestrzeń do TP", f"{name} M15 {level:.2f} przed TP {tp:.2f}" if blocked
            else f"brak poziomu M15 przed TP {tp:.2f}", not blocked)
    else:
        fmt = lambda x: "brak" if x is None else f"{x:.2f}"  # noqa: E731
        add("Najbliższe poziomy M15", f"wsparcie {fmt(s['support'])}, opór {fmt(s['resistance'])}", None)
    return rows


def strength(rows: list) -> dict:
    known = [r for r in rows if r["ok"] is not None]
    ok = sum(1 for r in known if r["ok"])
    return {"confirm": ok, "known": len(known), "text": f"{ok} z {len(known)} sprawdzonych warunków zgodnych z kierunkiem"}
