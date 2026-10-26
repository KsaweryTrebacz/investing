"""Inne rodziny strategii na złocie, oceniane bez ograniczeń ryzyka: pozycja 1x wartości nominalnej, bez stopów.

Każda strategia daje dzienną serię zwrotów netto (spread z cen bid/ask, finansowanie za rollover).
Ocena: walk-forward (wybór wariantu na `train_years` latach wstecz, test na kolejnym roku) i porównanie
z trzymaniem złota. Rodziny:
- sesja: pozycja od godziny h1 do h2 UTC każdego dnia (efekt sesji azjatyckiej i londyńskiej),
- momentum: znak zmiany ceny z L dni (LONG/SHORT albo LONG/bez pozycji),
- średnia: cena nad/pod średnią z N dni,
- powrót do średniej: RSI(2) dzienny z wyjściem nad/pod średnią 5-dniową,
- wybicie: zakres 01-07 UTC, wejście po przebiciu w sesji Londyn/Nowy Jork, wyjście o 20:00 UTC.

Uruchomienie z katalogu goldbot:
  python -m research.edges --broker dane/XAU_15m_data.csv --dukascopy dane/dukascopy_m15 --out wyniki
"""
import argparse
import json
import math
import os

import numpy as np
import pandas as pd

from indicators import rsi
from research.datasets import daily_from_m15, hourly_spread_profile, load_broker_m15, load_dukascopy

LONG_RATE, SHORT_RATE = -0.05, -0.01   # finansowanie roczne (ujemne = koszt), jak w research.study
NY = "America/New_York"
ROLLOVER_HOURS = {20, 21, 22}          # godziny UTC z przerwą dzienną; w danych jednocenowych pomijane


def hourly(m15: pd.DataFrame) -> pd.DataFrame:
    """Ceny otwarcia bid/ask każdej pełnej godziny UTC (pierwszy kwadrans godziny)."""
    d = m15[m15["time"].dt.minute == 0].set_index("time")[["bid_o", "ask_o"]]
    return d[~d.index.duplicated()]


def _rollover_utc_hour(dates: pd.DatetimeIndex) -> np.ndarray:
    """Godzina UTC rolloveru (17:00 Nowy Jork) dla każdego dnia: 21 latem, 22 zimą."""
    ny = (dates + pd.Timedelta(hours=17)).tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward")
    return ny.tz_convert("UTC").hour.to_numpy()


def session_returns(h: pd.DataFrame, h1: int, h2: int, side: int) -> pd.Series:
    """Dzienne zwroty netto pozycji od h1 do h2 UTC (h2 < h1: wyjście następnego dnia). Indeks: dzień wejścia."""
    t = h.index
    entry = h[t.hour == h1]
    exit_t = entry.index.normalize() + pd.Timedelta(hours=h2) + (pd.Timedelta(days=1) if h2 <= h1 else pd.Timedelta(0))
    ex = h.reindex(exit_t)
    e_bid, e_ask = entry["bid_o"].to_numpy(), entry["ask_o"].to_numpy()
    x_bid, x_ask = ex["bid_o"].to_numpy(), ex["ask_o"].to_numpy()
    mid = (e_bid + e_ask) / 2
    gross = (x_bid - e_ask) / mid if side == 1 else (e_bid - x_ask) / mid
    days = entry.index.normalize().tz_localize(None)
    roll = _rollover_utc_hour(pd.DatetimeIndex(days))
    crosses = (roll > h1) & (roll <= h2) if h2 > h1 else (roll > h1) | (roll <= h2)
    ny_wd = pd.DatetimeIndex(days).weekday.to_numpy()
    fin_days = np.where(crosses, np.where(ny_wd == 2, 3, 1), 0)
    fin = fin_days * (LONG_RATE if side == 1 else SHORT_RATE) / 365
    r = pd.Series(gross + fin, index=pd.DatetimeIndex(days))
    return r[np.isfinite(r.to_numpy())]


def _daily_mid(d1: pd.DataFrame) -> pd.Series:
    return pd.Series(((d1["bid_c"] + d1["ask_c"]) / 2).to_numpy(), index=d1["time"].dt.tz_convert(NY).dt.normalize()
                     .dt.tz_localize(None) + pd.Timedelta(days=1))  # dzień handlowy (17:00 NY dnia poprzedniego)


