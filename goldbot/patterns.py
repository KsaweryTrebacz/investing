"""Cechy opisujące kształt wykresu dziennego (świece, wybicia, struktura, zmienność, długie momentum).

Wszystkie liczone wyłącznie z danych do zamknięcia dnia t.
"""
import numpy as np
import pandas as pd

PATTERN_FEATURES = [
    "body_pct", "upper_wick", "lower_wick", "gap_pct", "close_pos",   # świeca dnia
    "up_streak", "dn_streak",                                           # serie
    "brk_hi20", "brk_lo20", "brk_hi55", "brk_lo55",                     # odległość od wybić (Donchian)
    "hh_count20", "ll_count20",                                         # struktura: wyższe szczyty, niższe dołki
    "dd_from_peak250", "run_from_low250",                               # obsunięcie od szczytu / wzrost od dołka
    "vol_ratio", "vol_pctl250", "atr_trend",                            # reżim zmienności
    "mom_120", "mom_250", "ema_slope50", "ema_align",                   # długie momentum i układ średnich
    "autocorr20", "eff_ratio20",                                        # charakter ruchu: trend czy szum
    "dow", "month",                                                     # kalendarz
]

PATTERN_FEATURES_PL = {
    "body_pct": "korpus świecy", "upper_wick": "górny cień", "lower_wick": "dolny cień", "gap_pct": "luka otwarcia",
    "close_pos": "zamknięcie w zakresie dnia", "up_streak": "seria wzrostów", "dn_streak": "seria spadków",
    "brk_hi20": "odległość od szczytu 20 sesji", "brk_lo20": "odległość od dołka 20 sesji",
    "brk_hi55": "odległość od szczytu 55 sesji", "brk_lo55": "odległość od dołka 55 sesji",
    "hh_count20": "wyższe szczyty (20 sesji)", "ll_count20": "niższe dołki (20 sesji)",
    "dd_from_peak250": "obsunięcie od szczytu roku", "run_from_low250": "wzrost od dołka roku",
    "vol_ratio": "zmienność krótka/długa", "vol_pctl250": "percentyl zmienności (rok)", "atr_trend": "trend ATR",
    "mom_120": "momentum 6 mies.", "mom_250": "momentum 12 mies.", "ema_slope50": "nachylenie EMA 50",
    "ema_align": "układ EMA 20/50/200", "autocorr20": "autokorelacja zwrotów", "eff_ratio20": "współczynnik efektywności",
    "dow": "dzień tygodnia", "month": "miesiąc",
}


def _streak(up: pd.Series) -> pd.Series:
    """Długość bieżącej serii wartości True."""
    out, n = np.zeros(len(up)), 0
    for i, v in enumerate(up.to_numpy()):
        n = n + 1 if v else 0
        out[i] = n
    return pd.Series(out, index=up.index)


def add_patterns(f: pd.DataFrame, o: pd.Series, h: pd.Series, l: pd.Series, c: pd.Series, time: pd.Series) -> pd.DataFrame:
    """f: ramka cech (ten sam indeks co o/h/l/c). Dodaje kolumny PATTERN_FEATURES."""
    rng = (h - l).replace(0, np.nan)
    logc = np.log(c)
    r = logc.diff()
    prev_c = c.shift(1)

    f["body_pct"] = (c - o) / prev_c
    f["upper_wick"] = (h - np.maximum(o, c)) / rng
    f["lower_wick"] = (np.minimum(o, c) - l) / rng
    f["gap_pct"] = (o - prev_c) / prev_c
    f["close_pos"] = (c - l) / rng

    f["up_streak"] = _streak(r > 0)
    f["dn_streak"] = _streak(r < 0)

    for n in (20, 55):
        f[f"brk_hi{n}"] = c / h.shift(1).rolling(n).max() - 1
        f[f"brk_lo{n}"] = c / l.shift(1).rolling(n).min() - 1
    f["hh_count20"] = (h > h.shift(1)).astype(float).rolling(20).sum()
    f["ll_count20"] = (l < l.shift(1)).astype(float).rolling(20).sum()
    f["dd_from_peak250"] = c / c.rolling(250).max() - 1
    f["run_from_low250"] = c / c.rolling(250).min() - 1

    v10, v60 = r.rolling(10).std(), r.rolling(60).std()
    f["vol_ratio"] = v10 / v60
    v20 = r.rolling(20).std()
    f["vol_pctl250"] = v20.rolling(250).rank(pct=True)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    f["atr_trend"] = tr.rolling(5).mean() / tr.rolling(50).mean() - 1

    f["mom_120"] = logc - logc.shift(120)
    f["mom_250"] = logc - logc.shift(250)
    e20, e50, e200 = (c.ewm(span=n, adjust=False).mean() for n in (20, 50, 200))
    f["ema_slope50"] = e50 / e50.shift(10) - 1
    f["ema_align"] = ((e20 > e50).astype(float) + (e50 > e200).astype(float) - 1.0)

    f["autocorr20"] = r.rolling(20).apply(lambda x: pd.Series(x).autocorr(1) if np.std(x) > 0 else 0.0, raw=True)
    f["eff_ratio20"] = (c - c.shift(20)).abs() / (c.diff().abs().rolling(20).sum()).replace(0, np.nan)

    t = pd.DatetimeIndex(time)
    f["dow"] = t.dayofweek.astype(float)
    f["month"] = t.month.astype(float)
    return f
