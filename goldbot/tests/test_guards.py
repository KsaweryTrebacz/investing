import pathlib

import numpy as np
import pandas as pd
import pytest

from guards import DataError, apply_guards, is_stale, macro_is_stale, validate_candles
from oanda import demo_candles
from store import Store

NOW = pd.Timestamp("2026-01-05 10:20", tz="UTC")
LAST = pd.Timestamp("2026-01-05 10:00", tz="UTC")


def trade(t="2026-01-05T10:00:00+00:00", verdict="KUP"):
    return {"time": t, "verdict": verdict, "regime": "SPRZYJA_KUPNIE", "entry": 2000.0, "sl": 1991.0,
            "tp": 2018.0, "atr": 6.0, "reasoning": "Powód.", "status": "OPEN"}


# --- jakość danych ---

def test_valid_demo_candles_pass():
    validate_candles(demo_candles(300), "M15", 250)


@pytest.mark.parametrize("breaker, match", [
    (lambda d: d.__setitem__("ask_c", d["bid_c"] - 1), "ask < bid"),
    (lambda d: d.loc.__setitem__((5, "bid_c"), np.nan), "brak"),
    (lambda d: d.loc.__setitem__((5, "bid_l"), -1.0), "niedodatnie"),
    (lambda d: d.loc.__setitem__((5, "time"), d.loc[1, "time"]), "czas"),
    (lambda d: d.loc.__setitem__((5, "bid_h"), d.loc[5, "bid_l"] - 1), "high < low"),
])
def test_broken_candles_are_rejected(breaker, match):
    d = demo_candles(300)
    breaker(d)
    with pytest.raises(DataError, match=match):
        validate_candles(d, "M15", 250)


def test_too_short_history_is_rejected():
    with pytest.raises(DataError, match="za mało"):
        validate_candles(demo_candles(100), "M15", 250)


# --- nieaktualne dane ---

def test_is_stale():
    assert not is_stale(LAST, NOW)  # świeca zamknięta o 10:15, minęło 5 min
    assert is_stale(LAST, pd.Timestamp("2026-01-05 11:00", tz="UTC"))  # 45 min > 2 interwały


def test_macro_is_stale():
    s = pd.Series([1.0, 1.1], index=pd.to_datetime(["2025-12-01", "2025-12-02"]))
    assert macro_is_stale(s, NOW, max_days=10)
    assert not macro_is_stale(s, pd.Timestamp("2025-12-05", tz="UTC"), max_days=10)


# --- blokady werdyktu ---

def test_clean_trade_passes_unchanged():
    v = trade()
    assert apply_guards(v, Store(), NOW, LAST) == v


def test_stale_data_blocks_trade():
    v = apply_guards(trade(), Store(), pd.Timestamp("2026-01-05 12:00", tz="UTC"), LAST)
    assert v["verdict"] == "CZEKAJ" and v["entry"] is None and v["status"] == "NONE"
    assert "nieaktualne" in v["reasoning"]


def test_stale_data_is_reported_on_wait_too():
    w = dict(trade(), verdict="CZEKAJ", entry=None, sl=None, tp=None, status="NONE")
    v = apply_guards(w, Store(), pd.Timestamp("2026-01-05 12:00", tz="UTC"), LAST)
    assert "nieaktualne" in v["reasoning"]


def test_open_advice_blocks_new_trade():
    s = Store()
    s.add_verdict(trade("2026-01-05T09:00:00+00:00"))
    v = apply_guards(trade(), s, NOW, LAST)
    assert v["verdict"] == "CZEKAJ" and "otwarta" in v["reasoning"]


def test_daily_loss_limit_blocks_trade():
    s = Store()
    for i in range(2):
        vid = s.add_verdict(trade(f"2026-01-05T0{i + 1}:00:00+00:00"))
        s.close_verdict(vid, "SL", -1.0, f"2026-01-05T0{i + 1}:30:00+00:00")
    v = apply_guards(trade(), s, NOW, LAST)
    assert v["verdict"] == "CZEKAJ" and "limit" in v["reasoning"]


def test_yesterdays_losses_do_not_count():
    s = Store()
    for i in range(2):
        vid = s.add_verdict(trade(f"2026-01-04T0{i + 1}:00:00+00:00"))
        s.close_verdict(vid, "SL", -1.0, f"2026-01-04T0{i + 1}:30:00+00:00")
    assert apply_guards(trade(), s, NOW, LAST)["verdict"] == "KUP"


# --- brak kodu składającego zlecenia ---

def test_package_contains_no_order_code():
    root = pathlib.Path(__file__).resolve().parents[1]
    forbidden = ("order_send", "order_check", "/orders", "market_order", "TRADE_ACTION")
    for f in root.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        for word in forbidden:
            assert word not in text, f"{f.name} zawiera '{word}'"
