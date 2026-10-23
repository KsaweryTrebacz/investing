import pandas as pd

import structure as st


def frame(closes, wick=0.5):
    c = pd.Series(closes, dtype=float)
    return pd.DataFrame({"mid_h": c + wick, "mid_l": c - wick, "mid_c": c})


RISE = [100, 101, 102, 103, 102, 101, 100, 101, 102, 103, 104, 105, 106]


def test_swing_points_need_confirmation():
    d = frame(RISE)
    hi, lo = st.swing_points(d["mid_h"], d["mid_l"], n=2)
    assert list(d.index[hi]) == [3] and list(d.index[lo]) == [6]
    assert not hi.iloc[-2:].any() and not lo.iloc[-2:].any()  # ostatnie n świec bez potwierdzenia


def test_classify():
    s = lambda *x: pd.Series(x, dtype=float)  # noqa: E731
    assert st.classify(s(10, 12), s(5, 7)) == st.STRUCT_UP
    assert st.classify(s(12, 10), s(7, 5)) == st.STRUCT_DOWN
    assert st.classify(s(10, 12), s(7, 5)) == st.STRUCT_MIXED
    assert st.classify(s(10), s(5)) == st.STRUCT_NA


def test_breakout_levels_and_support():
    r = st.analyze(frame(RISE), atr=1.0, n=2)
    assert r["breakout"] == {"direction": 1, "level": 103.5, "bars_ago": 2, "retest": False, "holding": True}
    assert r["support"] == 99.5 and r["resistance"] is None and r["structure"] == st.STRUCT_NA


def test_retest_after_breakout():
    r = st.analyze(frame(RISE[:10] + [104, 103.6, 104.5, 105]), atr=1.0, n=2)
    assert r["breakout"]["retest"] and r["breakout"]["holding"]


def test_failed_breakout_is_not_holding():
    r = st.analyze(frame(RISE[:10] + [104, 103.0, 102.5, 102.0]), atr=1.0, n=2)
    assert r["breakout"]["direction"] == 1 and not r["breakout"]["holding"]


def test_old_breakout_is_ignored():
    r = st.analyze(frame(RISE + [106] * 30), atr=1.0, n=2, recent=20)
    assert r["breakout"] is None
