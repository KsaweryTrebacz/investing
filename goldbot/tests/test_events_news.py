import pandas as pd
import pytest

import events as ev
import news

NOW = pd.Timestamp("2026-10-23 10:00", tz="UTC")


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self.payload, self.text = payload, text

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def fake_get(routes, calls):
    def get(url, params=None, timeout=None):
        calls.append((url, params))
        key = params.get("function") or url.rsplit("/", 1)[-1]
        return routes[key]
    return get


def test_make_event_all_day_and_timed():
    e = ev.make_event("2026-10-24", "CPI", "test", NOW)
    assert e["all_day"] and e["start"] == "2026-10-24T00:00:00+00:00" and e["end"] == "2026-10-25T00:00:00+00:00"
    e = ev.make_event("2026-10-24 12:30", "CPI", "test", NOW)
    assert not e["all_day"] and e["start"] == e["end"] == "2026-10-24T12:30:00+00:00"


def test_csv_events(tmp_path):
    p = tmp_path / "events.csv"
    p.write_text("time,name,importance,scope,kind,amount,source,published\n"
                 "2026-10-23 12:30,Payrolls USA,wysoka,USD,makro,,BLS,2026-10-01\n"
                 "2026-10-27,Dywidenda ABC,wysoka,ABC_USD,dywidenda,0.5,,\n"
                 ",pusty wiersz,,,,,,\n", encoding="utf-8")
    es = ev.load_csv_events(str(p), NOW)
    assert len(es) == 2 and es[0]["source"] == "BLS" and es[1]["amount"] == 0.5
    assert es[1]["source"] == "plik events.csv" and es[0]["fetched_at"] == NOW.isoformat()


def test_scope_window_and_guard():
    es = [ev.make_event("2026-10-23 11:00", "FOMC", "t", NOW, scope="USD"),
          ev.make_event("2026-10-24", "Wyniki", "t", NOW, scope="AAPL", kind="wyniki"),
          ev.make_event("2026-10-30", "Daleko", "t", NOW),
          ev.make_event("2026-10-23 10:30", "Drobne", "t", NOW, importance="niska")]
    up = ev.upcoming(es, NOW, 48, "XAU_USD")
    assert [e["name"] for e in up] == ["Drobne", "FOMC"]
    assert [e["name"] for e in ev.upcoming(es, NOW, 48, "AAPL_USD", "AAPL")] == ["Drobne", "FOMC", "Wyniki"]
    assert [e["name"] for e in ev.near_now(es, NOW, 2)] == ["FOMC"]   # niska waga nie blokuje
    assert ev.near_now(es, NOW, 0.5) == []


def test_all_day_event_guards_whole_day():
    es = [ev.make_event("2026-10-23", "CPI", "t", NOW)]
    assert ev.near_now(es, NOW, 0) and ev.near_now(es, NOW - pd.Timedelta(hours=11), 2)


def test_fred_release_calendar(monkeypatch):
    calls = []
    routes = {"release": FakeResponse({"releases": [{"id": 10, "name": "Consumer Price Index"}]}),
              "dates": FakeResponse({"release_dates": [{"release_id": 10, "date": "2026-10-20"},
                                                       {"release_id": 10, "date": "2026-11-12"}]})}
    monkeypatch.setattr(ev.requests, "get", fake_get(routes, calls))
    es = ev.fetch_fred_releases([10], "KEY", NOW)
    assert [(e["name"], e["start"][:10]) for e in es] == [("Consumer Price Index", "2026-11-12")]
    assert es[0]["scope"] == "USD" and "release_id=10" in es[0]["source"]
    assert calls[1][1]["include_release_dates_with_no_data"] == "true"


def test_alpha_vantage_company(monkeypatch):
    csv_text = ("symbol,name,reportDate,fiscalDateEnding,estimate,currency\r\n"
                "AAPL,Apple Inc,2026-10-29,2026-09-30,1.71,USD\r\n")
    overview = {"Symbol": "AAPL", "Sector": "TECHNOLOGY", "Industry": "ELECTRONIC COMPUTERS",
                "DividendPerShare": "1.04", "ExDividendDate": "2026-11-10"}
    monkeypatch.setattr(ev.requests, "get", fake_get(
        {"EARNINGS_CALENDAR": FakeResponse(text=csv_text), "OVERVIEW": FakeResponse(overview)}, []))
    es, info = ev.fetch_company("AAPL", "KEY", NOW)
    assert info["sector"] == "TECHNOLOGY" and [e["kind"] for e in es] == ["wyniki", "dywidenda"]
    assert "prognoza EPS analityków 1.71 USD" in es[0]["note"] and ev.dividend_in(es)["start"][:10] == "2026-11-10"


def test_alpha_vantage_limit_is_an_error(monkeypatch):
    monkeypatch.setattr(ev.requests, "get", fake_get(
        {"EARNINGS_CALENDAR": FakeResponse(text="symbol,name\r\n"),
         "OVERVIEW": FakeResponse({"Information": "limit zapytań"})}, []))
    with pytest.raises(RuntimeError, match="limit"):
        ev.fetch_company("AAPL", "KEY", NOW)


def test_overview_without_dividend():
    es, info = ev.parse_overview({"Symbol": "X", "ExDividendDate": "None", "DividendPerShare": "None"}, NOW)
    assert es == [] and info["dividend_per_share_annual"] is None


def test_news(monkeypatch):
    feed = {"feed": [{"title": "Fed holds rates", "source": "Reuters", "url": "u", "time_published": "20261023T083000",
                      "overall_sentiment_label": "Neutral"}] * 7}
    calls = []
    monkeypatch.setattr(news.requests, "get", fake_get({"NEWS_SENTIMENT": FakeResponse(feed)}, calls))
    items = news.fetch_news({"topics": "economy_monetary"}, "KEY", NOW)
    assert len(items) == 5 and items[0]["published"] == "2026-10-23 08:30" and items[0]["source"] == "Reuters"
    assert calls[0][1]["topics"] == "economy_monetary" and calls[0][1]["time_from"] == "20261022T1000"
    with pytest.raises(RuntimeError, match="limit"):
        news.parse_news({"Note": "limit zapytań"}, NOW)
