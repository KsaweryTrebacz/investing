import pandas as pd

from config import Costs
from resolve import resolve, stop_fill

T0 = pd.Timestamp("2026-01-05 10:00", tz="UTC")


def candles(rows):
    """rows: (h, l, c) albo (o, h, l, c); mid, spread 0. Bez open świeca otwiera się na poprzednim zamknięciu."""
    out, prev = [], 100.0
    for i, r in enumerate(rows, start=1):
        o, h, l, c = r if len(r) == 4 else (prev, *r)
        out.append({"time": T0 + pd.Timedelta(minutes=15 * i),
                    **{f"{s}_{k}": v for s in ("bid", "ask") for k, v in zip("ohlc", (o, h, l, c))}})
        prev = c
    return pd.DataFrame(out)


BUY = {"time": T0.isoformat(), "verdict": "KUP", "entry": 100.0, "sl": 98.0, "tp": 104.0, "atr": 4 / 3}
SELL = {"time": T0.isoformat(), "verdict": "SPRZEDAJ", "entry": 100.0, "sl": 102.0, "tp": 96.0, "atr": 4 / 3}


def test_buy_take_profit():
    s, r, _, cost = resolve(BUY, candles([(101, 99.5, 100), (104.5, 100, 104)]))
    assert s == "TP" and r == 2.0 and cost is None  # bez profilu kosztów koszt nieznany


def test_buy_stop_loss():
    s, r, _, _ = resolve(BUY, candles([(101, 97.5, 98)]))
    assert s == "SL" and r == -1.0


def test_gap_through_stop_fills_at_open():
    s, r, _, _ = resolve(BUY, candles([(97.0, 97.5, 96.5, 97.0)]))  # luka: otwarcie 97 poniżej SL 98
    assert s == "SL" and abs(r + 1.5) < 1e-9


def test_slippage_and_costs_in_r():
    c = Costs(commission_per_unit=0.05, financing_long_rate=0.0, slippage_atr=0.15)
    s, r, _, cost = resolve(BUY, candles([(101, 97.5, 98)]), costs=c)
    assert s == "SL" and abs(r + 1.1) < 1e-9       # poślizg 0,2 = 0,15 ATR
    assert abs(cost - 0.05) < 1e-9                 # prowizja 0,1 / ryzyko 2


def test_stop_fill_short_side():
    assert stop_fill(-1, 103.0, 103.5, 102.0) == 103.0
    assert stop_fill(-1, 101.0, 102.5, 102.0, 0.1) == 102.1
    assert stop_fill(-1, 101.0, 101.5, 102.0) is None


def test_both_in_one_candle_takes_stop_loss():
    assert resolve(BUY, candles([(105, 97, 100)]))[0] == "SL"


def test_sell_take_profit_and_stop():
    assert resolve(SELL, candles([(100.5, 95.5, 96)]))[0] == "TP"
    assert resolve(SELL, candles([(102.5, 99, 101)]))[0] == "SL"


def test_still_open_returns_none():
    assert resolve(BUY, candles([(101, 99.5, 100)] * 5)) is None


def test_expires_after_48h():
    rows = [(101, 99, 101)] * 200  # 50 godzin spokojnych świec
    s, r, _, _ = resolve(BUY, candles(rows))
    assert s == "EXPIRED" and abs(r - 0.5) < 1e-9  # (101-100)/2


def test_ignores_candles_before_verdict():
    early = candles([(110, 90, 100)])
    early["time"] = T0 - pd.Timedelta(minutes=15)
    assert resolve(BUY, early) is None
