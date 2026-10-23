"""Wiadomości z Alpha Vantage (NEWS_SENTIMENT): nagłówek, źródło, czas publikacji i czas pobrania.

Nagłówek, źródło i czas publikacji to fakty. Etykieta sentymentu to automatyczna ocena dostawcy,
czyli interpretacja; program nie używa jej w sygnale ani w decyzji.
"""
import pandas as pd
import requests

AV_URL = "https://www.alphavantage.co/query"


def _published(raw: str) -> str:
    """20261023T143000 -> 2026-10-23 14:30 (strefa czasowa tak, jak podaje Alpha Vantage)."""
    try:
        return pd.Timestamp(raw).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(raw)


def parse_news(payload: dict, fetched_at, limit: int = 5) -> list:
    if "feed" not in payload:
        raise RuntimeError(payload.get("Information") or payload.get("Note") or "nieoczekiwana odpowiedź Alpha Vantage")
    fetched = pd.Timestamp(fetched_at).isoformat()
    return [{"title": it.get("title", ""), "source": it.get("source", ""), "url": it.get("url", ""),
             "published": _published(it.get("time_published", "")),
             "sentiment": it.get("overall_sentiment_label"), "fetched_at": fetched}
            for it in payload["feed"][:limit]]


def fetch_news(query: dict, api_key: str, now, hours: int = 24, limit: int = 5) -> list:
    """query: parametry z konfiguracji instrumentu, np. {"topics": "economy_monetary"} albo {"tickers": "AAPL"}."""
    params = {"function": "NEWS_SENTIMENT", "sort": "LATEST", "limit": 50, "apikey": api_key,
              "time_from": (pd.Timestamp(now) - pd.Timedelta(hours=hours)).strftime("%Y%m%dT%H%M"), **query}
    r = requests.get(AV_URL, params=params, timeout=30)
    r.raise_for_status()
    return parse_news(r.json(), now, limit)
