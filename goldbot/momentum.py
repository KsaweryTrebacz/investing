"""Strategia trendowa D1 (tryb instrumentu "trend_d1"): momentum 120 dni z dźwignią dopasowaną do zmienności.

Badanie: docs/research/2026-10-26-optymalizacja-zloto.md, punkt 10. Pozycja LONG, gdy zamknięcie dnia jest wyżej
niż `lookback` dni handlowych wcześniej, inaczej bez pozycji. Dźwignia = docelowa zmienność roczna / zmienność
z ostatnich `vol_window` dni, nie więcej, niż pozwala depozyt brokera. Przeliczenie raz dziennie po zamknięciu
świecy D1 (17:00 Nowy Jork). Bez stopu: wyjście, gdy momentum spadnie do zera albo niżej; jedynym „stopem”
jest likwidacja przez brokera, więc raport zawsze podaje jej cenę.
"""
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

NY = "America/New_York"
MODE = "trend_d1"
RESEARCH_NOTE = ("Badanie 2008-2024 (docs/research, pkt 10): przy docelowej zmienności 50% kapitał x3,46 przy "
                 "finansowaniu -5%, największy spadek -86%; cel 30%: x3,23, spadek -65%. Sam filtr momentum nie jest "
                 "istotny statystycznie, wynik zależy od trwania trendu wzrostowego złota.")


@dataclass
class TrendParams:
    lookback: int = 120                 # dni handlowe momentum
    vol_window: int = 20                # dni do szacunku zmienności
    target_vol: float = 0.5             # docelowa zmienność roczna (optimum wzrostu w badaniu; 0.3 = mniejsze spadki)
    max_leverage: float | None = None   # dodatkowy limit dźwigni; domyślnie tyle, ile pozwala depozyt brokera
    long_only: bool = True
    rebalance_band: float = 0.1         # zmiana wielkości dopiero przy różnicy większej niż 10% obecnej pozycji


def daily_frame(d1: pd.DataFrame) -> pd.DataFrame:
    """Dzienne ceny środkowe, spread względny; indeks = dzień handlowy (kończący się o 17:00 Nowy Jork)."""
    d = d1.reset_index(drop=True)
    out = pd.DataFrame({k: ((d[f"bid_{k}"] + d[f"ask_{k}"]) / 2).to_numpy() for k in "ohlc"})
    out["spread"] = ((d["ask_c"] - d["bid_c"]) / out["c"]).to_numpy()
    out.index = d["time"].dt.tz_convert(NY).dt.normalize().dt.tz_localize(None) + pd.Timedelta(days=1)
    return out


def positions(day: pd.DataFrame, lookback: int, long_only: bool = True) -> np.ndarray:
    """Kierunek na zamknięciu każdego dnia: +1, gdy cena wyżej niż `lookback` dni temu (SHORT lustrzanie)."""
    s = np.sign(day["c"] / day["c"].shift(lookback) - 1).fillna(0.0)
    return (s.clip(lower=0) if long_only else s).to_numpy()


def vol_leverage(day: pd.DataFrame, target: float, window: int = 20, max_lev: float = 50.0) -> np.ndarray:
    """Dźwignia = docelowa zmienność roczna / zmienność z `window` dni (znana na zamknięciu dnia)."""
    vol = np.log(day["c"]).diff().rolling(window).std() * np.sqrt(252)
    return (target / vol).clip(upper=max_lev).fillna(0.0).to_numpy()


