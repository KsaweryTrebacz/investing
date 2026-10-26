"""Optymalizacja walk-forward, ryzyko utraty kapitału (Monte Carlo) i porównanie z losowymi wejściami.

Zasada: parametry na dany rok wybiera się wyłącznie na podstawie `train_years` lat poprzednich, a wynik
liczy się na tym roku (poza próbą). Sklejone wyniki lat testowych to uczciwa ocena całej procedury.

Uruchomienie z katalogu goldbot (dane pobiera research/download.sh):
  python -m research.study --broker dane/XAU_15m_data.csv --dukascopy dane/dukascopy_m15 --out wyniki
"""
import argparse
import itertools
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace

import numpy as np
import pandas as pd

import backtest
from config import Costs
from pipeline import prepare
from research.datasets import daily_from_m15, hourly_spread_profile, load_broker_m15, load_dukascopy
from strategy import Params

# Koszty przyjęte w badaniu (założenia, nie stawki konkretnego brokera): prowizja 0 jak w rachunkach
# ze spreadem, finansowanie obu stron jako koszt, poślizg na SL 0,1 ATR. Spread pochodzi z danych.
STUDY_COSTS = Costs(source="założenia badania", commission_per_unit=0.0, financing_long_rate=-0.05,
                    financing_short_rate=-0.01, slippage_atr=0.1)
SIGNAL_GRID = {"rsi_long": [35.0, 40.0, 45.0], "arm_bars": [5, 10, 20], "session": [None, (7, 17)],
               "ema_align": [False, True], "room_atr": [0.0, 2.0], "use_regime": [True, False]}
EXIT_GRID = {"sl_atr": [1.0, 1.5, 2.0, 3.0], "tp_atr": [1.0, 1.5, 2.0, 3.0, 4.0]}
MIN_TRADES = 30          # minimalna liczba transakcji w oknie uczącym
EXPIRE_HOURS = 48

_DATA = {}               # dane dla procesów potomnych (fork)


def signal_sets(grid=SIGNAL_GRID):
    keys = list(grid)
    for values in itertools.product(*(grid[k] for k in keys)):
        d = dict(zip(keys, values))
        d["rsi_short"] = 100.0 - d["rsi_long"]
        yield d


def exit_sets(grid=EXIT_GRID):
    for sl, tp in itertools.product(grid["sl_atr"], grid["tp_atr"]):
        yield {"sl_atr": sl, "tp_atr": tp}


def _run_signal_set(sig: dict) -> list:
    """Wszystkie warianty wyjścia dla jednego zestawu sygnału: [(parametry, czasy wejść, R)]."""
    m15, d1, costs = _DATA["m15"], _DATA["d1"], _DATA["costs"]
    base = Params(**sig)
    df = prepare(m15, d1, p=base, macro=False)  # reżim z trendu D1: w danych publicznych brak makro
    out = []
    for ex in exit_sets(_DATA["exit_grid"]):
        p = replace(base, **ex)
        t, _ = backtest.run(df, p, costs=costs, expire_hours=EXPIRE_HOURS)
        times = pd.DatetimeIndex(t["entry_time"]).as_unit("ns").asi8 if len(t) else np.array([], np.int64)
        out.append(({**sig, **ex}, times, t["R"].to_numpy() if len(t) else np.array([])))
    return out


def all_trades(m15, d1, costs=STUDY_COSTS, signal_grid=SIGNAL_GRID, exit_grid=EXIT_GRID, workers=4) -> list:
    """Pełne przebiegi dla całej siatki. Każda pozycja: (parametry, czasy wejść w ns, R netto)."""
    _DATA.update(m15=m15, d1=d1, costs=costs, exit_grid=exit_grid)
    sets = list(signal_sets(signal_grid))
    if workers > 1:
        with ProcessPoolExecutor(workers) as ex:
            chunks = list(ex.map(_run_signal_set, sets))
    else:
        chunks = [_run_signal_set(s) for s in sets]
    return [r for chunk in chunks for r in chunk]


