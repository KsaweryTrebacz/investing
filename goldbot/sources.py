"""Źródła danych dziennych: darmowe (Yahoo Finance + FRED CSV) albo OANDA Practice. Tylko odczyt.

Oba źródła zwracają ten sam kształt (DailyData), więc model i doradca nie wiedzą, skąd są dane.
"""
import json
import os
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
UA = {"User-Agent": "Mozilla/5.0 (goldbot; read-only research)"}

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={years}y"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
GOLD_SYMBOL = "GC=F"        # kontrakt na złoto COMEX, najbliższa seria (proxy spotu XAU/USD)
USD_SYMBOL = "DX-Y.NYB"     # indeks dolara ICE
YIELD_SERIES = "DFII10"     # realne rentowności 10Y (TIPS)
USD_SERIES = "DTWEXBGS"     # szeroki indeks dolara (gdy brak Yahoo)
HALF_SPREAD = 0.25          # typowy spread OANDA na XAU/USD to ok. 0,5 USD
PRICE_COLS = [f"{s}_{k}" for s in ("bid", "ask") for k in "ohlc"]


@dataclass
class DailyData:
    gold: pd.DataFrame            # time (UTC) + bid_*/ask_* (o,h,l,c)
    usd: pd.Series | None         # naiwny indeks dat
    yld: pd.Series | None
    source: str
    warnings: list = field(default_factory=list)


# --- sieć i pamięć podręczna -------------------------------------------------

def http_get(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.text


def save_cache(name: str, text: str):
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, name), "w", encoding="utf-8") as f:
        f.write(text)


def load_cache(name: str):
    """(tekst, wiek w dniach) albo (None, None)."""
    p = os.path.join(CACHE, name)
    if not os.path.exists(p):
        return None, None
    with open(p, encoding="utf-8") as f:
        return f.read(), (time.time() - os.path.getmtime(p)) / 86400


def fetch_text(url: str, name: str, offline: bool, warnings: list) -> str:
    """Pobiera i zapisuje do cache. Offline albo przy awarii sieci używa cache (z ostrzeżeniem)."""
    if not offline:
        try:
            text = http_get(url)
            save_cache(name, text)
            return text
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Nie pobrano {name} ({e}).")
    text, age = load_cache(name)
    if text is None:
        raise RuntimeError(f"Brak danych {name}: sieć niedostępna i brak pamięci podręcznej.")
    warnings.append(f"Dane {name} z pamięci podręcznej sprzed {age:.1f} dnia.")
    return text


# --- parsowanie --------------------------------------------------------------

def parse_yahoo_chart(payload: dict) -> pd.DataFrame:
    res = payload["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({"time": pd.to_datetime(res["timestamp"], unit="s", utc=True),
                       **{k: pd.to_numeric(pd.Series(q[k], dtype="float64"), errors="coerce")
                          for k in ("open", "high", "low", "close")}})
    df = df.dropna().drop_duplicates("time").sort_values("time").reset_index(drop=True)
    # sesja dzienna: zostaw samą datę (Yahoo daje czas otwarcia sesji)
    df["time"] = df["time"].dt.normalize()
    return df.drop_duplicates("time", keep="last").reset_index(drop=True)


def parse_fred_csv(text: str) -> pd.Series:
    rows = []
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        d, v = line.split(",")[:2]
        if v.strip() in (".", ""):
            continue
        rows.append((pd.Timestamp(d), float(v)))
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]), dtype=float)


def with_spread(ohlc: pd.DataFrame, half: float = HALF_SPREAD) -> pd.DataFrame:
    """OHLC (mid) -> kolumny bid_*/ask_* z symetrycznym spreadem."""
    out = pd.DataFrame({"time": ohlc["time"]})
    for k in "ohlc":
        col = {"o": "open", "h": "high", "l": "low", "c": "close"}[k]
        out[f"bid_{k}"] = ohlc[col] - half
        out[f"ask_{k}"] = ohlc[col] + half
    return out


def to_naive_series(df: pd.DataFrame) -> pd.Series:
    """Zamknięcia Yahoo jako Series z naiwnym indeksem dat (jak FRED)."""
    idx = pd.DatetimeIndex(df["time"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize())
    return pd.Series(df["close"].to_numpy(), index=idx, dtype=float)


# --- wybór i kontrola --------------------------------------------------------

def pick_source(name: str, env=None) -> str:
    env = os.environ if env is None else env
    if name == "auto":
        return "oanda" if env.get("OANDA_TOKEN") else "free"
    if name in ("free", "oanda"):
        return name
    raise ValueError(f"Nieznane źródło: {name} (dozwolone: auto, free, oanda)")


SESSION_CLOSE_UTC = 23  # po tej godzinie UTC świeca dzienna złota (COMEX/Yahoo) jest zamknięta


def drop_incomplete(df: pd.DataFrame, now=None) -> pd.DataFrame:
    """Usuwa ostatnią świecę dzienną, jeśli jej sesja jeszcze trwa (Yahoo zwraca bieżący dzień w toku)."""
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now).tz_convert("UTC")
    if df.empty:
        return df
    last_day = df["time"].iloc[-1].tz_convert("UTC").normalize()
    if now < last_day + pd.Timedelta(hours=SESSION_CLOSE_UTC):
        return df.iloc[:-1].reset_index(drop=True)
    return df


