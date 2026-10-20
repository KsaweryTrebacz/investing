from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from mt5_source import MT5Error, MT5Source

RATE_DTYPE = [("time", "<i8"), ("open", "<f8"), ("high", "<f8"), ("low", "<f8"), ("close", "<f8"),
              ("tick_volume", "<u8"), ("spread", "<i4"), ("real_volume", "<u8")]
# Czas serwera = UTC + 2 h. Świece serwera 12:00, 12:15, 12:30 to 10:00, 10:15, 10:30 UTC.
SERVER_T0 = int(pd.Timestamp("2026-01-05 12:00", tz="UTC").timestamp())


def rates():
    rows = [(SERVER_T0 + 900 * i, 2000.0 + i, 2001.0 + i, 1999.0 + i, 2000.5 + i, 10, 30, 0) for i in range(3)]
    return np.array(rows, dtype=RATE_DTYPE)


class FakeMT5:
    TIMEFRAME_M15 = 15
    TIMEFRAME_D1 = 16408

    def __init__(self, init_ok=True, symbol_ok=True, visible=True):
        self.init_ok, self.symbol_ok, self.visible = init_ok, symbol_ok, visible
        self.closed = False

    def initialize(self, *args):
        return self.init_ok

    def last_error(self):
        return (-1, "fake error")

    def symbol_info(self, symbol):
        return SimpleNamespace(point=0.01, visible=self.visible) if self.symbol_ok else None

    def symbols_get(self, pattern):
        return [SimpleNamespace(name="XAUUSD.pro")]

    def copy_rates_from_pos(self, symbol, tf, pos, count):
        return rates()[-count:]

    def shutdown(self):
        self.closed = True


def source(now="2026-01-05 10:40", **fake):
    return MT5Source(mt5=FakeMT5(**fake), symbol="XAUUSD", offset_hours=2.0,
                     now=lambda: pd.Timestamp(now, tz="UTC"))


def test_converts_server_time_and_drops_forming_bar():
    df = source().candles("XAU_USD", "M15", 10)
    assert len(df) == 2  # świeca 10:30 UTC jeszcze trwa
    assert df.time.tolist() == list(pd.to_datetime(["2026-01-05 10:00", "2026-01-05 10:15"], utc=True))


def test_ask_is_bid_plus_spread_in_points():
    df = source().candles("XAU_USD", "M15", 10)
    assert df.bid_c.iloc[0] == 2000.5
    assert abs(df.ask_c.iloc[0] - (2000.5 + 30 * 0.01)) < 1e-9
    assert (df.ask_l > df.bid_l).all()


def test_candles_in_the_future_mean_wrong_offset():
    with pytest.raises(MT5Error, match="MT5_SERVER_OFFSET_HOURS"):
        source(now="2026-01-05 09:00").candles("XAU_USD", "M15", 10)


def test_missing_offset_env_is_an_error(monkeypatch):
    monkeypatch.delenv("MT5_SERVER_OFFSET_HOURS", raising=False)
    with pytest.raises(MT5Error, match="MT5_SERVER_OFFSET_HOURS"):
        MT5Source(mt5=FakeMT5(), symbol="XAUUSD")


def test_unknown_symbol_lists_similar_names():
    with pytest.raises(MT5Error, match="XAUUSD.pro"):
        source(symbol_ok=False)


def test_symbol_must_be_in_market_watch():
    with pytest.raises(MT5Error, match="Obserwacj"):
        source(visible=False)


def test_terminal_not_running():
    with pytest.raises(MT5Error, match="terminal"):
        source(init_ok=False)


def test_close_shuts_down_terminal_connection():
    s = source()
    s.close()
    assert s.mt5.closed