def stats(r: np.ndarray, risk: float = 0.005) -> dict:
    """Statystyki serii R: liczba, trafność, średnia, suma, t, maks. spadek w R, wynik przy danym ryzyku."""
    n = len(r)
    if n == 0:
        return {"trades": 0}
    cum = np.cumsum(r)
    dd = float((cum - np.maximum.accumulate(np.r_[0.0, cum])[1:]).min())
    sd = float(r.std(ddof=1)) if n > 1 else 0.0
    equity = np.cumprod(1 + risk * r)
    eq_dd = float((equity / np.maximum.accumulate(np.r_[1.0, equity])[1:] - 1).min())
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {"trades": n, "win_rate_%": round(100 * float((r > 0).mean()), 1), "avg_R": round(float(r.mean()), 4),
            "total_R": round(float(cum[-1]), 2), "t_stat": round(float(r.mean() / sd * math.sqrt(n)), 2) if sd else 0.0,
            "max_dd_R": round(dd, 2), "profit_factor": round(float(gains / losses), 2) if losses else None,
            f"return_%_at_{risk:.1%}": round(100 * float(equity[-1] - 1), 2),
            f"max_dd_%_at_{risk:.1%}": round(100 * eq_dd, 2)}


def _in(times: np.ndarray, start, end) -> np.ndarray:
    return (times >= pd.Timestamp(start, tz="UTC").value) & (times < pd.Timestamp(end, tz="UTC").value)


def score(r: np.ndarray) -> float:
    """Kryterium wyboru na oknie uczącym: statystyka t średniego R (wynik i jego stabilność, nie sam zysk)."""
    if len(r) < MIN_TRADES or r.std(ddof=1) == 0:
        return -np.inf
    return float(r.mean() / r.std(ddof=1) * math.sqrt(len(r)))


def walk_forward(results: list, first_test: int, last_test: int, train_years: int = 3, only=None) -> dict:
    """Co roku wybór najlepszego wariantu na `train_years` latach wstecz i test na tym roku.

    only: funkcja filtrująca warianty (np. tylko wyjścia przy stałym sygnale). Gdy żaden wariant nie ma
    dodatniego wyniku w oknie uczącym, w roku testowym nie ma transakcji.
    """
    chosen, oos_t, oos_r = [], [], []
    pool = [x for x in results if only is None or only(x[0])]
    for year in range(first_test, last_test + 1):
        tr0, tr1, te1 = f"{year - train_years}-01-01", f"{year}-01-01", f"{year + 1}-01-01"
        best, best_s = None, -np.inf
        for params, times, r in pool:
            s = score(r[_in(times, tr0, tr1)])
            if s > best_s:
                best, best_s = (params, times, r), s
        if best is None or best_s <= 0:
            chosen.append({"year": year, "params": None, "train_t": None})
            continue
        params, times, r = best
        m = _in(times, tr1, te1)
        oos_t.append(times[m])
        oos_r.append(r[m])
        chosen.append({"year": year, "params": params, "train_t": round(best_s, 2), "test": stats(r[m])})
    t = np.concatenate(oos_t) if oos_t else np.array([], np.int64)
    r = np.concatenate(oos_r) if oos_r else np.array([])
    return {"chosen": chosen, "times": t, "R": r}


def by_year(times: np.ndarray, r: np.ndarray) -> dict:
    years = pd.DatetimeIndex(times.astype("datetime64[ns]")).year
    return {int(y): round(float(r[years == y].sum()), 2) for y in sorted(set(years))}


