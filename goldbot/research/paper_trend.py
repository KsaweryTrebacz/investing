"""Symulacja rachunku prowadzonego według rad strategii trendowej D1 (momentum.signal + momentum.advise).

Dzień po dniu: po zamknięciu świecy D1 program liczy sygnał i radę z progiem `rebalance_band` (tak jak cykl
trybu trend_d1), a transakcja wykonuje się na otwarciu następnego dnia po ASK/BID. Wynik dzienny z ceny
środkowej, finansowanie od całej wartości (środa potrójnie), likwidacja przez brokera, gdy kapitał spadnie
poniżej `closeout` x depozyt (dzienny dołek, przy luce po otwarciu). Waluta rachunku = waluta kwotowania (USD).

Uruchomienie z katalogu goldbot:
  python -m research.paper_trend --broker dane/XAU_15m_data.csv --dukascopy dane/dukascopy_m15 --out wyniki
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

from momentum import TrendParams, advise, daily_frame, leverage_cap, positions, simulate, vol_leverage
from research.datasets import daily_from_m15, hourly_spread_profile, load_broker_m15, load_dukascopy


def paper_trade(d1: pd.DataFrame, p: TrendParams, start: str, capital: float = 20_000.0, margin_rate: float = 0.02,
                closeout: float = 0.5, long_rate: float = -0.05, short_rate: float = -0.01, step: float = 1.0,
                end: str | None = None) -> tuple[pd.Series, pd.DataFrame]:
    """(kapitał na koniec każdego dnia, dziennik transakcji). Rada z dnia t wykonana na otwarciu dnia t+1."""
    day = daily_frame(d1)
    bid_o = d1["bid_o"].to_numpy()
    ask_o = d1["ask_o"].to_numpy()
    cap = leverage_cap(p, margin_rate)
    pos = positions(day, p.lookback, p.long_only)
    lev = vol_leverage(day, p.target_vol, p.vol_window, cap)
    o, h, low, c = (day[k].to_numpy() for k in ("o", "h", "l", "c"))
    idx = day.index
    i0 = max(int(np.searchsorted(idx.values, np.datetime64(start))), p.lookback + p.vol_window)
    i1 = len(day) if end is None else int(np.searchsorted(idx.values, np.datetime64(end)))
    eq, units, curve, log, held = capital, 0.0, [], [], []
    for t in range(i0, i1):
        # 1) rada z zamknięcia dnia t-1, wykonanie na otwarciu dnia t
        adv = advise(int(pos[t - 1]), float(lev[t - 1]), eq, c[t - 1], 1.0, step, units, p.rebalance_band)
        traded = adv["action"] not in ("UTRZYMAJ", "BEZ POZYCJI") and eq > 0
        if traded:
            diff = adv["target_units"] - units
            fill = ask_o[t] if diff > 0 else bid_o[t]
            eq += units * (o[t] - c[t - 1])          # luka nocna na dotychczasowej pozycji
            eq -= abs(diff) * abs(fill - o[t])       # połowa spreadu od zmiany wielkości
            log.append({"date": idx[t], "action": adv["action"], "units_from": units, "units_to": adv["target_units"],
                        "price": fill, "equity": eq, "leverage": adv["target_units"] * o[t] / eq if eq > 0 else 0})
            units, ref = adv["target_units"], o[t]
        else:
            ref = c[t - 1]
        # 2) likwidacja przez brokera w ciągu dnia
        held.append(int(np.sign(units)))
        if units:
            side, u = (1, units) if units > 0 else (-1, -units)
            if side == 1:
                p_star = (u * ref - eq) / (u * (1 - closeout * margin_rate))
                hit, gap = low[t] <= p_star, not traded and o[t] <= p_star
            else:
                p_star = (eq + u * ref) / (u * (1 + closeout * margin_rate))
                hit, gap = h[t] >= p_star, not traded and o[t] >= p_star
            if hit or gap:
                fill = o[t] if gap else p_star
                eq = max(0.0, eq + units * (fill - ref))
                log.append({"date": idx[t], "action": "LIKWIDACJA", "units_from": units, "units_to": 0.0,
                            "price": fill, "equity": eq, "leverage": 0.0})
                units = 0.0
                curve.append(eq)
                continue
            # 3) wynik dnia i finansowanie
            rate = long_rate if side == 1 else short_rate
            eq += units * (c[t] - ref) + u * c[t] * rate / 365 * (3 if idx[t].weekday() == 2 else 1)
            eq = max(eq, 0.0)
        curve.append(eq)
    out = pd.Series(curve, index=idx[i0:i1])
    out.attrs["side"] = np.array(held)  # kierunek pozycji w ciągu każdego dnia (do podziału wyniku LONG/SHORT)
    return out, pd.DataFrame(log)


def summarize(curve: pd.Series, log: pd.DataFrame, capital: float) -> dict:
    years = max((curve.index[-1] - curve.index[0]).days / 365.25, 1e-9)
    yearly = curve.groupby(curve.index.year).last()
    prev = pd.concat([pd.Series([capital]), yearly.iloc[:-1]]).to_numpy()
    w = []
    for s in pd.date_range(curve.index[0], curve.index[-1] - pd.DateOffset(months=4), freq="MS"):
        a, b = curve[curve.index < s], curve[curve.index < s + pd.DateOffset(months=4)]
        if len(a) and a.iloc[-1] > 0:
            w.append(b.iloc[-1] / a.iloc[-1])
    w = np.array(w)
    acts = log["action"].value_counts().to_dict() if len(log) else {}
    windows = {"liczba": 0} if len(w) == 0 else {
        "liczba": len(w), "mediana_%": round(100 * float(np.median(w) - 1), 1),
        "P(strata)_%": round(100 * float((w < 1).mean()), 1), "P(+80%)_%": round(100 * float((w >= 1.8).mean()), 1),
        "P(-50%)_%": round(100 * float((w <= 0.5).mean()), 1), "najlepsze_%": round(100 * float(w.max() - 1), 1),
        "najgorsze_%": round(100 * float(w.min() - 1), 1)}
    return {"od": str(curve.index[0].date()), "do": str(curve.index[-1].date()), "kapital_koncowy": round(float(curve.iloc[-1]), 0),
            "mnoznik": round(float(curve.iloc[-1] / capital), 2),
            "roczne_tempo_%": round(100 * ((max(float(curve.iloc[-1]), 1e-9) / capital) ** (1 / years) - 1), 1),
            "najwiekszy_spadek_%": round(100 * float((curve / curve.cummax() - 1).min()), 1),
            "lata_%": {int(y): round(100 * (v / p0 - 1), 1) for y, v, p0 in zip(yearly.index, yearly.to_numpy(), prev)},
            "transakcje": {k: int(v) for k, v in acts.items()},
            "okna_4m": windows}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", required=True)
    ap.add_argument("--dukascopy", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--capital", type=float, default=20_000.0)
    ap.add_argument("--start", default="2005-01-01")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    duk = load_dukascopy(args.dukascopy)
    d1 = daily_from_m15(load_broker_m15(args.broker, hourly_spread_profile(duk)))
    report = {}
    for fin in ((-0.05, -0.01), (-0.025, 0.0)):
        for tv in (0.5, 0.3):
            curve, log = paper_trade(d1, TrendParams(target_vol=tv), args.start, args.capital, long_rate=fin[0], short_rate=fin[1])
            key = f"cel {tv:.0%}, finansowanie LONG {fin[0]:+.1%}"
            report[key] = summarize(curve, log, args.capital)
            print(key, json.dumps({k: v for k, v in report[key].items() if k != "lata_%"}, ensure_ascii=False), flush=True)
    day = daily_frame(d1)
    for fin in ((-0.05, -0.01), (-0.025, 0.0)):
        i0 = int(np.searchsorted(day.index.values, np.datetime64(args.start)))
        bh = simulate(day.iloc[i0 - 1:], np.ones(len(day) - i0 + 1), np.ones(len(day) - i0 + 1),
                      long_rate=fin[0], short_rate=fin[1]).iloc[1:] * args.capital
        key = f"kup i trzymaj 1x, finansowanie LONG {fin[0]:+.1%}"
        report[key] = summarize(bh, pd.DataFrame(), args.capital)
        print(key, json.dumps({k: v for k, v in report[key].items() if k != "lata_%"}, ensure_ascii=False), flush=True)
    with open(os.path.join(args.out, "paper_trend.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
