"""Świece XAU/USD z terminala MetaTrader 5 (np. OANDA TMS). Tylko odczyt, bez zleceń.

Terminal musi być uruchomiony i ręcznie zalogowany. Program się do niego tylko podłącza,
więc nie potrzebuje hasła. Czas w MT5 jest w strefie serwera brokera, dlatego przesunięcie
względem UTC trzeba podać w MT5_SERVER_OFFSET_HOURS.
"""
import os

import pandas as pd

TIMEFRAMES = {"M15": ("TIMEFRAME_M15", 900), "D": ("TIMEFRAME_D1", 86400)}


class MT5Error(RuntimeError):
    pass


def _offset_from_env() -> float:
    raw = os.environ.get("MT5_SERVER_OFFSET_HOURS", "").strip()
    if not raw:
        raise MT5Error("Brak MT5_SERVER_OFFSET_HOURS: podaj przesunięcie czasu serwera MT5 względem UTC "
                       "w godzinach (np. 2 zimą, 3 latem dla serwerów GMT+2/+3).")
    return float(raw)


def rates_to_frame(rates, point: float, offset_hours: float, tf_seconds: int, now_utc) -> pd.DataFrame:
    """Tablica z copy_rates_* -> ramka bid_*/ask_* w UTC, tylko świece zamknięte przed `now_utc`."""
    df = pd.DataFrame(rates)
    t = pd.to_datetime(df["time"], unit="s", utc=True) - pd.Timedelta(hours=offset_hours)
    if t.iloc[-1] > now_utc + pd.Timedelta(minutes=1):
        raise MT5Error(f"Świeca z {t.iloc[-1]} jest w przyszłości. Sprawdź MT5_SERVER_OFFSET_HOURS "
                       f"(obecnie {offset_hours}).")
    closed = ((t + pd.Timedelta(seconds=tf_seconds)) <= now_utc).to_numpy()
    df, t = df[closed].reset_index(drop=True), t[closed].reset_index(drop=True)
    spread = df["spread"].to_numpy() * point  # MT5 podaje spread świecy w punktach, ceny OHLC są po BID
    out = pd.DataFrame({"time": t})
    for k, col in zip("ohlc", ("open", "high", "low", "close")):
        out[f"bid_{k}"] = df[col].to_numpy(dtype=float)
        out[f"ask_{k}"] = df[col].to_numpy(dtype=float) + spread
    return out.drop_duplicates("time").sort_values("time").reset_index(drop=True)


class MT5Source:
    def __init__(self, mt5=None, symbol=None, offset_hours=None, now=None):
        if mt5 is None:
            try:
                import MetaTrader5 as mt5
            except ImportError:
                raise MT5Error("Brak pakietu MetaTrader5 (python -m pip install MetaTrader5).") from None
        self.mt5 = mt5
        self.symbol = symbol or os.environ.get("MT5_GOLD_SYMBOL", "XAUUSD")
        self.offset = _offset_from_env() if offset_hours is None else float(offset_hours)
        self._now = now or (lambda: pd.Timestamp.now(tz="UTC"))

        path = os.environ.get("MT5_TERMINAL_PATH")
        if not (mt5.initialize(path) if path else mt5.initialize()):
            raise MT5Error(f"Brak połączenia z terminalem MT5 ({mt5.last_error()}). "
                           "Uruchom terminal i zaloguj się ręcznie.")
        info = mt5.symbol_info(self.symbol)
        if info is None:
            similar = [s.name for s in (mt5.symbols_get("*XAU*") or [])][:10]
            raise MT5Error(f"Symbol '{self.symbol}' nie istnieje u brokera. Podobne: {similar}. "
                           "Ustaw MT5_GOLD_SYMBOL.")
        if not info.visible:
            raise MT5Error(f"Symbol '{self.symbol}' nie jest w oknie Obserwacja rynku. Dodaj go w MT5 (Ctrl+U).")
        self.point = float(info.point)

    def candles(self, instrument=None, granularity="M15", bars=5000) -> pd.DataFrame:
        """Ten sam format co Oanda.candles. `instrument` jest ignorowany (symbol z MT5_GOLD_SYMBOL)."""
        const, secs = TIMEFRAMES[granularity]
        rates = self.mt5.copy_rates_from_pos(self.symbol, getattr(self.mt5, const), 0, bars + 1)
        if rates is None or len(rates) == 0:
            raise MT5Error(f"Brak świec {self.symbol} {granularity} ({self.mt5.last_error()}).")
        return rates_to_frame(rates, self.point, self.offset, secs, self._now())

    def close(self):
        self.mt5.shutdown()
