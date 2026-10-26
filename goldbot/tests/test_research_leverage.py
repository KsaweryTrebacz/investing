import pandas as pd

from research.leverage import Step, simulate

T = pd.Timestamp("2020-01-02", tz="UTC")


def step(side, worst, close, new=True, last=True, gap=100.0, fin=0):
    return Step(T, side, new, 100.0, gap, worst, close, 0.0, fin, last)


def test_leverage_multiplies_result_without_liquidation():
    assert abs(simulate([step(1, 99.9, 101.0)], 10, long_rate=0)["curve"].iloc[-1] - 1.10) < 1e-12
    assert abs(simulate([step(-1, 100.1, 99.0)], 10, short_rate=0)["curve"].iloc[-1] - 1.10) < 1e-12


def test_liquidation_at_50x_after_about_one_percent():
    r = simulate([step(1, 98.0, 101.0)], 50, long_rate=0)
    assert r["stopouts"] == 1 and 0.49 < r["curve"].iloc[-1] < 0.5   # zostaje ~50% depozytu, mimo że cena wróciła


def test_gap_beyond_liquidation_and_negative_balance_protection():
    r = simulate([step(1, 90.0, 95.0, gap=90.0)], 50, long_rate=0)  # luka -10% przy dźwigni 50: strata > 100%
    assert r["stopouts"] == 1 and r["curve"].iloc[-1] == 0.0 and r["ruined_at"] is None
    r = simulate([step(1, 90.0, 95.0, gap=90.0), step(1, 99.0, 100.0)], 50, long_rate=0)
    assert r["ruined_at"] == T


def test_financing_on_full_notional():
    r = simulate([step(1, 100.0, 100.0, fin=1)], 50, long_rate=-0.0365)
    assert abs(r["curve"].iloc[-1] - (1 - 50 * 0.0365 / 365)) < 1e-12