def is_daily_stale(last_time, now) -> bool:
    """Ostatnia świeca dzienna jest nieaktualna, gdy między nią a `now` minął więcej niż jeden
    dzień sesyjny bez świecy (np. piątkowa świeca w środę). Weekend się nie liczy."""
    last_day = pd.Timestamp(last_time).tz_convert("UTC").normalize().tz_localize(None)
    today = pd.Timestamp(now).tz_convert("UTC").normalize().tz_localize(None)
    # dni robocze w przedziale (last_day, today) wyłącznie; dziś może nie mieć jeszcze świecy
    missing = len(pd.bdate_range(last_day + pd.Timedelta(days=1), today - pd.Timedelta(days=1)))
    return missing > 1


def cross_check(gold_bidask: pd.DataFrame, yahoo: pd.DataFrame, n: int = 20, limit: float = 0.02):
    """Porównanie ostatnich n zamknięć OANDA (mid) z Yahoo. Ostrzeżenie, gdy mediana różnicy > limit."""
    a = gold_bidask.assign(mid=(gold_bidask["bid_c"] + gold_bidask["ask_c"]) / 2)
    a = a.assign(day=a["time"].dt.normalize()).set_index("day")["mid"]
    b = yahoo.assign(day=yahoo["time"].dt.normalize()).set_index("day")["close"]
    both = pd.concat([a, b], axis=1, join="inner").tail(n)
    if both.empty:
        return "Brak wspólnych dni do porównania źródeł."
    gap = float(((both.iloc[:, 1] - both.iloc[:, 0]).abs() / both.iloc[:, 0]).median())
    if gap > limit:
        return f"Rozjazd cen OANDA i Yahoo: mediana {100 * gap:.1f}% w ostatnich {len(both)} sesjach."
    return None


# --- źródła ------------------------------------------------------------------

class FreeSource:
    """Yahoo Finance (GC=F, DX-Y.NYB) + FRED CSV bez klucza. Prawdziwe dane, zero kont."""
    name = "free"

    def __init__(self, offline: bool = False, now=None):
        self.offline = offline
        self.now = now

    def fetch_daily(self, years: int = 15) -> DailyData:
        w = []
        gold = drop_incomplete(parse_yahoo_chart(json.loads(fetch_text(
            YAHOO.format(symbol=GOLD_SYMBOL, years=years), "gold.json", self.offline, w))), self.now)
        usd = yld = None
        try:
            usd = to_naive_series(parse_yahoo_chart(json.loads(
                fetch_text(YAHOO.format(symbol=USD_SYMBOL, years=years), "usd.json", self.offline, w))))
        except Exception as e:  # noqa: BLE001
            w.append(f"Brak indeksu dolara ({e}); cechy dolara będą puste.")
        try:
            yld = parse_fred_csv(fetch_text(FRED_CSV.format(series=YIELD_SERIES), "yld.csv", self.offline, w))
        except Exception as e:  # noqa: BLE001
            w.append(f"Brak realnych rentowności ({e}); cechy stóp będą puste.")
        w.append("Ceny złota to kontrakt GC=F (Yahoo), nie kwotowanie OANDA; spread przyjęty 0,50 USD.")
        return DailyData(with_spread(gold), usd, yld, "free", w)


class OandaSource:
    """Świece D z OANDA Practice (bid/ask). Makro z FRED CSV. Yahoo jako kontrola krzyżowa."""
    name = "oanda"

    def __init__(self, offline: bool = False):
        from oanda import Oanda
        self.api = Oanda()
        self.offline = offline

    def fetch_daily(self, years: int = 15) -> DailyData:
        w = []
        gold = self.api.candles("XAU_USD", "D", int(years * 262))
        gold["time"] = gold["time"].dt.tz_convert("UTC").dt.normalize()
        gold = gold.drop_duplicates("time", keep="last").reset_index(drop=True)
        free = FreeSource(self.offline)
        usd = yld = None
        try:
            usd = to_naive_series(parse_yahoo_chart(json.loads(
                fetch_text(YAHOO.format(symbol=USD_SYMBOL, years=years), "usd.json", self.offline, w))))
            yahoo_gold = parse_yahoo_chart(json.loads(
                fetch_text(YAHOO.format(symbol=GOLD_SYMBOL, years=years), "gold.json", self.offline, w)))
            warn = cross_check(gold, yahoo_gold)
            if warn:
                w.append(warn)
        except Exception as e:  # noqa: BLE001
            w.append(f"Brak danych Yahoo ({e}); bez indeksu dolara i kontroli krzyżowej.")
        try:
            yld = parse_fred_csv(fetch_text(FRED_CSV.format(series=YIELD_SERIES), "yld.csv", self.offline, w))
        except Exception as e:  # noqa: BLE001
            w.append(f"Brak realnych rentowności ({e}); cechy stóp będą puste.")
        del free
        return DailyData(gold[["time", *PRICE_COLS]], usd, yld, "oanda", w)


def make_source(name: str, offline: bool = False):
    chosen = pick_source(name)
    return OandaSource(offline) if chosen == "oanda" else FreeSource(offline)
