import pandas as pd

from resolve import resolve

T0 = pd.Timestamp("2026-01-05 10:00", tz="UTC")


def candles(rows):
    out = []
    for i, (h, l, c) in enumerate(rows, start=1):  # mid, spread 0
        out.append({"time": T0 + pd.Timedelta(minutes=15 * i), "bid_h": h, "bid_l": l, "bid_c": c,
                    "ask_h": h, "ask_l": l, "ask_c": c})
    return pd.DataFrame(out)


BUY = {"time": T0.isoformat(), "verdict": "KUP", "entry": 100.0, "sl": 98.0, "tp": 104.0}
SELL = {"time": T0.isoformat(), "verdict": "SPRZEDAJ", "entry": 100.0, "sl": 102.0, "tp": 96.0}


def test_buy_take_profit():
    s, r, _ = resolve(BUY, candles([(101, 99.5, 100), (104.5, 100, 104)]))
    assert s == "TP" and r == 2.0


def test_buy_stop_loss():
    s, r, _ = resolve(BUY, candles([(101, 97.5, 98)]))
    assert s == "SL" and r == -1.0


def test_both_in_one_candle_takes_stop_loss():
    assert resolve(BUY, candles([(105, 97, 100)]))[0] == "SL"


def test_sell_take_profit_and_stop():
    assert resolve(SELL, candles([(100.5, 95.5, 96)]))[0] == "TP"
    assert resolve(SELL, candles([(102.5, 99, 101)]))[0] == "SL"


def test_still_open_returns_none():
    assert resolve(BUY, candles([(101, 99.5, 100)] * 5)) is None


def test_expires_after_48h():
    rows = [(101, 99, 101)] * 200  # 50 godzin spokojnych świec
    s, r, _ = resolve(BUY, candles(rows))
    assert s == "EXPIRED" and abs(r - 0.5) < 1e-9  # (101-100)/2


def test_ignores_candles_before_verdict():
    early = candles([(110, 90, 100)])
    early["time"] = T0 - pd.Timedelta(minutes=15)
    assert resolve(BUY, early) is None