def position_returns(d1: pd.DataFrame, pos: pd.Series) -> pd.Series:
    """Dzienne zwroty netto: pozycja z zamknięcia dnia t na dzień t+1, koszt spreadu przy zmianie, finansowanie."""
    c = _daily_mid(d1)
    spread = pd.Series(((d1["ask_c"] - d1["bid_c"]) / ((d1["ask_c"] + d1["bid_c"]) / 2)).to_numpy(), index=c.index)
    p = pos.reindex(c.index).fillna(0).shift(1).fillna(0)  # decyzja na zamknięciu, wynik następnego dnia
    ret = c.pct_change().fillna(0)
    trade_cost = p.diff().abs().fillna(p.abs()) * spread.shift(1).fillna(spread.median()) / 2
    days = pd.Series(np.where(c.index.weekday == 2, 3, 1), index=c.index)  # dzień kończący się rolloverem w środę: x3
    fin = np.where(p > 0, LONG_RATE, np.where(p < 0, SHORT_RATE, 0.0)) * p.abs() * days / 365
    return (p * ret - trade_cost + fin).iloc[1:]


def momentum_pos(d1, lookback: int, long_only: bool) -> pd.Series:
    c = _daily_mid(d1)
    s = np.sign(c / c.shift(lookback) - 1)
    return s.clip(lower=0) if long_only else s


def ma_pos(d1, n: int, long_only: bool) -> pd.Series:
    c = _daily_mid(d1)
    s = np.sign(c - c.rolling(n).mean())
    return s.clip(lower=0) if long_only else s


def rsi2_pos(d1, level: float, long_only: bool) -> pd.Series:
    """Wejście LONG przy RSI(2) < level, wyjście gdy cena > średnia 5-dniowa (SHORT lustrzanie)."""
    c = _daily_mid(d1)
    r, ma5 = rsi(c, 2).to_numpy(), c.rolling(5).mean().to_numpy()
    cv, pos, cur = c.to_numpy(), np.zeros(len(c)), 0
    for i in range(len(c)):
        if cur == 1 and cv[i] > ma5[i] or cur == -1 and cv[i] < ma5[i]:
            cur = 0
        if cur == 0:
            cur = 1 if r[i] < level else (-1 if (r[i] > 100 - level and not long_only) else 0)
        pos[i] = cur
    return pd.Series(pos, index=c.index)


def breakout_returns(m15: pd.DataFrame, side_mode: str = "both") -> pd.Series:
    """Zakres 01:00-07:00 UTC; pierwsze przebicie w 07:00-20:00 otwiera pozycję po cenie przebicia
    (+ spread), wyjście o 20:00 UTC po bid/ask. Bez stopu."""
    d = m15.set_index("time")
    hour = d.index.hour
    rng = d[(hour >= 1) & (hour < 7)]
    hi = ((rng["bid_h"] + rng["ask_h"]) / 2).groupby(rng.index.normalize()).max()
    lo = ((rng["bid_l"] + rng["ask_l"]) / 2).groupby(rng.index.normalize()).min()
    sess = d[(hour >= 7) & (hour < 20)]
    out = {}
    for dd, g in sess.groupby(sess.index.normalize()):
        if dd not in hi.index or len(g) < 40:
            continue
        mh, ml = (g["bid_h"] + g["ask_h"]) / 2, (g["bid_l"] + g["ask_l"]) / 2
        up = np.flatnonzero(mh.to_numpy() > hi[dd])
        dn = np.flatnonzero(ml.to_numpy() < lo[dd])
        first_up = up[0] if len(up) else None
        first_dn = dn[0] if len(dn) else None
        if side_mode == "long":
            first_dn = None
        if first_up is None and first_dn is None:
            continue
        side = 1 if first_dn is None or (first_up is not None and first_up <= first_dn) else -1
        level = hi[dd] if side == 1 else lo[dd]
        half = float((g["ask_c"] - g["bid_c"]).iloc[0]) / 2
        last = g.iloc[-1]
        exit_px = last["bid_c"] if side == 1 else last["ask_c"]
        out[dd.tz_localize(None)] = (side * (exit_px - level) - half) / level
    return pd.Series(out).sort_index()


def summarize(r: pd.Series) -> dict:
    """Wynik serii dziennych zwrotów przy pozycji 1x: łączny i roczny zwrot, t, dni na plusie, największy spadek."""
    r = r.dropna()
    if len(r) < 2:
        return {"days": len(r)}
    eq = (1 + r).cumprod()
    years = max((r.index[-1] - r.index[0]).days / 365.25, 1e-9)
    yr = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    return {"days": int((r != 0).sum()), "total_%": round(100 * (eq.iloc[-1] - 1), 1),
            "cagr_%": round(100 * (eq.iloc[-1] ** (1 / years) - 1), 2),
            "t_stat": round(float(r.mean() / r.std(ddof=1) * math.sqrt(len(r))), 2),
            "years_positive": f"{int((yr > 0).sum())}/{len(yr)}",
            "max_dd_%": round(100 * float((eq / eq.cummax() - 1).min()), 1)}


