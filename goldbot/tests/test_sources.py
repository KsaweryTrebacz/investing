import json

import pandas as pd

import sources
from config import Account, Config, Instrument
from store import Store
from tradingview import load_csv

NOW = pd.Timestamp("2026-10-23 10:00", tz="UTC")


def test_cache_reuses_fresh_value_and_survives_errors():
    store, errors, calls = Store(), [], []

    def fetch():
        calls.append(1)
        return [1, 2]

    assert sources.cached(store, "k", 3, NOW, fetch, errors, "Test") == [1, 2]
    assert sources.cached(store, "k", 3, NOW + pd.Timedelta(hours=1), fetch, errors, "Test") == [1, 2]
    assert len(calls) == 1

    def broken():
        raise RuntimeError("limit zapytań")

    later = NOW + pd.Timedelta(hours=5)
    assert sources.cached(store, "k", 3, later, broken, errors, "Test") == [1, 2]
    assert "limit zapytań" in errors[0] and "z bufora pobranych 2026-10-23T10:00" in errors[0]
    assert sources.cached(Store(), "k", 3, later, broken, [], "Test") is None


class FakeApi:
    def __init__(self, pairs):
        self.pairs = pairs

    def candles(self, pair, granularity, n):
        if pair not in self.pairs:
            raise RuntimeError("brak pary")
        mid = self.pairs[pair]
        return pd.DataFrame([{"time": NOW, "bid_c": mid - 0.001, "ask_c": mid + 0.001}])


def test_live_fx_direct_and_inverse():
    cfg = Config(account=Account(currency="PLN"))
    fx = sources.live_fx(FakeApi({"USD_PLN": 3.65}), cfg, "USD", [])
    assert abs(fx["USDPLN"]["rate"] - 3.65) < 1e-9 and "OANDA USD_PLN" in fx["USDPLN"]["source"]
    cfg = Config(account=Account(currency="EUR"))
    fx = sources.live_fx(FakeApi({"EUR_USD": 1.25}), cfg, "USD", [])
    assert abs(fx["USDEUR"]["rate"] - 0.8) < 1e-6
    errors = []
    assert sources.live_fx(FakeApi({}), cfg, "USD", errors) == {} and errors


def test_gather_reads_positions_and_event_file(tmp_path, monkeypatch):
    (tmp_path / "positions.json").write_text(json.dumps({"as_of": "x", "positions": []}), encoding="utf-8")
    (tmp_path / "events.csv").write_text("time,name\n2026-10-24 12:30,CPI\n", encoding="utf-8")
    cfg = Config(path=str(tmp_path / "config.json"), events={"file": "events.csv", "fred_releases": [10]})
    cfg.instruments = {"XAU_USD": Instrument(news={"topics": "economy_monetary"})}
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    ctx = sources.gather(cfg, "XAU_USD", Store(), NOW)
    assert ctx.positions == {"as_of": "x", "positions": []} and ctx.events_known
    assert [e["name"] for e in ctx.events] == ["CPI"]
    assert ctx.errors == ["Wiadomości: brak ALPHAVANTAGE_API_KEY."]
    demo = sources.gather(cfg, "XAU_USD", Store(), NOW, demo=True)
    assert demo.errors == [] and demo.news == []


def test_tradingview_csv(tmp_path):
    p = tmp_path / "tv.csv"
    p.write_text("time,open,high,low,close,Volume\n"
                 "1792742400,2000,2002,1999,2001,120\n"
                 "1792743300,2001,2003,2000,2002,90\n", encoding="utf-8")
    t0 = pd.Timestamp(1792742400, unit="s", tz="UTC")
    df = load_csv(str(p), 0.4, "M15", now=t0 + pd.Timedelta(minutes=20))  # druga świeca jeszcze trwa
    assert len(df) == 1 and df["bid_c"].iloc[0] == 2000.8 and df["ask_c"].iloc[0] == 2001.2
    assert df["volume"].iloc[0] == 120 and df["time"].iloc[0] == t0
    iso = tmp_path / "iso.csv"
    iso.write_text("time,open,high,low,close\n2026-10-20T00:00:00Z,1,2,0.5,1.5\n", encoding="utf-8")
    assert len(load_csv(str(iso), 0.1, "D", now=NOW)) == 1


def test_tradingview_needs_spread_and_columns(tmp_path):
    import pytest
    p = tmp_path / "tv.csv"
    p.write_text("time,close\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="spread"):
        load_csv(str(p), None, "M15")
    with pytest.raises(ValueError, match="brak kolumn"):
        load_csv(str(p), 0.1, "M15")
