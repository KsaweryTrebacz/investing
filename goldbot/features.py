"""Cechy dzienne dla modelu i cel prognozy. Wszystko przyczynowe: wiersz t zna tylko dane do zamknięcia t."""
import numpy as np
import pandas as pd

from indicators import atr, ema, rsi
from regime import trend_dir

HORIZON = 10          # sesji do przodu
MACRO_LAG_DAYS = 1    # FRED/Yahoo publikują z opóźnieniem; wartość z dnia t jest znana dopiero t+1

FEATURES = ["ret_1", "ret_5", "ret_10", "ret_20", "ret_60", "dist_ema50", "dist_ema200", "rsi14",
            "vol20", "atr_pct", "range_pos250", "usd_chg5", "usd_chg20", "yld_chg5", "yld_chg20",
            "reg_trend", "reg_dollar", "reg_yields"]

FEATURES_PL = {
    "ret_1": "zwrot 1 sesji", "ret_5": "zwrot 5 sesji", "ret_10": "zwrot 10 sesji",
    "ret_20": "zwrot 20 sesji", "ret_60": "zwrot 60 sesji",
    "dist_ema50": "odległość od EMA 50", "dist_ema200": "odległość od EMA 200", "rsi14": "RSI 14",
    "vol20": "zmienność 20 sesji", "atr_pct": "ATR w % ceny", "range_pos250": "pozycja w zakresie roku",
    "usd_chg5": "zmiana dolara 5 sesji", "usd_chg20": "zmiana dolara 20 sesji",
    "yld_chg5": "zmiana realnych stóp 5 sesji", "yld_chg20": "zmiana realnych stóp 20 sesji",
    "reg_trend": "trend złota (reżim)", "reg_dollar": "dolar (reżim)", "reg_yields": "realne stopy (reżim)",
}


def _align_macro(s, days: pd.DatetimeIndex) -> pd.Series:
    """Ostatnia wartość makro znana w dniu sesji (z opóźnieniem publikacji), dopasowana wstecz."""
    if s is None or len(s) == 0:
        return pd.Series(np.nan, index=days)
    s = s.sort_index()
    s.index = pd.DatetimeIndex(s.index) + pd.Timedelta(days=MACRO_LAG_DAYS)
    return pd.Series(s.reindex(days, method="ffill").to_numpy(), index=days)


def build_features(gold: pd.DataFrame, usd=None, yld=None, horizon: int = HORIZON) -> pd.DataFrame:
    g = gold.sort_values("time").reset_index(drop=True)
    mid = {k: (g[f"bid_{k}"] + g[f"ask_{k}"]) / 2 for k in "ohlc"}
    close, high, low = mid["c"], mid["h"], mid["l"]
    days = pd.DatetimeIndex(g["time"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize())
    logc = np.log(close)

    f = pd.DataFrame({"time": g["time"]})
    for n in (1, 5, 10, 20, 60):
        f[f"ret_{n}"] = logc - logc.shift(n)
    f["dist_ema50"] = close / ema(close, 50) - 1
    f["dist_ema200"] = close / ema(close, 200) - 1
    f["rsi14"] = rsi(close, 14)
    f["vol20"] = logc.diff().rolling(20).std()
    a = atr(high, low, close, 14)
    f["atr_pct"] = a / close
    rng_hi, rng_lo = close.rolling(250).max(), close.rolling(250).min()
    f["range_pos250"] = (close - rng_lo) / (rng_hi - rng_lo).replace(0, np.nan)

    u, y = _align_macro(usd, days), _align_macro(yld, days)
    f["usd_chg5"] = (u - u.shift(5)).to_numpy()
    f["usd_chg20"] = (u - u.shift(20)).to_numpy()
    f["yld_chg5"] = (y - y.shift(5)).to_numpy()
    f["yld_chg20"] = (y - y.shift(20)).to_numpy()

    f["reg_trend"] = trend_dir(close, 50, 200).to_numpy()
    f["reg_dollar"] = (-trend_dir(u, 20, 50)).to_numpy() if usd is not None else np.nan
    f["reg_yields"] = (-trend_dir(y, 20, 50)).to_numpy() if yld is not None else np.nan

    f["close"] = close
    f["atr"] = a
    f["cost"] = (g["ask_c"] - g["bid_c"]) / close          # pełny spread jako ułamek ceny (wejście + wyjście)
    f["fwd_ret"] = logc.shift(-horizon) - logc
    f["y"] = (f["fwd_ret"] > f["cost"]).astype(float).where(f["fwd_ret"].notna())
    # rozgrzewka wskaźników: pierwsze 250 sesji nie ma pełnych cech
    out = f.set_index("time")
    out.index.name = "time"
    return out
