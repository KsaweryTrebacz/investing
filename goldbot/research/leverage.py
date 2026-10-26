"""Strategie na złocie przez CFD z dźwignią: symulacja rachunku z depozytem i likwidacją przez brokera.

Pozycja otwierana jest za `lev` x kapitał (wartość nominalna), depozyt = wartość x `margin_rate`
(1:50 -> 0,02). Broker zamyka pozycję, gdy kapitał spadnie poniżej `closeout` x depozyt
(50% jak w zasadach ESMA dla klientów detalicznych); sprawdzane na najgorszej cenie w kroku
(dzienny dołek/szczyt albo najgorsza cena w czasie transakcji), przy luce wykonanie po otwarciu.
Kapitał nie spada poniżej zera (ochrona przed ujemnym saldem). Finansowanie liczone od całej
wartości pozycji. Po likwidacji strategia wchodzi ponownie pozostałym kapitałem.

Uruchomienie z katalogu goldbot:
  python -m research.leverage --broker dane/XAU_15m_data.csv --dukascopy dane/dukascopy_m15 --out wyniki
"""
import argparse
import json
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

import backtest
from pipeline import prepare
from research import edges as E
from research.datasets import daily_from_m15, hourly_spread_profile, load_broker_m15, load_dukascopy
from strategy import Params

NY = "America/New_York"
LEVERAGES = (1, 2, 5, 10, 20, 50)


@dataclass
class Step:
    """Odcinek z pozycją: start (nowe wejście) albo kontynuacja poprzedniego kroku."""
    time: pd.Timestamp
    side: int
    new: bool          # True: otwarcie pozycji na początku kroku (koszt spreadu, nowa wielkość)
    open_mid: float    # cena odniesienia na początku kroku (wejście albo poprzednie zamknięcie)
    gap_mid: float     # pierwsza cena kroku (luka względem odniesienia)
    worst: float       # najgorsza cena w kroku dla pozycji (dołek dla LONG, szczyt dla SHORT)
    close_mid: float
    spread: float      # spread względny przy wejściu/wyjściu
    fin_days: int      # dni finansowania w kroku
    last: bool         # True: pozycja zamykana na końcu kroku


def simulate(steps: list, lev: float, margin_rate: float = 0.02, closeout: float = 0.5,
             long_rate: float = -0.05, short_rate: float = -0.01, start: float = 1.0) -> dict:
    """Kapitał po każdym kroku; liczba likwidacji; czy rachunek został wyzerowany (< 1% startu)."""
    eq, units, ref, side = start, 0.0, None, 0
    curve, times, stopouts, ruined_at = [], [], 0, None
    for s in steps:
        if eq <= start * 0.01:
            ruined_at = ruined_at or s.time
            curve.append(eq)
            times.append(s.time)
            continue
        if s.new or units == 0.0:
            side = s.side
            units = lev * eq / s.open_mid
            eq -= units * s.open_mid * s.spread / 2          # połowa spreadu przy wejściu
            ref = s.open_mid
        # likwidacja: kapitał przy cenie P spada do closeout x depozyt
        if side == 1:   # eq + u(P - ref) = c*m*u*P
            p_star = (units * ref - eq) / (units * (1 - closeout * margin_rate))
        else:           # eq - u(P - ref) = c*m*u*P
            p_star = (eq + units * ref) / (units * (1 + closeout * margin_rate))
        hit_gap = side * (s.gap_mid - p_star) <= 0
        hit = hit_gap or side * (s.worst - p_star) <= 0
        if hit:
            fill = s.gap_mid if hit_gap else p_star
            eq = max(0.0, eq + side * units * (fill - ref) - units * fill * s.spread / 2)
            units, stopouts = 0.0, stopouts + 1
        else:
            eq += side * units * (s.close_mid - ref)
            rate = long_rate if side == 1 else short_rate
            eq += units * s.close_mid * rate / 365 * s.fin_days
            ref = s.close_mid
            if s.last:
                eq -= units * s.close_mid * s.spread / 2       # połowa spreadu przy wyjściu
                units = 0.0
            eq = max(eq, 0.0)
        curve.append(eq)
        times.append(s.time)
    c = pd.Series(curve, index=pd.DatetimeIndex(times))
    return {"curve": c, "stopouts": stopouts, "ruined_at": ruined_at}


