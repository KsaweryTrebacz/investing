"""Strategia 'Wybicie z Korekty': EMA200 (kierunek) -> RSI (korekta) -> MACD hist (zapłon)."""
from dataclasses import dataclass

import pandas as pd

from indicators import atr, ema, macd_hist, rsi
from regime import REGIME_BUY, REGIME_SELL


@dataclass
class Params:
    ema_len: int = 200
    rsi_len: int = 14
    rsi_long: float = 40.0      # LONG: RSI spadło poniżej i wróciło powyżej tego poziomu
    rsi_short: float = 60.0     # SHORT: lustrzanie (założenie, spec opisuje tylko LONG)
    arm_bars: int = 10          # ile świec po sygnale RSI czekamy na MACD (założenie)
    atr_len: int = 14
    sl_atr: float = 1.5
    tp_atr: float = 3.0         # RRR 1:2
    max_spread_atr: float = 0.25  # pomiń wejście, gdy spread > 25% ATR (założenie)
    risk_per_trade: float = 0.01  # 1% kapitału na transakcję (założenie)


def add_signals(df: pd.DataFrame, p: Params = Params()) -> pd.DataFrame:
    """df: kolumny bid_*/ask_* (o,h,l,c). Dodaje ema, rsi, hist, atr, signal (+1/-1/0).

    Sygnał dotyczy ZAMKNIĘTEJ świecy; wejście następuje dopiero na otwarciu kolejnej.
    """
    out = df.copy()
    for k in "ohlc":
        out[f"mid_{k}"] = (out[f"bid_{k}"] + out[f"ask_{k}"]) / 2
    c = out["mid_c"]
    out["ema"] = ema(c, p.ema_len)
    out["rsi"] = rsi(c, p.rsi_len)
    out["hist"] = macd_hist(c)
    out["atr"] = atr(out["mid_h"], out["mid_l"], c, p.atr_len)

    r, r1 = out["rsi"], out["rsi"].shift(1)
    arm_long = ((r1 < p.rsi_long) & (r >= p.rsi_long)).astype(int).rolling(p.arm_bars, min_periods=1).max() > 0
    arm_short = ((r1 > p.rsi_short) & (r <= p.rsi_short)).astype(int).rolling(p.arm_bars, min_periods=1).max() > 0
    h, h1 = out["hist"], out["hist"].shift(1)
    cross_up = (h1 <= 0) & (h > 0)
    cross_dn = (h1 >= 0) & (h < 0)

    long_ = (c > out["ema"]) & arm_long & cross_up
    short_ = (c < out["ema"]) & arm_short & cross_dn
    out["signal"] = 0
    out.loc[long_, "signal"] = 1
    out.loc[short_, "signal"] = -1
    out.iloc[: p.ema_len, out.columns.get_loc("signal")] = 0  # rozgrzewka EMA200
    return out


def gate_by_regime(df: pd.DataFrame) -> pd.DataFrame:
    """LONG tylko w reżimie kupna, SHORT tylko w reżimie sprzedaży. Surowy sygnał zostaje w signal_raw."""
    out = df.copy()
    out["signal_raw"] = out["signal"]
    ok = ((out["signal"] == 1) & (out["regime"] == REGIME_BUY)) | \
         ((out["signal"] == -1) & (out["regime"] == REGIME_SELL))
    out["signal"] = out["signal"].where(ok, 0)
    return out
