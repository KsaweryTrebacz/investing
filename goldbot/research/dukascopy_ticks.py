"""Ticki Dukascopy (repo FX-Data/FX-Data-XAUUSD-DS) -> świece M15 bid/ask i liczba ticków.

Użycie: python -I dukascopy_ticks.py <katalog_sklonowanego_roku> <plik_wyjściowy.csv>
Ceny w repozytorium są podzielone przez 100 (research.datasets.load_dukascopy to koryguje).
"""
import glob
import sys

import pandas as pd

src, out = sys.argv[1], sys.argv[2]
parts = []
for month in sorted(glob.glob(f"{src}/XAUUSD/*/*")):
    frames = [pd.read_csv(f, header=None, names=["t", "c1", "c2", "v1", "v2"]) for f in sorted(glob.glob(f"{month}/*.csv"))]
    if not frames:
        continue
    df = pd.concat(frames, ignore_index=True)
    df["t"] = pd.to_datetime(df["t"], format="%Y.%m.%d %H:%M:%S.%f", utc=True)
    bid, ask = df[["c1", "c2"]].min(axis=1), df[["c1", "c2"]].max(axis=1)
    swapped = (df["c1"] > df["c2"]).mean()
    g = pd.DataFrame({"bid": bid.values, "ask": ask.values}, index=df["t"]).resample("15min", label="left", closed="left")
    m = pd.concat([g["bid"].ohlc().add_prefix("bid_"), g["ask"].ohlc().add_prefix("ask_"), g["bid"].count().rename("volume")], axis=1)
    m = m[m["volume"] > 0]
    parts.append(m)
    print(month[-7:], len(df), "ticków, kolumna1>kolumna2:", f"{swapped:.4f}", flush=True)
res = pd.concat(parts)
res.index.name = "time"
res.to_csv(out)
print("zapisano", out, len(res))
