import numpy as np
import pandas as pd

import research.edges as E


def hours_frame(prices, start="2021-01-04 00:00", spread=0.0):
    t = pd.date_range(start, periods=len(prices), freq="1h", tz="UTC")
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"bid_o": p - spread / 2, "ask_o": p + spread / 2}, index=t)


def test_session_long_and_short_returns_with_spread():
    prices = [100.0] * 24 + [100.0] * 7 + [102.0] * 17          # 2. dzień: od 07:00 cena 102
    h = hours_frame(prices, spread=0.2)
    long_ = E.session_returns(h, 5, 8, 1)                          # wejście 05:00 po ask, wyjście 08:00 po bid
    assert abs(long_.iloc[1] - (101.9 - 100.1) / 100.0) < 1e-12
    short = E.session_returns(h, 5, 8, -1)
    assert abs(short.iloc[1] - (99.9 - 102.1) / 100.0) < 1e-12


def test_session_crossing_rollover_pays_financing():
    h = hours_frame([100.0] * 72)                                  # 4-6 stycznia 2021, zima: rollover 22:00 UTC
    r = E.session_returns(h, 20, 23, 1)
    assert abs(r.iloc[0] - E.LONG_RATE / 365) < 1e-12              # poniedziałek: 1 dzień
    assert abs(r.iloc[2] - 3 * E.LONG_RATE / 365) < 1e-12          # środa: potrójnie
    assert (E.session_returns(h, 1, 5, 1) == 0).all()              # bez rolloveru bez kosztu


def test_position_returns_costs_and_lag():
    t = pd.date_range("2021-01-03 22:00", periods=4, freq="D", tz="UTC")
    c = np.array([100.0, 110.0, 121.0, 121.0])
    d1 = pd.DataFrame({"time": t, "bid_c": c - 0.1, "ask_c": c + 0.1})
    old = E.LONG_RATE, E.SHORT_RATE
    E.LONG_RATE, E.SHORT_RATE = 0.0, 0.0
    try:
        pos = pd.Series([1.0, 1.0, 1.0, 1.0], index=E._daily_mid(d1).index)
        r = E.position_returns(d1, pos)
    finally:
        E.LONG_RATE, E.SHORT_RATE = old
    spread = 0.2 / 100.0
    assert abs(r.iloc[0] - (0.10 - spread / 2)) < 1e-9             # pozycja od zamknięcia 1. dnia, koszt wejścia
    assert abs(r.iloc[1] - 0.10) < 1e-9 and abs(r.iloc[2]) < 1e-12


def test_summarize_and_walk_forward():
    idx = pd.date_range("2015-01-01", "2018-12-31", freq="B")
    good = pd.Series(np.where(idx.year < 2018, 0.001, -0.001), index=idx)
    bad = -good
    s = E.summarize(good)
    assert s["years_positive"] == "3/4" and s["cagr_%"] > 0
    oos, chosen = E.walk_forward({"A": good, "B": bad}, 2018, 2018, train_years=3)
    assert chosen[0]["variant"] == "A" and oos.mean() < 0          # wybór na przeszłości, uczciwy wynik poza próbą
