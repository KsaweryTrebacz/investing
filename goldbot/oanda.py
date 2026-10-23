"""Klient OANDA REST-v20 (tylko odczyt, środowisko PRACTICE) oraz dane demo."""
import os

import numpy as np
import pandas as pd
import requests

HOSTS = {"practice": "https://api-fxpractice.oanda.com", "live": "https://api-fxtrade.oanda.com"}


class Oanda:
    def __init__(self):
        self.token = os.environ.get("OANDA_TOKEN")
        env = os.environ.get("OANDA_ENV", "practice")
        if env != "practice":
            raise SystemExit("Ten projekt celowo obsługuje tylko OANDA_ENV=practice.")
        if not self.token:
            raise SystemExit("Brak OANDA_TOKEN (ustaw zmienną środowiskową).")
        self.base = HOSTS[env]
        self.h = {"Authorization": f"Bearer {self.token}"}

    def _get(self, path, **params):
        r = requests.get(self.base + path, headers=self.h, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def candles(self, instrument="XAU_USD", granularity="M15", bars=5000) -> pd.DataFrame:
        """Ostatnie `bars` ZAMKNIĘTYCH świec z cenami bid i ask (paginacja wstecz po 5000)."""
        rows, to = [], None
        while len(rows) < bars:
            params = dict(granularity=granularity, price="BA", count=min(5000, bars - len(rows)))
            if to:
                params["to"] = to
            data = self._get(f"/v3/instruments/{instrument}/candles", **params)["candles"]
            data = [c for c in data if c["complete"]]
            if len(data) < 2 or data[0]["time"] == to:
                rows = data + rows
                break
            rows = data + rows
            to = data[0]["time"]
        recs = [{"time": pd.Timestamp(c["time"]),
                 **{f"bid_{k}": float(c["bid"][k]) for k in "ohlc"},
                 **{f"ask_{k}": float(c["ask"][k]) for k in "ohlc"},
                 "volume": float(c.get("volume", "nan"))} for c in rows]  # wolumen tickowy (liczba zmian ceny)
        return pd.DataFrame(recs).drop_duplicates("time").sort_values("time").reset_index(drop=True)


def demo_candles(bars=5000, seed=7) -> pd.DataFrame:
    """SYNTETYCZNE dane do testu działania kodu. Nie nadają się do oceny strategii."""
    rng = np.random.default_rng(seed)
    px = 2000 + np.cumsum(rng.normal(0, 1.2, bars) + 0.02 * np.sin(np.arange(bars) / 300))
    t = pd.date_range("2026-01-01", periods=bars, freq="15min", tz="UTC")
    o = np.r_[px[0], px[:-1]]
    hi = np.maximum(o, px) + rng.random(bars) * 0.8
    lo = np.minimum(o, px) - rng.random(bars) * 0.8
    half = 0.17  # spread ~0.34 USD
    d = {"time": t}
    for k, v in zip("ohlc", (o, hi, lo, px)):
        d[f"bid_{k}"], d[f"ask_{k}"] = v - half, v + half
    d["volume"] = np.random.default_rng(seed + 1).integers(50, 500, bars).astype(float)  # osobny generator: ceny bez zmian
    return pd.DataFrame(d)


def demo_daily(m15: pd.DataFrame) -> pd.DataFrame:
    """Świece dzienne zagregowane ze świec M15 (dane demo)."""
    agg = {}
    for side in ("bid", "ask"):
        agg.update({f"{side}_o": "first", f"{side}_h": "max", f"{side}_l": "min", f"{side}_c": "last"})
    if "volume" in m15:
        agg["volume"] = "sum"
    return m15.set_index("time").resample("1D").agg(agg).dropna().reset_index()


def demo_macro(d1: pd.DataFrame, seed=11):
    """Dwa syntetyczne szeregi (dolar, rentowności) z naiwnym indeksem dat."""
    rng = np.random.default_rng(seed)
    idx = pd.DatetimeIndex(d1["time"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize())
    usd = pd.Series(100 + np.cumsum(rng.normal(0, 0.3, len(idx))), index=idx)
    yld = pd.Series(1.5 + np.cumsum(rng.normal(0, 0.03, len(idx))), index=idx)
    return usd, yld
