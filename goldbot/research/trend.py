"""Alternatywna rodzina strategii do porównania: podążanie za trendem na świecach dziennych.

Wybicie z kanału Donchiana: wejście po zamknięciu powyżej najwyższego zamknięcia z `entry_n` dni
(SHORT lustrzanie), wyjście po zamknięciu poniżej najniższego dołka z `exit_n` dni albo na stopie
początkowym `stop_atr` x ATR(20). Wejście i wyjście na otwarciu następnego dnia, po ASK/BID.
Stop przy luce wykonuje się po otwarciu. Finansowanie za każdy rollover jak w costs.py.

Uruchomienie z katalogu goldbot:
  python -m research.trend --broker dane/XAU_15m_data.csv --dukascopy dane/dukascopy_m15 --out wyniki
"""
import argparse
import itertools
import json
import os

import numpy as np
import pandas as pd

from config import Costs
from costs import financing_days
from indicators import atr
from research.datasets import daily_from_m15, hourly_spread_profile, load_broker_m15, load_dukascopy
from research.study import STUDY_COSTS, _in, by_year, monte_carlo, stats

GRID = {"entry_n": [20, 55, 100], "exit_n": [10, 20, 50], "stop_atr": [2.0, 3.0, 4.0], "long_only": [True, False]}
MIN_TRADES = 10


def run_donchian(d1: pd.DataFrame, entry_n: int, exit_n: int, stop_atr: float, long_only: bool,
                 costs: Costs = STUDY_COSTS) -> pd.DataFrame:
    """Transakcje strategii: entry_time, exit_time, side, R (netto: spread w cenach, poślizg, finansowanie)."""
    d = d1.reset_index(drop=True)
    mid = {k: ((d[f"bid_{k}"] + d[f"ask_{k}"]) / 2).to_numpy() for k in "ohlc"}
    a = atr(pd.Series(mid["h"]), pd.Series(mid["l"]), pd.Series(mid["c"]), 20).to_numpy()
    c = pd.Series(mid["c"])
    up = (c > c.rolling(entry_n).max().shift(1)).to_numpy()
    dn = (c < c.rolling(entry_n).min().shift(1)).to_numpy()
    ex_lo = pd.Series(mid["l"]).rolling(exit_n).min().shift(1).to_numpy()
    ex_hi = pd.Series(mid["h"]).rolling(exit_n).max().shift(1).to_numpy()
    bo, bl, bc, ao, ah, ac = (d[x].to_numpy() for x in ("bid_o", "bid_l", "bid_c", "ask_o", "ask_h", "ask_c"))
    times = d["time"].array
    n, i, trades = len(d), max(entry_n, 20), []
    while i < n - 1:
        side = 1 if up[i] else -1 if (dn[i] and not long_only) else 0
        if side == 0 or not a[i] > 0:
            i += 1
            continue
        j = i + 1
        entry = ao[j] if side == 1 else bo[j]
        stop = entry - side * stop_atr * a[i]
        risk, slip = abs(entry - stop), (costs.slippage_atr or 0.0) * a[i]
        exit_px, k = None, j
        for k in range(j, n):
            o, ext = (bo[k], bl[k]) if side == 1 else (ao[k], ah[k])
            if side * (o - stop) <= 0:            # luka za stopem: wykonanie po otwarciu
                exit_px = o - side * slip
                break
            if side * (ext - stop) <= 0:
                exit_px = stop - side * slip
                break
            if k + 1 < n and side * (mid["c"][k] - (ex_lo[k] if side == 1 else ex_hi[k])) < 0:
                k += 1                            # zamknięcie za kanałem wyjścia: wyjście na następnym otwarciu
                exit_px = bo[k] if side == 1 else ao[k]
                break
        if exit_px is None:
            k = n - 1
            exit_px = bc[k] if side == 1 else ac[k]
        days = financing_days(times[j], times[k], costs.triple_financing_weekday)
        rate = costs.financing_long_rate if side == 1 else costs.financing_short_rate
        fin = -entry * (rate or 0.0) / 365 * days
        trades.append({"entry_time": times[j], "exit_time": times[k], "side": side,
                       "R": (side * (exit_px - entry) - fin) / risk, "days": (times[k] - times[j]).days})
        i = k + 1
    return pd.DataFrame(trades)


