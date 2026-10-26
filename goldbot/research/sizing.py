"""Dobór dźwigni CFD (1:50) dla strategii dziennych: stała, walk-forward, celowanie w zmienność, Kelly kroczący.

Kryterium „optymalnej” dźwigni: największy kapitał końcowy (wzrost geometryczny), bez kary za spadki.
Rachunek przeliczany codziennie: ekspozycja = dźwignia x kapitał (na zamknięciu poprzedniego dnia),
koszt spreadu od zmiany wielkości, finansowanie od całej wartości, likwidacja przez brokera, gdy kapitał
spadnie poniżej `closeout` x depozyt (sprawdzana na dziennym dołku/szczycie, przy luce po otwarciu).

Uruchomienie z katalogu goldbot:
  python -m research.sizing --broker dane/XAU_15m_data.csv --dukascopy dane/dukascopy_m15 --out wyniki
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

from research import edges as E
from research.datasets import daily_from_m15, hourly_spread_profile, load_broker_m15, load_dukascopy

NY = "America/New_York"
GRID = (0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 7, 10, 15, 20, 30, 50)
VOL_TARGETS = (0.05, 0.1, 0.15, 0.2, 0.3, 0.5)
FIXED_TARGETS = (0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0)
MAX_LEV = 50.0


def daily_frame(d1: pd.DataFrame) -> pd.DataFrame:
    """Dzienne ceny środkowe, spread względny i etykieta dnia handlowego (jak w research.edges)."""
    d = d1.reset_index(drop=True)
    out = pd.DataFrame({k: ((d[f"bid_{k}"] + d[f"ask_{k}"]) / 2).to_numpy() for k in "ohlc"})
    out["spread"] = ((d["ask_c"] - d["bid_c"]) / out["c"]).to_numpy()
    out.index = d["time"].dt.tz_convert(NY).dt.normalize().dt.tz_localize(None) + pd.Timedelta(days=1)
    return out


def simulate(day: pd.DataFrame, pos: np.ndarray, lev: np.ndarray, margin_rate: float = 0.02, closeout: float = 0.5,
             long_rate: float = -0.05, short_rate: float = -0.01) -> pd.Series:
    """Kapitał na koniec każdego dnia (start 1). pos i lev ustalone na zamknięciu dnia t-1, działają w dniu t."""
    o, h, low, c, spr = (day[k].to_numpy() for k in ("o", "h", "l", "c", "spread"))
    triple = (day.index.weekday == 2)
    eq, units, out = 1.0, 0.0, np.empty(len(day))
    out[0] = eq
    for t in range(1, len(day)):
        if eq <= 1e-6:
            out[t:] = 0.0
            break
        ref = c[t - 1]
        target = pos[t - 1] * min(lev[t - 1], MAX_LEV) * eq / ref if np.isfinite(lev[t - 1]) else 0.0
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


def run(day, pos, lev, start, end, fin) -> pd.Series:
    """Świeży rachunek (kapitał 1) w okresie [start, end): symulacja od ostatniego dnia przed `start`."""
    i0 = max(int(np.searchsorted(day.index.values, np.datetime64(start))) - 1, 0)
    i1 = int(np.searchsorted(day.index.values, np.datetime64(end)))
    return simulate(day.iloc[i0:i1], pos[i0:i1], lev[i0:i1], long_rate=fin[0], short_rate=fin[1])


def wealth(day, pos, lev, start, end, fin) -> float:
    """Mnożnik kapitału świeżego rachunku w okresie [start, end)."""
    c = run(day, pos, lev, start, end, fin)
    return float(c.iloc[-1]) if len(c) > 1 else 1.0


def vol_leverage(day: pd.DataFrame, target: float, window: int = 20) -> np.ndarray:
    """Dźwignia = docelowa zmienność roczna / zmienność z `window` dni (znana na zamknięciu dnia)."""
    r = np.log(day["c"]).diff()
    vol = r.rolling(window).std() * np.sqrt(252)
    return (target / vol).clip(upper=MAX_LEV).fillna(0.0).to_numpy()


def kelly_leverage(day: pd.DataFrame, pos: np.ndarray, fraction: float = 0.5, window: int = 500,
                   long_rate: float = -0.05, short_rate: float = -0.01) -> np.ndarray:
    """Kroczący Kelly: f = frakcja x średnia / wariancja dziennych zwrotów strategii (1x, po finansowaniu)."""
    r = day["c"].pct_change().to_numpy()
    p_prev = np.r_[0.0, pos[:-1]]
    fin = np.where(p_prev > 0, long_rate, np.where(p_prev < 0, short_rate, 0.0)) * np.abs(p_prev) / 365
    sr = pd.Series(p_prev * r + fin, index=day.index)
    mu, var = sr.rolling(window, min_periods=250).mean(), sr.rolling(window, min_periods=250).var()
    return (fraction * mu / var).clip(lower=0, upper=MAX_LEV).fillna(0.0).to_numpy()


def static_grid(day, pos, fin, start, end) -> dict:
    return {lev: wealth(day, pos, np.full(len(day), float(lev)), start, end, fin) for lev in GRID}


def walk_forward(day, pos, rules: dict, fin, first: int, last: int, train_years: int = 3):
    """rules: nazwa -> tablica dźwigni. Co rok wybór reguły z największym kapitałem w `train_years` latach wstecz."""
    eq, chosen = 1.0, []
    for y in range(first, last + 1):
        tr0, tr1, te1 = pd.Timestamp(f"{y - train_years}-01-01"), pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01")
        best = max(rules, key=lambda k: wealth(day, pos, rules[k], tr0, tr1, fin))
        g = wealth(day, pos, rules[best], tr1, te1, fin)
        eq *= g
        chosen.append({"year": y, "rule": best, "year_x": round(g, 3)})
    return eq, chosen


def windows4m(day, pos, lev, fin, first: int = 2008, last: int = 2024) -> dict:
    """Okna 4-miesięczne zaczynane co miesiąc, każde ze świeżym rachunkiem."""
    f = np.array([wealth(day, pos, lev, s, s + pd.DateOffset(months=4), fin)
                  for s in pd.date_range(f"{first}-01-01", f"{last}-09-01", freq="MS")])
    return {"okna": len(f), "mediana_%": round(100 * float(np.median(f) - 1), 1), "P(strata)_%": round(100 * float((f < 1).mean()), 1),
            "P(+80%)_%": round(100 * float((f >= 1.8).mean()), 1), "P(-50%)_%": round(100 * float((f <= 0.5).mean()), 1)}


def fixed_targets(day, pos, fin, split: str = "2016-01-01", first: int = 2008, last: int = 2024) -> dict:
    """Stała docelowa zmienność: wynik na połowie do doboru, na połowie testowej i w całości, spadki, okna 4m."""
    a, b, c = pd.Timestamp(f"{first}-01-01"), pd.Timestamp(split), pd.Timestamp(f"{last + 1}-01-01")
    dd = lambda x: round(100 * float((x / x.cummax() - 1).min()), 1)  # noqa: E731
    m = (day.index >= a) & (day.index < c)
    out = {}
    for t in FIXED_TARGETS:
        lev = vol_leverage(day, t)
        ra, rb, rc = run(day, pos, lev, a, b, fin), run(day, pos, lev, b, c, fin), run(day, pos, lev, a, c, fin)
        used = lev[m][pos[m] != 0]
        out[f"{int(t * 100)}%"] = {"dobor_x": round(float(ra.iloc[-1]), 3), "dobor_dd_%": dd(ra),
                                   "test_x": round(float(rb.iloc[-1]), 3), "test_dd_%": dd(rb),
                                   "calosc_x": round(float(rc.iloc[-1]), 3), "calosc_dd_%": dd(rc),
                                   "sr_dzwignia": round(float(used.mean()), 2), "maks_dzwignia": round(float(min(used.max(), MAX_LEV)), 1),
                                   "okna_4m_test": windows4m(day, pos, lev, fin, int(split[:4]), last)}
    best = max(out, key=lambda k: out[k]["dobor_x"])
    return {"targets": out, "wybor_na_dobor": best, "wynik_testu_x": out[best]["test_x"]}


def study(day: pd.DataFrame, strategies: dict, fin, first=2008, last=2024) -> dict:
    out = {}
    start, end = pd.Timestamp(f"{first}-01-01"), pd.Timestamp(f"{last + 1}-01-01")
    for name, pos in strategies.items():
        grid = static_grid(day, pos, fin, start, end)
        best = max(grid, key=grid.get)
        rules = {f"stała {lev}x": np.full(len(day), float(lev)) for lev in GRID}
        wf_static, ch_static = walk_forward(day, pos, rules, fin, first, last)
        vol_rules = {f"zmienność {int(t * 100)}%": vol_leverage(day, t) for t in VOL_TARGETS}
        wf_vol, ch_vol = walk_forward(day, pos, vol_rules, fin, first, last)
        kelly = {}
        for frac in (0.5, 1.0):
            lev = kelly_leverage(day, pos, frac, long_rate=fin[0], short_rate=fin[1])
            kelly[f"Kelly x{frac:g}"] = {"wealth_x": round(wealth(day, pos, lev, start, end, fin), 3),
                                         "avg_leverage": round(float(lev[(day.index >= start) & (day.index < end)].mean()), 2)}
        out[name] = {"static_grid_wealth_x": {str(k): round(v, 3) for k, v in grid.items()},
                     "hindsight_best_leverage": best, "hindsight_best_wealth_x": round(grid[best], 3),
                     "hindsight_best_4m": windows4m(day, pos, np.full(len(day), float(best)), fin, first, last),
                     "wf_static_wealth_x": round(wf_static, 3), "wf_static_chosen": [c["rule"] for c in ch_static],
                     "wf_vol_target_wealth_x": round(wf_vol, 3), "wf_vol_chosen": [c["rule"] for c in ch_vol],
                     "kelly": kelly, "fixed_vol_targets": fixed_targets(day, pos, fin)}
        ft = out[name]["fixed_vol_targets"]
        print(name, fin, "| stała zmienność: wybór", ft["wybor_na_dobor"], "test x", ft["wynik_testu_x"],
              "| najlepsza stała dźwignia", best, round(grid[best], 3), "| WF stała", round(wf_static, 3),
              "| WF zmienność", round(wf_vol, 3), "|", kelly, flush=True)
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
    d1 = daily_from_m15(m15)
    day = daily_frame(d1)
    strategies = {
        "kup i trzymaj (LONG)": np.ones(len(day)),
        "momentum 120d LONG/bez pozycji": E.momentum_pos(d1, 120, True).reindex(day.index).fillna(0).to_numpy(),
        "momentum 120d LONG/SHORT": E.momentum_pos(d1, 120, False).reindex(day.index).fillna(0).to_numpy(),
        "średnia 200d LONG/bez pozycji": E.ma_pos(d1, 200, True).reindex(day.index).fillna(0).to_numpy(),
    }
    report = {"grid": GRID, "vol_targets": VOL_TARGETS, "margin_rate": 0.02, "closeout": 0.5}
    for fin in ((-0.05, -0.01), (-0.025, 0.0), (0.0, 0.0)):
        report[f"finansowanie LONG {fin[0]:+.1%} SHORT {fin[1]:+.1%}"] = study(day, strategies, fin)
    with open(os.path.join(args.out, "sizing.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
