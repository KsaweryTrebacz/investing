"""Reżim dzienny: trend złota + dolar + realne rentowności -> KUPNO / NEUTRALNY / SPRZEDAŻ."""
import numpy as np
import pandas as pd

from indicators import ema

REGIME_BUY = "SPRZYJA_KUPNIE"
REGIME_NEUTRAL = "NEUTRALNY"
REGIME_SELL = "SPRZYJA_SPRZEDAZY"
REGIME_PL = {REGIME_BUY: "sprzyja kupnie", REGIME_NEUTRAL: "neutralny", REGIME_SELL: "sprzyja sprzedaży"}


def trend_dir(s: pd.Series, fast: int, slow: int) -> pd.Series:
    """+1 gdy EMA(fast) > EMA(slow) i EMA(fast) rośnie, -1 symetrycznie, inaczej 0. Rozgrzewka = NaN."""
    f, sl = ema(s, fast), ema(s, slow)
    up = (f > sl) & (f > f.shift(1))
    dn = (f < sl) & (f < f.shift(1))
    out = (up.astype(float) - dn.astype(float))
    out.iloc[:slow] = np.nan
    return out


def apply_hysteresis(raw: pd.Series, confirm: int = 2) -> pd.Series:
    """Nowy stan wchodzi w życie dopiero po `confirm` kolejnych dniach."""
    out, cur, cand, n = [], REGIME_NEUTRAL, None, 0
    for r in raw:
        if r == cur:
            cand, n = None, 0
        elif r == cand:
            n += 1
        else:
            cand, n = r, 1
        if cand is not None and n >= confirm:
            cur, cand, n = cand, None, 0
        out.append(cur)
    return pd.Series(out, index=raw.index)


def _macro_component(s, keys: pd.Series) -> pd.Series:
    """Kierunek szeregu makro (odwrócony: spadek dolara/rentowności sprzyja złotu), wyrównany do dat."""
    if s is None:
        return pd.Series(np.nan, index=keys.index)
    d = -trend_dir(s.sort_index(), 20, 50)
    return pd.Series(d.reindex(pd.DatetimeIndex(keys), method="ffill").to_numpy(), index=keys.index)


def build_regime(d1: pd.DataFrame, usd=None, yld=None, enter: int = 2, confirm: int = 2) -> pd.DataFrame:
    """d1: świece dzienne (kolumny time, bid_c, ask_c). Reżim danego dnia obowiązuje od `known_from`."""
    d1 = d1.reset_index(drop=True)
    close = (d1["bid_c"] + d1["ask_c"]) / 2
    known_from = d1["time"] + pd.Timedelta(days=1)
    keys = known_from.dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()

    out = pd.DataFrame({"time": d1["time"], "known_from": known_from})
    out["trend"] = trend_dir(close, 50, 200)
    out["dollar"] = _macro_component(usd, keys)
    out["yields"] = _macro_component(yld, keys)
    out["total"] = out["trend"] + out["dollar"] + out["yields"]  # NaN gdy brakuje któregokolwiek składnika

    raw = pd.Series(REGIME_NEUTRAL, index=out.index)
    raw[out["total"] >= enter] = REGIME_BUY
    raw[out["total"] <= -enter] = REGIME_SELL
    out["regime"] = apply_hysteresis(raw, confirm)
    return out


def attach_regime(df15: pd.DataFrame, reg: pd.DataFrame) -> pd.DataFrame:
    """Dołącza do świec M15 ostatni reżim znany w chwili otwarcia świecy (bez zaglądania w przyszłość)."""
    cols = ["known_from", "regime", "trend", "dollar", "yields", "total"]
    r = reg[cols].copy()
    r["known_from"] = r["known_from"].astype("datetime64[ns, UTC]")
    left = df15.copy()
    left["time"] = left["time"].astype("datetime64[ns, UTC]")
    out = pd.merge_asof(left.sort_values("time"), r.sort_values("known_from"),
                        left_on="time", right_on="known_from", direction="backward")
    out["regime"] = out["regime"].fillna(REGIME_NEUTRAL)
    return out.drop(columns=["known_from"]).reset_index(drop=True)