def monte_carlo(r: np.ndarray, trades_per_year: float, months: int = 4, risks=(0.005, 0.01, 0.02),
                paths: int = 10_000, seed: int = 1) -> dict:
    """Losowanie ze zwracaniem transakcji poza próbą: rozkład wyniku i spadku kapitału w horyzoncie `months`."""
    rng = np.random.default_rng(seed)
    n = max(1, round(trades_per_year * months / 12))
    sample = rng.choice(r, size=(paths, n), replace=True)
    out = {"months": months, "trades_per_path": n}
    for risk in risks:
        eq = np.cumprod(1 + risk * sample, axis=1)
        ret = eq[:, -1] - 1
        dd = (eq / np.maximum.accumulate(np.concatenate([np.ones((paths, 1)), eq], axis=1)[:, 1:], axis=1) - 1).min(1)
        out[f"{risk:.1%}"] = {"P(strata)_%": round(100 * float((ret < 0).mean()), 1),
                              "mediana_%": round(100 * float(np.median(ret)), 2),
                              "p5_%": round(100 * float(np.percentile(ret, 5)), 2),
                              "p95_%": round(100 * float(np.percentile(ret, 95)), 2),
                              "P(spadek>=10%)_%": round(100 * float((dd <= -0.10).mean()), 1),
                              "P(spadek>=20%)_%": round(100 * float((dd <= -0.20).mean()), 1),
                              "P(spadek>=50%)_%": round(100 * float((dd <= -0.50).mean()), 2)}
    return out


def random_benchmark(m15, d1, p: Params, n_signals: int, runs: int = 100, costs=STUDY_COSTS, seed: int = 7) -> np.ndarray:
    """Średnie R losowych wejść (losowy moment i kierunek, te same wyjścia i koszty) w `runs` próbach."""
    rng = np.random.default_rng(seed)
    df = prepare(m15, d1, p=p, macro=False)
    means = []
    for _ in range(runs):
        sig = np.zeros(len(df), dtype=int)
        idx = rng.choice(np.arange(p.ema_len, len(df) - 1), size=n_signals, replace=False)
        sig[idx] = rng.choice([-1, 1], size=n_signals)
        t, _ = backtest.run(df.assign(signal=sig), p, costs=costs, expire_hours=EXPIRE_HOURS)
        means.append(t["R"].mean() if len(t) else 0.0)
    return np.array(means)


def run_fixed(m15, d1, p: Params, costs=STUDY_COSTS):
    df = prepare(m15, d1, p=p, macro=False)
    t, _ = backtest.run(df, p, costs=costs, expire_hours=EXPIRE_HOURS)
    return pd.DatetimeIndex(t["entry_time"]).as_unit("ns").asi8, t["R"].to_numpy()