def walk_forward(candidates: dict, first: int, last: int, train_years: int = 3) -> tuple[pd.Series, list]:
    """Co rok wariant o najwyższym średnim zwrocie z `train_years` lat wstecz; zwraca sklejone zwroty poza próbą."""
    parts, chosen = [], []
    for y in range(first, last + 1):
        best, best_m = None, 0.0
        for name, r in candidates.items():
            tr = r[(r.index.year >= y - train_years) & (r.index.year < y)]
            if len(tr) > 100 and tr.mean() > best_m:
                best, best_m = name, tr.mean()
        chosen.append({"year": y, "variant": best, "train_mean_bp": round(best_m * 1e4, 2) if best else None})
        if best:
            parts.append(candidates[best][candidates[best].index.year == y])
    return (pd.concat(parts) if parts else pd.Series(dtype=float)), chosen


def candidates_for(m15: pd.DataFrame, d1: pd.DataFrame, real_spread: bool) -> dict:
    """Wszystkie warianty rodzin strategii jako dzienne serie zwrotów."""
    c = {}
    h = hourly(m15)
    hours = [x for x in range(24) if real_spread or x not in ROLLOVER_HOURS]
    hours = [x for x in hours if (h.index.hour == x).any()]
    for h1 in hours:
        for h2 in hours:
            span = (h2 - h1) % 24
            if 1 <= span <= 12:
                for side in (1, -1):
                    c[f"sesja {h1:02d}-{h2:02d} {'LONG' if side == 1 else 'SHORT'}"] = session_returns(h, h1, h2, side)
    for lo in (True, False):
        tag = "LONG/flat" if lo else "LONG/SHORT"
        for L in (5, 10, 20, 60, 120, 250):
            c[f"momentum {L}d {tag}"] = position_returns(d1, momentum_pos(d1, L, lo))
        for n in (20, 50, 100, 200):
            c[f"średnia {n}d {tag}"] = position_returns(d1, ma_pos(d1, n, lo))
        for lvl in (5, 10, 20):
            c[f"RSI2<{lvl} {tag}"] = position_returns(d1, rsi2_pos(d1, lvl, lo))
    c["wybicie zakresu azjatyckiego LONG/SHORT"] = breakout_returns(m15)
    c["wybicie zakresu azjatyckiego LONG"] = breakout_returns(m15, "long")
    return c


def family(name: str) -> str:
    return name.split(" ")[0]


def evaluate(m15, d1, first: int, last: int, real_spread: bool, train_years: int = 3) -> dict:
    cands = candidates_for(m15, d1, real_spread)
    bh = position_returns(d1, pd.Series(1.0, index=_daily_mid(d1).index))
    span = lambda r: r[(r.index.year >= first) & (r.index.year <= last)]  # noqa: E731
    out = {"variants": len(cands), "buy_and_hold": summarize(span(bh))}
    oos, chosen = walk_forward(cands, first, last, train_years)
    out["walk_forward_all"] = {"oos": summarize(oos), "chosen": chosen}
    for fam in sorted({family(n) for n in cands}):
        sub = {n: r for n, r in cands.items() if family(n) == fam}
        o, ch = walk_forward(sub, first, last, train_years)
        out[f"walk_forward_{fam}"] = {"variants": len(sub), "oos": summarize(o), "chosen": [c["variant"] for c in ch]}
    full = {n: summarize(span(r)) for n, r in cands.items()}
    out["top_full_period"] = dict(sorted(full.items(), key=lambda kv: -kv[1].get("cagr_%", -1e9))[:15])
    out["_series"] = {"oos": oos, "cands": cands}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", required=True)
    ap.add_argument("--dukascopy", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    duk = load_dukascopy(args.dukascopy)
    m15 = load_broker_m15(args.broker, hourly_spread_profile(duk))
    report = {"broker_2008_2024": evaluate(m15, daily_from_m15(m15), 2008, 2024, real_spread=False),
              "dukascopy_2015_2018": evaluate(duk, daily_from_m15(duk), 2015, 2018, real_spread=True)}
    # wariant wybrany na brokerze 2021-2023 sprawdzony na niezależnych danych Dukascopy (te same godziny)
    b = report["broker_2008_2024"]["_series"]["cands"]
    d = report["dukascopy_2015_2018"]["_series"]["cands"]
    report["cross_check_dukascopy_2011_2018"] = {n: summarize(d[n]) for n in sorted(
        b, key=lambda n: -b[n][(b[n].index.year >= 2021) & (b[n].index.year <= 2023)].mean())[:10] if n in d}
    for k in ("broker_2008_2024", "dukascopy_2015_2018"):
        report[k].pop("_series")
    with open(os.path.join(args.out, "edges.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    print(json.dumps(report, ensure_ascii=False, indent=1, default=str)[:30000])


if __name__ == "__main__":
    main()
