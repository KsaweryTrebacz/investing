"""Wskaźniki techniczne liczone czystym pandas/numpy (bez pandas-ta)."""
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI Wilder'a."""
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).fillna(100)


def macd_hist(close: pd.Series, fast=12, slow=26, signal=9) -> pd.Series:
    line = ema(close, fast) - ema(close, slow)
    return line - ema(line, signal)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """ATR Wilder'a."""
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP sesji liczonej od 00:00 UTC, z ceny typowej mid i wolumenu. NaN, gdy brak wolumenu."""
    if "volume" not in df or df["volume"].isna().all():
        return pd.Series(float("nan"), index=df.index)
    typical = sum((df[f"bid_{k}"] + df[f"ask_{k}"]) / 2 for k in "hlc") / 3
    day = df["time"].dt.tz_convert("UTC").dt.floor("D")
    vol = df["volume"]
    return (typical * vol).groupby(day).cumsum() / vol.groupby(day).cumsum().replace(0, float("nan"))


def volume_ratio(volume: pd.Series, n: int = 20) -> pd.Series:
    """Wolumen świecy względem średniej z `n` świec."""
    return volume / volume.rolling(n, min_periods=n).mean()
