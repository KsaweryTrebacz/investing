import numpy as np
import pandas as pd

from research.study import _in, monte_carlo, stats, walk_forward
from research.trend import run_donchian

NS = lambda s: pd.Timestamp(s, tz="UTC").value  # noqa: E731


def test_stats_hand_computed():
    s = stats(np.array([2.0, -1.0, -1.0, 2.0]), risk=0.01)
    assert s["trades"] == 4 and s["win_rate_%"] == 50.0 and s["avg_R"] == 0.5 and s["total_R"] == 2.0
    assert s["max_dd_R"] == -2.0 and s["profit_factor"] == 2.0
    assert abs(s["return_%_at_1.0%"] - 100 * (1.02 * 0.99 * 0.99 * 1.02 - 1)) < 0.01
    assert stats(np.array([]))["trades"] == 0


def test_walk_forward_uses_only_past_years():
    # wariant A świetny w latach uczących i zły w teście; wariant B odwrotnie: wybrany musi być A
    years = range(2010, 2014)
    times = np.array([NS(f"{y}-0{m}-01") for y in years for m in range(1, 10)])
    good_then_bad = np.array([2.0 if y < 2013 else -1.0 for y in years for _ in range(9)])
    bad_then_good = -good_then_bad
    res = [({"name": "A"}, times, good_then_bad + np.tile([0.0, 0.1, -0.1], 12)),
           ({"name": "B"}, times, bad_then_good + np.tile([0.0, 0.1, -0.1], 12))]
    import research.study as st
    old, st.MIN_TRADES = st.MIN_TRADES, 5
    try:
        w = walk_forward(res, 2013, 2013, train_years=3)
    finally:
        st.MIN_TRADES = old
    assert w["chosen"][0]["params"] == {"name": "A"} and w["R"].mean() < 0  # uczciwie: wynik poza próbą ujemny


def test_walk_forward_skips_year_without_positive_variant():
    times = np.array([NS(f"2011-0{m}-01") for m in range(1, 10)] * 4)
    w = walk_forward([({"x": 1}, times, -np.ones(len(times)))], 2014, 2014)
    assert w["chosen"][0]["params"] is None and len(w["R"]) == 0


def test_in_window():
    t = np.array([NS("2020-12-31 23:59"), NS("2021-01-01"), NS("2021-12-31 23:00"), NS("2022-01-01")])
    assert _in(t, "2021-01-01", "2022-01-01").tolist() == [False, True, True, False]


def test_monte_carlo_bounds():
    mc = monte_carlo(np.array([-1.0] * 10), trades_per_year=30, months=4, risks=(0.01,), paths=200)
    r = mc["1.0%"]
    assert mc["trades_per_path"] == 10 and r["P(strata)_%"] == 100.0 and abs(r["mediana_%"] - 100 * (0.99 ** 10 - 1)) < 0.01


def d1_frame(closes):
    t = pd.date_range("2020-01-01 22:00", periods=len(closes), freq="D", tz="UTC")
    c = np.array(closes, dtype=float)
    d = {"time": t}
    for side, off in (("bid", -0.05), ("ask", 0.05)):
        d.update({f"{side}_o": c + off, f"{side}_h": c + 1 + off, f"{side}_l": c - 1 + off, f"{side}_c": c + off})
    return pd.DataFrame(d)


def test_donchian_trend_trade():
    from config import Costs
    closes = [100.0] * 30 + [100.0 + 2 * i for i in range(1, 21)] + [140.0 - 5 * i for i in range(1, 6)]
    t = run_donchian(d1_frame(closes), entry_n=20, exit_n=10, stop_atr=3.0, long_only=True,
                     costs=Costs(financing_long_rate=0.0, slippage_atr=0.0))
    assert len(t) >= 1 and t.iloc[0]["side"] == 1 and t.iloc[0]["R"] > 0
