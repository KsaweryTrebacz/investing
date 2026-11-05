"""Strategia trendowa D1 z pozycjami LONG i SHORT: rachunek według rad programu i reguły wejścia na SHORT.

1) paper_trade z long_only=False (SHORT przy ujemnym momentum 120 dni) wobec wersji tylko LONG,
   z podziałem wyniku na dni z pozycją LONG i SHORT.
2) Reguły SHORT (dłuższe momentum, cena pod średnią 200 dni, próg spadku, połowa dźwigni): wybór na
   2005-2014, test na 2015-2025, symulacja momentum.simulate (przeliczanie codzienne).

Uruchomienie z katalogu goldbot:
  python -m research.longshort --broker dane/XAU_15m_data.csv --dukascopy dane/dukascopy_m15 --out wyniki
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

import momentum as M
from research.datasets import daily_from_m15, hourly_spread_profile, load_broker_m15, load_dukascopy
from research.paper_trend import paper_trade, summarize

FINANCING = ((-0.05, -0.01), (-0.025, 0.0))


def side_split(curve: pd.Series, capital: float) -> dict:
    """Łączny wynik dni z pozycją LONG i dni z pozycją SHORT (iloczyn dziennych zmian kapitału)."""
    side = curve.attrs["side"]
    r = curve.pct_change().fillna(curve.iloc[0] / capital - 1).to_numpy()
    return {"LONG_%": round(100 * float(np.prod(1 + r[side == 1]) - 1), 1),
            "SHORT_%": round(100 * float(np.prod(1 + r[side == -1]) - 1), 1),
            "dni_LONG_%": round(100 * float((side == 1).mean()), 1), "dni_SHORT_%": round(100 * float((side == -1).mean()), 1)}


def short_rules(day: pd.DataFrame) -> dict:
    c = day["c"]
    mom = lambda n: (c / c.shift(n) - 1).to_numpy()  # noqa: E731
    below = c.to_numpy() < c.rolling(200).mean().to_numpy()
    return {"tylko LONG": np.zeros(len(c), bool), "momentum 120 < 0": mom(120) < 0, "momentum 250 < 0": mom(250) < 0,
            "momentum 120 < 0 i cena < SMA200": (mom(120) < 0) & below,
            "momentum 120 < -5%": mom(120) < -0.05, "momentum 120 < -10%": mom(120) < -0.10}


def _run(day, pos, lev, a, b, fin) -> dict:
    i0 = max(int(np.searchsorted(day.index.values, np.datetime64(a))) - 1, 0)
    i1 = int(np.searchsorted(day.index.values, np.datetime64(b)))
    eq = M.simulate(day.iloc[i0:i1], pos[i0:i1], lev[i0:i1], long_rate=fin[0], short_rate=fin[1])
    return {"x": round(float(eq.iloc[-1]), 2), "spadek_%": round(100 * float((eq / eq.cummax() - 1).min()), 1)}


def rules_split(day: pd.DataFrame, target_vol: float = 0.5, select: tuple = ("2005-01-01", "2015-01-01"),
                test: tuple = ("2015-01-01", "2025-04-01")) -> dict:
    lev = M.vol_leverage(day, target_vol)
    long_ = M.positions(day, 120) > 0
    out = {}
    for fin in FINANCING:
        rows = {}
        for name, short in short_rules(day).items():
            for scale in ((1.0,) if name == "tylko LONG" else (1.0, 0.5)):
                pos = np.where(long_, 1.0, np.where(short, -1.0, 0.0))
                lv = np.where(pos < 0, lev * scale, lev)
                rows[name + ("" if scale == 1.0 else ", SHORT z połową dźwigni")] = {
                    "dobor": _run(day, pos, lv, *select, fin), "test": _run(day, pos, lv, *test, fin),
                    "calosc": _run(day, pos, lv, select[0], test[1], fin), "dni_SHORT_%": round(100 * float((pos < 0).mean()), 1)}
        best = max(rows, key=lambda k: rows[k]["dobor"]["x"])
        out[f"finansowanie LONG {fin[0]:+.1%} SHORT {fin[1]:+.1%}"] = {
            "reguly": rows, "wybor_na_doborze": best, "wynik_testu_x": rows[best]["test"]["x"],
            "tylko_LONG_test_x": rows["tylko LONG"]["test"]["x"]}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", required=True)
    ap.add_argument("--dukascopy", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--capital", type=float, default=20_000.0)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    duk = load_dukascopy(args.dukascopy)
    d1 = daily_from_m15(load_broker_m15(args.broker, hourly_spread_profile(duk)))
    report = {"paper_trade": {}}
    for fin in FINANCING:
        for tv in (0.5, 0.3):
            for lo in (True, False):
                curve, log = paper_trade(d1, M.TrendParams(target_vol=tv, long_only=lo), "2005-01-01", args.capital,
                                         long_rate=fin[0], short_rate=fin[1])
                key = f"{'LONG' if lo else 'LONG i SHORT'}, cel {tv:.0%}, finansowanie LONG {fin[0]:+.1%} SHORT {fin[1]:+.1%}"
                report["paper_trade"][key] = {**summarize(curve, log, args.capital), "podzial": side_split(curve, args.capital)}
                s = report["paper_trade"][key]
                print(key, "->", s["kapital_koncowy"], f"x{s['mnoznik']}", f"spadek {s['najwiekszy_spadek_%']}%", s["podzial"], flush=True)
    report["reguly_short"] = rules_split(M.daily_frame(d1))
    for k, v in report["reguly_short"].items():
        print(k, "| wybór:", v["wybor_na_doborze"], "test x", v["wynik_testu_x"], "| tylko LONG test x", v["tylko_LONG_test_x"])
    with open(os.path.join(args.out, "longshort.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
