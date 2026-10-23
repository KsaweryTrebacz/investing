import pandas as pd

from config import Costs
from costs import financing_days, holding_estimate, per_unit_costs


def ts(s):
    return pd.Timestamp(s, tz="UTC")


def test_financing_days_weekdays_and_triple_wednesday():
    assert financing_days(ts("2026-01-05 10:00"), ts("2026-01-06 23:00")) == 2   # pn i wt o 22:00 UTC
    assert financing_days(ts("2026-01-07 21:00"), ts("2026-01-07 23:00")) == 3   # środa
    assert financing_days(ts("2026-01-09 23:00"), ts("2026-01-12 12:00")) == 0   # weekend bez naliczeń
    assert financing_days(ts("2026-01-05 12:00"), ts("2026-01-05 11:00")) == 0


def test_financing_days_follow_new_york_dst():
    # 9 marca 2026 obowiązuje już czas letni: rollover 17:00 EDT = 21:00 UTC
    assert financing_days(ts("2026-03-09 20:30"), ts("2026-03-09 21:30")) == 1
    assert financing_days(ts("2026-03-09 21:30"), ts("2026-03-09 22:30")) == 0


def test_per_unit_costs_known():
    c = Costs(commission_per_unit=0.1, financing_long_rate=-0.0365, slippage_atr=0.1)
    pc = per_unit_costs(c, 1, 2000.0, 5.0, ts("2026-01-05 10:00"), ts("2026-01-06 23:00"))
    assert abs(pc["commission"] - 0.2) < 1e-12           # otwarcie i zamknięcie
    assert abs(pc["financing"] - 0.4) < 1e-12            # 2000 * 3,65% / 365 * 2 dni
    assert abs(pc["slippage"] - 0.5) < 1e-12 and pc["financing_days"] == 2 and pc["missing"] == []


def test_commission_rate_and_swap_income():
    c = Costs(commission_rate=0.0001, swap_short_per_unit=0.05, slippage_atr=0.0)
    pc = per_unit_costs(c, -1, 2000.0, 5.0, ts("2026-01-07 21:00"), ts("2026-01-07 23:00"))
    assert abs(pc["commission"] - 0.4) < 1e-12 and abs(pc["financing"] + 0.15) < 1e-12


def test_missing_costs_are_listed():
    pc = per_unit_costs(Costs(), 1, 2000.0, 5.0, ts("2026-01-05 10:00"), ts("2026-01-05 11:00"))
    assert pc["financing"] == 0.0  # bez nocy finansowanie jest znane: zero
    assert pc["missing"] == ["prowizja", "poślizg na SL"]
    pc = per_unit_costs(Costs(), 1, 2000.0, 5.0, ts("2026-01-05 10:00"), ts("2026-01-06 10:00"))
    assert pc["financing"] is None and "finansowanie overnight" in pc["missing"]


def test_holding_estimate():
    r = [{"time": "2026-01-05T10:00:00+00:00", "resolved_time": "2026-01-05T12:00:00+00:00"}] * 10
    h = holding_estimate(r)
    assert h["hours"] == 2.0 and h["n"] == 10 and "mediana" in h["basis"]
    h = holding_estimate(r[:3])
    assert h["hours"] == 48.0 and "górną granicę" in h["basis"]