def _rel_spread(row) -> float:
    return float((row["ask_c"] - row["bid_c"]) / ((row["ask_c"] + row["bid_c"]) / 2))


def daily_steps(d1: pd.DataFrame, pos: pd.Series) -> list:
    """Kroki dzienne dla pozycji wyznaczanej na zamknięciu dnia (stosowanej od następnego dnia)."""
    d = d1.reset_index(drop=True)
    mid = {k: ((d[f"bid_{k}"] + d[f"ask_{k}"]) / 2).to_numpy() for k in "ohlc"}
    label = d["time"].dt.tz_convert(NY).dt.normalize().dt.tz_localize(None) + pd.Timedelta(days=1)
    p = pos.reindex(label.values).fillna(0).to_numpy()
    spread = ((d["ask_c"] - d["bid_c"]) / ((d["ask_c"] + d["bid_c"]) / 2)).to_numpy()
    wd = label.dt.weekday.to_numpy()
    steps, prev = [], 0
    for i in range(1, len(d)):
        side = int(p[i - 1])                               # decyzja z zamknięcia poprzedniego dnia
        if side == 0:
            prev = 0
            continue
        nxt = int(p[i]) if i + 1 < len(d) else 0
        steps.append(Step(time=d["time"].iloc[i], side=side, new=side != prev, open_mid=mid["c"][i - 1],
                          gap_mid=mid["o"][i], worst=mid["l"][i] if side == 1 else mid["h"][i], close_mid=mid["c"][i],
                          spread=spread[i - 1], fin_days=3 if wd[i] == 2 else 1, last=nxt != side))
        prev = side
    return steps


def session_steps(m15: pd.DataFrame, h1: int, h2: int, side: int) -> list:
    """Jeden krok na dzień: wejście o h1, wyjście o h2 UTC (h1 < h2, bez przechodzenia przez rollover)."""
    d = m15.assign(day=m15["time"].dt.normalize(), hour=m15["time"].dt.hour)
    s = d[(d["hour"] >= h1) & (d["hour"] < h2)]
    steps = []
    for day, g in s.groupby("day"):
        if g["hour"].iloc[0] != h1 or g["hour"].iloc[-1] != h2 - 1:
            continue
        o = (g["bid_o"].iloc[0] + g["ask_o"].iloc[0]) / 2
        worst = ((g["bid_l"] + g["ask_l"]) / 2).min() if side == 1 else ((g["bid_h"] + g["ask_h"]) / 2).max()
        c = (g["bid_c"].iloc[-1] + g["ask_c"].iloc[-1]) / 2
        steps.append(Step(time=g["time"].iloc[-1], side=side, new=True, open_mid=o, gap_mid=o, worst=worst,
                          close_mid=c, spread=_rel_spread(g.iloc[0]), fin_days=0, last=True))
    return steps