def simulate(day: pd.DataFrame, pos: np.ndarray, lev: np.ndarray, margin_rate: float = 0.02, closeout: float = 0.5,
             long_rate: float = -0.05, short_rate: float = -0.01, max_lev: float | None = None) -> pd.Series:
    """Kapitał na koniec każdego dnia (start 1). pos i lev ustalone na zamknięciu dnia t-1, działają w dniu t.

    Ekspozycja = dźwignia x kapitał, przeliczana codziennie; koszt spreadu od zmiany wielkości; finansowanie
    od całej wartości (środa potrójnie); likwidacja, gdy kapitał < closeout x depozyt (na dziennym dołku
    albo szczycie, przy luce po otwarciu); kapitał nie spada poniżej zera.
    """
    cap = max_lev if max_lev is not None else 1 / margin_rate
    o, h, low, c, spr = (day[k].to_numpy() for k in ("o", "h", "l", "c", "spread"))
    triple = (day.index.weekday == 2)
    eq, units, out = 1.0, 0.0, np.empty(len(day))
    out[0] = eq
    for t in range(1, len(day)):
        if eq <= 1e-6:
            out[t:] = 0.0
            break
        ref = c[t - 1]
        target = pos[t - 1] * min(lev[t - 1], cap) * eq / ref if np.isfinite(lev[t - 1]) else 0.0
        eq -= abs(target - units) * ref * spr[t - 1] / 2
        units = target
        if units == 0.0:
            out[t] = eq
            continue
        side, u = (1, units) if units > 0 else (-1, -units)
        if side == 1:   # eq + u(P - ref) = c*m*u*P
            p_star = (u * ref - eq) / (u * (1 - closeout * margin_rate))
            gap, worst = o[t] <= p_star, low[t] <= p_star
        else:
            p_star = (eq + u * ref) / (u * (1 + closeout * margin_rate))
            gap, worst = o[t] >= p_star, h[t] >= p_star
        if gap or worst:
            fill = o[t] if gap else p_star
            eq = max(0.0, eq + units * (fill - ref) - u * fill * spr[t] / 2)
            units = 0.0
        else:
            rate = long_rate if side == 1 else short_rate
            eq += units * (c[t] - ref) + u * c[t] * rate / 365 * (3 if triple[t] else 1)
            eq = max(eq, 0.0)
        out[t] = eq
    return pd.Series(out, index=day.index)


def leverage_cap(p: TrendParams, margin_rate: float | None) -> float:
    broker = 1 / margin_rate if margin_rate else math.inf
    return min(broker, p.max_leverage or math.inf)


def signal(d1: pd.DataFrame, p: TrendParams, margin_rate: float | None) -> dict:
    """Pozycja docelowa z ostatniej zamkniętej świecy D1: kierunek, dźwignia, momentum, zmienność."""
    day = daily_frame(d1)
    if len(day) < p.lookback + p.vol_window + 1:
        raise ValueError(f"Za mało świec D1: {len(day)} < {p.lookback + p.vol_window + 1}.")
    cap = leverage_cap(p, margin_rate)
    pos = positions(day, p.lookback, p.long_only)
    lev = vol_leverage(day, p.target_vol, p.vol_window, cap if math.isfinite(cap) else 1e9)
    c = day["c"]
    side = int(pos[-1])
    changes = np.flatnonzero(np.diff(pos) != 0)
    runs = np.diff(np.r_[0, changes + 1, len(pos)])
    starts = np.r_[0, changes + 1]
    long_runs = [r for r, s in zip(runs, starts) if pos[s] == 1 and s > p.lookback]
    return {"time": d1["time"].iloc[-1].isoformat(), "close": float(c.iloc[-1]),
            "lookback_close": float(c.iloc[-1 - p.lookback]), "momentum": float(c.iloc[-1] / c.iloc[-1 - p.lookback] - 1),
            "vol": float(np.log(c).diff().iloc[-p.vol_window:].std() * np.sqrt(252)), "side": side,
            "leverage": float(lev[-1]) if side else 0.0, "cap": cap, "target_vol": p.target_vol,
            "lookback": p.lookback, "since_days": int(runs[-1]),
            "avg_long_days": round(float(np.mean(long_runs)), 1) if long_runs else None,
            "spread": float(day["spread"].iloc[-1])}


def recent_backtest(d1: pd.DataFrame, p: TrendParams, margin_rate: float, closeout: float,
                    long_rate: float, short_rate: float) -> dict:
    """Wynik strategii na dostępnej historii D1 (po rozgrzewce): mnożnik kapitału, największy spadek, dni."""
    day = daily_frame(d1)
    cap = leverage_cap(p, margin_rate)
    pos = positions(day, p.lookback, p.long_only)
    lev = vol_leverage(day, p.target_vol, p.vol_window, cap)
    start = p.lookback + p.vol_window
    eq = simulate(day.iloc[start:], pos[start:], lev[start:], margin_rate, closeout, long_rate, short_rate, cap)
    return {"from": str(eq.index[0].date()), "to": str(eq.index[-1].date()), "days": len(eq),
            "wealth_x": round(float(eq.iloc[-1]), 3), "max_dd_%": round(100 * float((eq / eq.cummax() - 1).min()), 1),
            "avg_leverage": round(float(lev[start:][pos[start:] != 0].mean()), 2) if (pos[start:] != 0).any() else 0.0}