def grid_results(d1, grid=GRID, costs=STUDY_COSTS) -> list:
    out = []
    keys = list(grid)
    for values in itertools.product(*(grid[k] for k in keys)):
        p = dict(zip(keys, values))
        if p["exit_n"] >= p["entry_n"]:
            continue
        t = run_donchian(d1, costs=costs, **p)
        times = pd.DatetimeIndex(t["entry_time"]).as_unit("ns").asi8 if len(t) else np.array([], np.int64)
        out.append((p, times, t["R"].to_numpy() if len(t) else np.array([])))
    return out


def buy_and_hold(d1, start, end) -> dict:
    """Zwrot z trzymania złota (bez dźwigni i kosztów) i jego największy spadek w okresie."""
    d = d1[(d1["time"] >= pd.Timestamp(start, tz="UTC")) & (d1["time"] < pd.Timestamp(end, tz="UTC"))]
    c = ((d["bid_c"] + d["ask_c"]) / 2).to_numpy()
    return {"return_%": round(100 * (c[-1] / c[0] - 1), 1),
            "max_dd_%": round(100 * float((c / np.maximum.accumulate(c) - 1).min()), 1)}


def main(argv=None):
    import research.study as st
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", required=True)
    ap.add_argument("--dukascopy", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--train-years", type=int, default=3)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    duk = load_dukascopy(args.dukascopy)
    m15 = load_broker_m15(args.broker, hourly_spread_profile(duk))
    d1 = daily_from_m15(m15)
    first, last = d1.time.min().year + args.train_years + 1, 2024
    results = grid_results(d1)
    st.MIN_TRADES = MIN_TRADES
    span = last + 1 - first
    report = {"grid": GRID, "min_trades": MIN_TRADES, "buy_and_hold": buy_and_hold(d1, f"{first}-01-01", f"{last + 1}-01-01")}
    for name, only in (("walk_forward", None), ("walk_forward_long_only", lambda p: p["long_only"])):
        w = st.walk_forward(results, first, last, args.train_years, only=only)
        report[name] = {"stats": stats(w["R"]), "by_year": by_year(w["times"], w["R"]), "chosen": w["chosen"],
                        "trades_per_year": round(len(w["R"]) / span, 1)}
        if len(w["R"]) >= 20:
            report[name]["monte_carlo_4m"] = monte_carlo(w["R"], len(w["R"]) / span, 4)
            report[name]["monte_carlo_12m"] = monte_carlo(w["R"], len(w["R"]) / span, 12)
    report["classic_55_20_3atr"] = {}
    for lo in (True, False):
        t = run_donchian(d1, 55, 20, 3.0, lo)
        tt = pd.DatetimeIndex(t["entry_time"]).as_unit("ns").asi8
        m = _in(tt, f"{first}-01-01", f"{last + 1}-01-01")
        report["classic_55_20_3atr"]["long_only" if lo else "long_short"] = {
            "stats": stats(t["R"].to_numpy()[m]), "by_year": by_year(tt[m], t["R"].to_numpy()[m])}
    tr0 = f"{last + 1 - args.train_years}-01-01"
    live = max(results, key=lambda x: st.score(x[2][_in(x[1], tr0, f"{last + 1}-01-01")]))
    report["latest_selection"] = {"params": live[0], "train_stats": stats(live[2][_in(live[1], tr0, f"{last + 1}-01-01")])}
    dt = run_donchian(daily_from_m15(duk), **live[0])
    report["latest_selection"]["dukascopy_2011_2018"] = stats(dt["R"].to_numpy()) if len(dt) else {"trades": 0}
    with open(os.path.join(args.out, "trend.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    print(json.dumps(report, ensure_ascii=False, indent=1, default=str)[:15000])


if __name__ == "__main__":
    main()