def m15_strategy_steps(m15: pd.DataFrame, d1: pd.DataFrame, p: Params = Params()) -> list:
    """Transakcje strategii doradcy (SL/TP, wygaśnięcie 48 h) jako kroki z najgorszą ceną w czasie transakcji."""
    df = prepare(m15, d1, p=p, macro=False)
    t, _ = backtest.run(df, p, costs=None, expire_hours=48)
    idx = pd.DatetimeIndex(df["time"])
    mid_l = ((df["bid_l"] + df["ask_l"]) / 2).to_numpy()
    mid_h = ((df["bid_h"] + df["ask_h"]) / 2).to_numpy()
    steps = []
    for tr in t.itertuples():
        j, k = idx.get_loc(tr.entry_time), idx.get_loc(tr.exit_time)
        side = 1 if tr.side == "LONG" else -1
        worst = mid_l[j:k + 1].min() if side == 1 else mid_h[j:k + 1].max()
        sp = _rel_spread(df.iloc[j])
        entry_mid, exit_mid = tr.entry - side * tr.entry * sp / 2, tr.exit + side * tr.exit * sp / 2
        days = int((tr.exit_time - tr.entry_time).total_seconds() // 86400)
        steps.append(Step(time=tr.exit_time, side=side, new=True, open_mid=entry_mid, gap_mid=entry_mid,
                          worst=worst, close_mid=exit_mid, spread=sp, fin_days=days, last=True))
    return steps


def outcome(res: dict, start, end) -> dict:
    c = res["curve"]
    c = c[(c.index >= pd.Timestamp(start, tz="UTC")) & (c.index < pd.Timestamp(end, tz="UTC"))]
    if c.empty:
        return {}
    years = max((c.index[-1] - c.index[0]).days / 365.25, 1e-9)
    final = float(c.iloc[-1])
    return {"final_x": round(final, 3), "cagr_%": round(100 * (max(final, 1e-12) ** (1 / years) - 1), 1),
            "max_dd_%": round(100 * float((c / c.cummax().clip(lower=1e-12) - 1).min()), 1),
            "stopouts": res["stopouts"], "ruined": str(res["ruined_at"])[:10] if res["ruined_at"] else None}


def windows(steps: list, lev: float, months: int = 4, first: int = 2008, last: int = 2024) -> dict:
    """Okna `months` miesięcy zaczynane co miesiąc: jaki odsetek kończy się stratą, -50% i wyzerowaniem."""
    finals, liquidated = [], 0
    times = np.array([s.time.value for s in steps])
    for start in pd.date_range(f"{first}-01-01", f"{last}-12-01", freq="MS", tz="UTC"):
        end = start + pd.DateOffset(months=months)
        sel = [s for s, t in zip(steps, times) if start.value <= t < end.value]
        if not sel:
            continue
        sel[0] = Step(**{**sel[0].__dict__, "new": True})
        r = simulate(sel, lev)
        finals.append(float(r["curve"].iloc[-1]))
        liquidated += r["stopouts"] > 0
    f = np.array(finals)
    return {"windows": len(f), "median_%": round(100 * float(np.median(f) - 1), 1),
            "P(strata)_%": round(100 * float((f < 1).mean()), 1), "P(-50%)_%": round(100 * float((f <= 0.5).mean()), 1),
            "P(wyzerowanie)_%": round(100 * float((f <= 0.01).mean()), 1),
            "P(likwidacja)_%": round(100 * liquidated / len(f), 1), "P(+80%)_%": round(100 * float((f >= 1.8).mean()), 1),
            "best_%": round(100 * float(f.max() - 1), 1)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", required=True)
    ap.add_argument("--dukascopy", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--margin-rate", type=float, default=0.02, help="1:50 -> 0.02")
    ap.add_argument("--closeout", type=float, default=0.5)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    duk = load_dukascopy(args.dukascopy)
    m15 = load_broker_m15(args.broker, hourly_spread_profile(duk))
    m15 = m15[m15["time"] >= pd.Timestamp("2007-01-01", tz="UTC")].reset_index(drop=True)
    d1 = daily_from_m15(m15)
    bh = pd.Series(1.0, index=E._daily_mid(d1).index)
    bh[bh.index < pd.Timestamp("2008-01-01")] = 0.0
    strategies = {
        "kup i trzymaj": daily_steps(d1, bh),
        "momentum 120d LONG/bez pozycji": daily_steps(d1, E.momentum_pos(d1, 120, True).where(lambda s: s.index >= "2008-01-01", 0)),
        "SHORT 07-15 UTC (Londyn)": [s for s in session_steps(m15, 7, 15, -1) if s.time.year >= 2008],
        "strategia doradcy M15 (SL/TP)": [s for s in m15_strategy_steps(m15, d1) if s.time.year >= 2008],
    }
    report = {"margin_rate": args.margin_rate, "closeout": args.closeout, "leverages": LEVERAGES, "results": {}}
    for name, steps in strategies.items():
        report["results"][name] = {}
        for lev in LEVERAGES:
            r = simulate(steps, lev, args.margin_rate, args.closeout)
            report["results"][name][f"{lev}x"] = {"2008-2024": outcome(r, "2008-01-01", "2025-01-01"),
                                                  "okna_4m": windows(steps, lev)}
            print(name, f"{lev}x", report["results"][name][f"{lev}x"], flush=True)
    with open(os.path.join(args.out, "leverage.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
