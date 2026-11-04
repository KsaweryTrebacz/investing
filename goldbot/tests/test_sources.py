import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import sources
from sources import (DailyData, cross_check, drop_incomplete, is_daily_stale, parse_fred_csv,
                     parse_yahoo_chart, pick_source, with_spread)

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_parse_yahoo_chart_drops_missing_and_keeps_order():
    df = parse_yahoo_chart(json.loads((FIX / "yahoo_sample.json").read_text()))
    assert list(df.columns) == ["time", "open", "high", "low", "close"]
    assert len(df) == 39  # jeden brak usunięty
    assert df["time"].dt.tz is not None
    assert df["time"].is_monotonic_increasing
    assert (df["high"] >= df["low"]).all()
    assert df["close"].between(1000, 5000).all()


def test_parse_fred_csv_skips_dots():
    s = parse_fred_csv((FIX / "fred_sample.csv").read_text())
    assert s.index.tz is None
    assert len(s) == 36  # 39 wierszy minus 3 z wartością "."
    assert s.iloc[0] == 2.43
    assert not s.isna().any() and s.index.is_monotonic_increasing


def test_with_spread_adds_bid_ask_columns():
    ohlc = pd.DataFrame({"time": pd.date_range("2024-01-01", periods=3, tz="UTC"),
                         "open": [2000.0, 2010.0, 2020.0], "high": [2005.0, 2015, 2025],
                         "low": [1995.0, 2005, 2015], "close": [2002.0, 2012, 2022]})
    out = with_spread(ohlc, half=0.25)
    for k in "ohlc":
        assert f"bid_{k}" in out and f"ask_{k}" in out
    assert (out["ask_c"] - out["bid_c"]).round(6).eq(0.5).all()
    assert out["bid_c"].iloc[0] == 2001.75


def test_pick_source_auto_depends_on_token():
    assert pick_source("auto", {}) == "free"
    assert pick_source("auto", {"OANDA_TOKEN": "x"}) == "oanda"
    assert pick_source("free", {"OANDA_TOKEN": "x"}) == "free"
    with pytest.raises(ValueError):
        pick_source("mt5", {})


def test_is_daily_stale_respects_weekends():
    fri = pd.Timestamp("2026-10-30 00:00", tz="UTC")  # świeca piątkowa
    assert not is_daily_stale(fri, pd.Timestamp("2026-10-31 23:30", tz="UTC"))  # sobota
    assert not is_daily_stale(fri, pd.Timestamp("2026-11-02 23:30", tz="UTC"))  # poniedziałek wieczór
    assert is_daily_stale(fri, pd.Timestamp("2026-11-04 23:30", tz="UTC"))      # środa: brak pon. i wt.
    mon = pd.Timestamp("2026-11-02 00:00", tz="UTC")
    assert not is_daily_stale(mon, pd.Timestamp("2026-11-03 23:30", tz="UTC"))
    assert is_daily_stale(mon, pd.Timestamp("2026-11-05 01:00", tz="UTC"))


def test_cross_check_warns_only_on_large_gap():
    t = pd.date_range("2024-01-01", periods=30, tz="UTC")
    a = pd.DataFrame({"time": t, "bid_c": 2000.0 - 0.25, "ask_c": 2000.0 + 0.25})
    b = pd.DataFrame({"time": t, "close": 2010.0})
    assert cross_check(a, b) is None
    b["close"] = 2070.0
    w = cross_check(a, b)
    assert w and "3." in w


def test_free_source_uses_cache_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "CACHE", str(tmp_path))
    payload = json.loads((FIX / "yahoo_sample.json").read_text())
    sources.save_cache("gold.json", json.dumps(payload))
    sources.save_cache("usd.json", json.dumps(payload))
    sources.save_cache("yld.csv", (FIX / "fred_sample.csv").read_text())

    def boom(*a, **k):
        raise AssertionError("sieć nie powinna być użyta")
    monkeypatch.setattr(sources, "http_get", boom)
    d = sources.FreeSource(offline=True).fetch_daily(years=15)
    assert isinstance(d, DailyData)
    assert d.source == "free"
    assert len(d.gold) == 39 and "bid_c" in d.gold
    assert d.usd is not None and d.yld is not None
    assert any("pamięci podręcznej" in w for w in d.warnings)


def test_drop_incomplete_removes_todays_running_session_only():
    df = pd.DataFrame({"time": pd.to_datetime(["2026-11-03", "2026-11-04"], utc=True), "close": [1.0, 2.0]})
    assert len(drop_incomplete(df, pd.Timestamp("2026-11-04 10:00", tz="UTC"))) == 1
    assert len(drop_incomplete(df, pd.Timestamp("2026-11-04 23:30", tz="UTC"))) == 2
    assert len(drop_incomplete(df, pd.Timestamp("2026-11-05 01:00", tz="UTC"))) == 2
    assert drop_incomplete(df.iloc[:0], pd.Timestamp("2026-11-05", tz="UTC")).empty
