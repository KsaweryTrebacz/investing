import numpy as np
import pandas as pd

from advisor import make_verdict
from regime import REGIME_BUY, REGIME_NEUTRAL
from strategy import Params


def frame(signal=0, raw=None, regime=REGIME_BUY, bid=2000.0, ask=2000.3, atr=6.0,
          trend=1.0, dollar=1.0, yields=1.0):
    return pd.DataFrame([{
        "time": pd.Timestamp("2026-01-05 10:00", tz="UTC"), "bid_c": bid, "ask_c": ask, "atr": atr,
        "signal": signal, "signal_raw": signal if raw is None else raw, "regime": regime,
        "trend": trend, "dollar": dollar, "yields": yields}])


def test_buy_levels():
    v = make_verdict(frame(signal=1), Params())
    assert v["verdict"] == "KUP" and v["status"] == "OPEN"
    assert v["entry"] == 2000.3
    assert abs(v["sl"] - (2000.3 - 1.5 * 6.0)) < 1e-9
    assert abs(v["tp"] - (2000.3 + 3.0 * 6.0)) < 1e-9


def test_sell_levels_use_bid():
    v = make_verdict(frame(signal=-1, regime="SPRZYJA_SPRZEDAZY"), Params())
    assert v["verdict"] == "SPRZEDAJ" and v["entry"] == 2000.0
    assert v["sl"] > v["entry"] > v["tp"]


def test_no_signal_waits():
    v = make_verdict(frame(), Params())
    assert v["verdict"] == "CZEKAJ" and v["status"] == "NONE" and v["entry"] is None
    assert "Reżim dzienny: sprzyja kupnie" in v["reasoning"]


def test_wide_spread_rejects_signal():
    v = make_verdict(frame(signal=1, ask=2003.0), Params())  # spread 3.0 > 25% * 6.0
    assert v["verdict"] == "CZEKAJ" and "spread" in v["reasoning"]


def test_regime_block_is_explained():
    v = make_verdict(frame(signal=0, raw=1, regime=REGIME_NEUTRAL), Params())
    assert v["verdict"] == "CZEKAJ" and "zablokowany" in v["reasoning"]


def test_missing_macro_is_reported():
    v = make_verdict(frame(regime=REGIME_NEUTRAL, dollar=np.nan, yields=np.nan), Params())
    assert v["reasoning"].count("brak danych") == 2