def current_units(positions_file: dict | None, instrument: str) -> float | None:
    """Obecna pozycja w instrumencie z pliku pozycji (LONG dodatnio). None, gdy pliku nie ma."""
    if positions_file is None:
        return None
    total = 0.0
    for p in positions_file.get("positions", []):
        if p["instrument"] == instrument:
            sign = 1 if str(p["side"]).upper() in ("LONG", "KUP", "BUY") else -1
            total += sign * float(p["units"])
    return total


def advise(side: int, leverage: float, equity: float, price: float, fx: float, step: float,
           current: float | None, band: float) -> dict:
    """Rada na podstawie pozycji docelowej i obecnej: akcja, werdykt (KUP/SPRZEDAJ/CZEKAJ), zmiana jednostek."""
    raw = leverage * equity / (price * fx) if side else 0.0
    target = side * math.floor(raw / step + 1e-9) * step
    out = {"target_units": target, "current_units": current, "change_units": None}
    if current is None:
        action = ("OTWÓRZ " + ("LONG" if side == 1 else "SHORT")) if target else "BEZ POZYCJI"
        verdict = ("KUP" if side == 1 else "SPRZEDAJ") if target else "CZEKAJ"
        return {**out, "action": action, "verdict": verdict, "current_known": False}
    diff = target - current
    out.update(change_units=diff, current_known=True)
    if target == 0 and current == 0:
        action, verdict = "BEZ POZYCJI", "CZEKAJ"
    elif target == 0:
        action, verdict = "ZAMKNIJ", ("SPRZEDAJ" if current > 0 else "KUP")
    elif current == 0:
        action, verdict = "OTWÓRZ " + ("LONG" if side == 1 else "SHORT"), ("KUP" if side == 1 else "SPRZEDAJ")
    elif np.sign(target) != np.sign(current):
        action, verdict = "ODWRÓĆ", ("KUP" if diff > 0 else "SPRZEDAJ")
    elif abs(diff) <= band * abs(current):
        action, verdict = "UTRZYMAJ", "CZEKAJ"
    else:
        action = "ZWIĘKSZ" if abs(target) > abs(current) else "ZMNIEJSZ"
        verdict = "KUP" if diff > 0 else "SPRZEDAJ"
    return {**out, "action": action, "verdict": verdict}


def validate(d1: pd.DataFrame, p: TrendParams, margin_rate: float, closeout: float, long_rate: float,
             short_rate: float, split: float = 0.5) -> dict:
    """Strategia na historii D1 (po rozgrzewce): całość, dwie połowy (każda ze świeżym rachunkiem), kup i trzymaj."""
    day = daily_frame(d1)
    cap = leverage_cap(p, margin_rate)
    pos = positions(day, p.lookback, p.long_only)
    lev = vol_leverage(day, p.target_vol, p.vol_window, cap)
    start = p.lookback + p.vol_window
    if len(day) - start < 20:
        raise ValueError(f"Za mało świec D1 po rozgrzewce ({len(day) - start}).")
    mid = start + int((len(day) - start) * split)

    def stats(a: int, b: int | None, ps=pos, ls=lev) -> dict:
        eq = simulate(day.iloc[a:b], ps[a:b], ls[a:b], margin_rate, closeout, long_rate, short_rate, cap)
        years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
        return {"od": str(eq.index[0].date()), "do": str(eq.index[-1].date()), "kapital_x": round(float(eq.iloc[-1]), 3),
                "cagr_%": round(100 * (max(float(eq.iloc[-1]), 1e-12) ** (1 / years) - 1), 1),
                "max_spadek_%": round(100 * float((eq / eq.cummax() - 1).min()), 1)}

    held = pos[start:] != 0
    return {"calosc": stats(start, None), "pierwsza_polowa": stats(start, mid), "druga_polowa": stats(mid - 1, None),
            "kup_i_trzymaj_1x": stats(start, None, np.ones(len(day)), np.ones(len(day))),
            "zmiany_kierunku": int((np.diff(pos[start:]) != 0).sum()), "dni_w_pozycji_%": round(100 * float(held.mean()), 1),
            "srednia_dzwignia": round(float(lev[start:][held].mean()), 2) if held.any() else 0.0}