def _params_key(p: dict) -> str:
    return json.dumps({k: p[k] for k in sorted(p)}, default=str)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", required=True, help="XAU_15m_data.csv (BaseMax)")
    ap.add_argument("--dukascopy", required=True, help="katalog z XAUUSD_<rok>.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--train-years", type=int, default=3)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    report = {"costs": asdict(STUDY_COSTS), "signal_grid": {k: [str(v) for v in vs] for k, vs in SIGNAL_GRID.items()},
              "exit_grid": EXIT_GRID, "min_trades": MIN_TRADES, "train_years": args.train_years}

    duk = load_dukascopy(args.dukascopy)
    profile = hourly_spread_profile(duk)
    m15 = load_broker_m15(args.broker, profile)
    d1 = daily_from_m15(m15)
    report["data"] = {"broker": [str(m15.time.min()), str(m15.time.max()), len(m15)],
                      "dukascopy": [str(duk.time.min()), str(duk.time.max()), len(duk)],
                      "spread_profile_bp": {int(h): round(v * 1e4, 2) for h, v in profile.items()}}
    print("Dane:", report["data"]["broker"], "Dukascopy:", report["data"]["dukascopy"], flush=True)

    results = all_trades(m15, d1, workers=args.workers)
    print(f"Warianty: {len(results)}", flush=True)
    first = m15.time.min().year + args.train_years + 1  # pierwszy pełny rok testowy
    last = m15.time.max().year - 1 if m15.time.max().month < 7 else m15.time.max().year

    baseline = Params(use_regime=True)
    bt, br = run_fixed(m15, d1, baseline)
    m = _in(bt, f"{first}-01-01", f"{last + 1}-01-01")
    report["baseline"] = {"params": "domyślne (reżim z trendu D1)", "stats": stats(br[m]), "by_year": by_year(bt[m], br[m])}

    wf = walk_forward(results, first, last, args.train_years)
    base_sig = {k: getattr(baseline, k) for k in SIGNAL_GRID} | {"rsi_short": baseline.rsi_short}
    wf_exit = walk_forward(results, first, last, args.train_years,
                           only=lambda p: all(p[k] == base_sig[k] for k in base_sig))
    span = (pd.Timestamp(f"{last + 1}-01-01") - pd.Timestamp(f"{first}-01-01")).days / 365.25
    for name, w in (("walk_forward_full_grid", wf), ("walk_forward_exits_only", wf_exit)):
        report[name] = {"stats": stats(w["R"]), "by_year": by_year(w["times"], w["R"]), "chosen": w["chosen"],
                        "trades_per_year": round(len(w["R"]) / span, 1)}
        if len(w["R"]) >= 20:
            report[name]["monte_carlo_4m"] = monte_carlo(w["R"], len(w["R"]) / span, 4)
            report[name]["monte_carlo_12m"] = monte_carlo(w["R"], len(w["R"]) / span, 12)

    # najlepszy wariant "z wiedzą o przyszłości" (na całym okresie testowym): miara przeuczenia
    hind = max(results, key=lambda x: score(x[2][_in(x[1], f"{first}-01-01", f"{last + 1}-01-01")]))
    hm = _in(hind[1], f"{first}-01-01", f"{last + 1}-01-01")
    report["hindsight_best"] = {"params": hind[0], "stats": stats(hind[2][hm])}

    # losowe wejścia (tyle, ile transakcji ma strategia domyślna) z tymi samymi wyjściami i kosztami
    rnd = random_benchmark(m15, d1, Params(), max(500, len(br)), runs=100)
    report["random_benchmark"] = {"runs": 100, "signals_per_run": max(500, len(br)),
                                  "mean_R_mean": round(float(rnd.mean()), 4),
                                  "mean_R_p5": round(float(np.percentile(rnd, 5)), 4),
                                  "mean_R_p95": round(float(np.percentile(rnd, 95)), 4),
                                  "baseline_mean_R_full": round(float(br.mean()), 4),
                                  "wf_mean_R": round(float(wf["R"].mean()), 4) if len(wf["R"]) else None}

    # wariant na przyszłość: wybór na ostatnich latach (tak wybrałby go program dziś)
    tr0 = f"{last + 1 - args.train_years}-01-01"
    live = max(results, key=lambda x: score(x[2][_in(x[1], tr0, f"{last + 1}-01-01")]))
    lm = _in(live[1], tr0, f"{last + 1}-01-01")
    report["latest_selection"] = {"params": live[0], "train_window": [tr0, f"{last}-12-31"],
                                  "train_stats": stats(live[2][lm]), "positive": score(live[2][lm]) > 0}

    # niezależne źródło: Dukascopy (prawdziwy spread) i stres podwójnego spreadu dla wybranego wariantu
    lp = Params(**{k: v for k, v in live[0].items()})
    duk_d1 = daily_from_m15(duk)
    dt, dr = run_fixed(duk, duk_d1, lp)
    bt2, br2 = run_fixed(m15, d1, lp)
    same = _in(bt2, str(duk.time.min().date()), str(duk.time.max().date()))
    wide = load_broker_m15(args.broker, profile, spread_mult=2.0)
    wt, wr = run_fixed(wide, daily_from_m15(wide), lp)
    report["latest_selection"]["dukascopy_2011_2018"] = stats(dr)
    report["latest_selection"]["broker_same_period"] = stats(br2[same])
    report["latest_selection"]["broker_full_double_spread"] = stats(wr)
    dbt, dbr = run_fixed(duk, duk_d1, baseline)
    report["baseline"]["dukascopy_2011_2018"] = stats(dbr)

    with open(os.path.join(args.out, "study.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    pd.DataFrame([{**p, **stats(r)} for p, _, r in results]).to_csv(os.path.join(args.out, "grid_full_period.csv"),
                                                                     index=False)
    print(json.dumps({k: report[k] for k in report if k not in ("chosen",)}, ensure_ascii=False, indent=1,
                     default=str)[:20000])


if __name__ == "__main__":
    main()
