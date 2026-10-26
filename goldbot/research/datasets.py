"""Publiczne notowania złota do badań: wczytanie, czas UTC, model spreadu, świece dzienne.

Źródła (pobierane skryptem research/download.sh, nie trafiają do repozytorium):
- BaseMax/XAUUSD-LSTM: M15 od 2004 r., jedna cena (bid), czas serwera brokera.
  ejtraderLabs/historical-data i parshant65 (M1 2020-2025) to ten sam strumień notowań.
- FX-Data/FX-Data-XAUUSD-DS: ticki Dukascopy 2011-2018 z bid i ask, czas GMT (niezależne źródło).

Czas serwera brokera to czas nowojorski przesunięty o stałą liczbę godzin, zmienną między latami.
Przesunięcie wyznacza się z danych: skok zmienności po publikacji NFP (8:30 Nowy Jork, pierwszy piątek).
"""
import glob
import os

import numpy as np
import pandas as pd

NY = "America/New_York"


def load_mt_csv(path: str) -> pd.DataFrame:
    """CSV z MetaTradera: BaseMax (Date;Open;...;Volume) albo ejtrader (Date,open,...,tick_volume, ceny x100)."""
    with open(path, encoding="utf-8") as f:
        head = f.readline()
    df = pd.read_csv(path, sep=";" if ";" in head else ",")
    df.columns = [c.lower() for c in df.columns]
    t = df["date"].astype(str)
    df["time"] = pd.to_datetime(t, format="%Y.%m.%d %H:%M" if "." in t.iloc[0][:5] else "%Y-%m-%d %H:%M:%S")
    if df["close"].median() > 20_000:  # ejtrader zapisuje ceny w setnych
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] / 100
    vol = "tick_volume" if "tick_volume" in df else "volume"
    return df.rename(columns={vol: "volume"})[["time", "open", "high", "low", "close", "volume"]]


def nfp_offsets(df: pd.DataFrame) -> pd.Series:
    """Przesunięcie czasu serwera względem Nowego Jorku (godziny) w każdym roku, z dni NFP.

    W pierwszy piątek miesiąca szukamy świecy o największym zakresie między 12:00 a 20:00 czasu
    serwera i porównujemy z 8:30 w Nowym Jorku. Wynik: najczęstsza wartość w roku.
    """
    d = df.assign(rng=df["high"] - df["low"], day=df["time"].dt.normalize())
    first_fridays = d[(d["time"].dt.weekday == 4) & (d["time"].dt.day <= 7)]
    window = first_fridays[first_fridays["time"].dt.hour.between(12, 19)]
    spikes = window.loc[window.groupby("day")["rng"].idxmax()]
    hours = (spikes["time"] - spikes["day"]).dt.total_seconds() / 3600 - 8.5
    yearly = hours.round().groupby(spikes["time"].dt.year).agg(lambda s: s.mode().iloc[0])
    # pojedynczy rok odstający od obu sąsiadów to szum (np. inne wydarzenie mocniejsze niż NFP)
    smooth = yearly.rolling(3, center=True, min_periods=1).median()
    return smooth.round().astype(int)


def server_to_utc(df: pd.DataFrame, offsets: pd.Series) -> pd.DataFrame:
    """Czas serwera -> UTC: odejmij przesunięcie roku i potraktuj wynik jako czas nowojorski."""
    nearest = lambda y: offsets.get(y, offsets.iloc[np.abs(offsets.index.values - y).argmin()])  # noqa: E731
    off = df["time"].dt.year.map(nearest)
    local = (df["time"] - pd.to_timedelta(off, unit="h")).dt.tz_localize(NY, ambiguous="NaT", nonexistent="NaT")
    out = df.assign(time=local.dt.tz_convert("UTC")).dropna(subset=["time"])
    return out.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def hourly_spread_profile(dukascopy: pd.DataFrame) -> pd.Series:
    """Mediana spreadu względem ceny (ułamek) w każdej godzinie UTC, z prawdziwych bid/ask."""
    rel = (dukascopy["ask_c"] - dukascopy["bid_c"]) / dukascopy["bid_c"]
    return rel.groupby(dukascopy["time"].dt.hour).median()


def with_spread(df: pd.DataFrame, profile: pd.Series, mult: float = 1.0) -> pd.DataFrame:
    """Jedna cena (bid z wykresu) -> bid/ask: ask = bid + spread(godzina UTC) x cena x mult."""
    rel = df["time"].dt.hour.map(profile).fillna(profile.median()) * mult
    out = pd.DataFrame({"time": df["time"]})
    for k, c in zip("ohlc", ("open", "high", "low", "close")):
        out[f"bid_{k}"] = df[c].values
        out[f"ask_{k}"] = (df[c] * (1 + rel)).values
    out["volume"] = df["volume"].astype(float).values
    return out


def load_broker_m15(path: str, profile: pd.Series, end: str | None = "2025-03-22", spread_mult: float = 1.0):
    """Zbiór BaseMax: czas UTC, bid/ask z modelu spreadu. `end` odcina okres z dużymi lukami w 2025 r."""
    raw = load_mt_csv(path)
    utc = server_to_utc(raw, nfp_offsets(raw))
    if end:
        utc = utc[utc["time"] < pd.Timestamp(end, tz="UTC")]
    return with_spread(utc, profile, spread_mult)


def load_dukascopy(directory: str) -> pd.DataFrame:
    """Świece M15 bid/ask z plików XAUUSD_<rok>.csv (ceny w repo FX-Data są podzielone przez 100)."""
    parts = [pd.read_csv(f, parse_dates=["time"]) for f in sorted(glob.glob(os.path.join(directory, "XAUUSD_*.csv")))]
    df = pd.concat(parts, ignore_index=True)
    out = pd.DataFrame({"time": pd.to_datetime(df["time"], utc=True)})
    for side in ("bid", "ask"):
        for k, name in zip("ohlc", ("open", "high", "low", "close")):
            out[f"{side}_{k}"] = df[f"{side}_{name}"] * 100
    out["volume"] = df["volume"].astype(float)
    out = out[(out["ask_c"] >= out["bid_c"]) & (out["bid_h"] >= out["bid_l"])]
    return out.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def daily_from_m15(m15: pd.DataFrame) -> pd.DataFrame:
    """Świece dzienne jak w OANDA: dzień handlowy od 17:00 do 17:00 w Nowym Jorku, czas = początek dnia (UTC)."""
    ny = m15["time"].dt.tz_convert(NY)
    day = (ny + pd.Timedelta(hours=7)).dt.normalize().dt.tz_localize(None)
    agg = {f"{s}_{k}": f for s in ("bid", "ask") for k, f in zip("ohlc", ("first", "max", "min", "last"))}
    agg["volume"] = "sum"
    d1 = m15.groupby(day).agg(agg)
    start = (pd.DatetimeIndex(d1.index) - pd.Timedelta(hours=7)).tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward")
    d1.index = start.tz_convert("UTC")
    d1 = d1[d1.index.notna()]
    return d1.rename_axis("time").reset_index()
