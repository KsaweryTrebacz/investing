"""Klient OANDA REST-v20. Domyślnie wyłącznie środowisko PRACTICE."""
import os

import numpy as np
import pandas as pd
import requests

HOSTS = {"practice": "https://api-fxpractice.oanda.com", "live": "https://api-fxtrade.oanda.com"}


class Oanda:
    def __init__(self):
        self.token = os.environ.get("OANDA_TOKEN")
        self.account = os.environ.get("OANDA_ACCOUNT_ID")
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
            if not data:
                break
            rows = data + rows
            to = data[0]["time"]
            if len(data) < 2:
                break
        recs = [{"time": pd.Timestamp(c["time"]),
                 **{f"bid_{k}": float(c["bid"][k]) for k in "ohlc"},
                 **{f"ask_{k}": float(c["ask"][k]) for k in "ohlc"}} for c in rows]
        return pd.DataFrame(recs).drop_duplicates("time").sort_values("time").reset_index(drop=True)

    def spread(self, instrument="XAU_USD") -> float:
        pr = self._get(f"/v3/accounts/{self.account}/pricing", instruments=instrument)["prices"][0]
        return float(pr["asks"][0]["price"]) - float(pr["bids"][0]["price"])

    def market_order(self, instrument, units, sl, tp):
        """Zlecenie rynkowe z SL/TP (units>0 = LONG, <0 = SHORT)."""
        body = {"order": {
            "type": "MARKET", "instrument": instrument, "units": str(units),
            "timeInForce": "FOK", "positionFill": "DEFAULT",
            "stopLossOnFill": {"price": f"{sl:.3f}"},
            "takeProfitOnFill": {"price": f"{tp:.3f}"}}}
        r = requests.post(f"{self.base}/v3/accounts/{self.account}/orders",
                          headers=self.h, json=body, timeout=30)
        r.raise_for_status()
        return r.json()


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
    return pd.DataFrame(d)
