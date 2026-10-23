"""Nadchodzące wydarzenia: własny plik CSV, kalendarz publikacji FRED, wyniki i dywidendy spółek (Alpha Vantage).

Każde wydarzenie ma źródło i czas pobrania. Wydarzenie z samą datą obejmuje cały dzień UTC.
"""
import csv
import io
import os

import pandas as pd
import requests

FRED_URL = "https://api.stlouisfed.org/fred"
AV_URL = "https://www.alphavantage.co/query"
HIGH = "wysoka"


def _utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def make_event(when: str, name: str, source: str, fetched_at, importance: str = HIGH, scope: str = "*",
               kind: str = "inne", amount: float | None = None, published: str | None = None, note: str = "") -> dict:
    """`when` jako data (RRRR-MM-DD, cały dzień) albo data z godziną (bez strefy = UTC)."""
    when = str(when).strip()
    all_day = len(when) == 10
    start = _utc(when)
    end = start + pd.Timedelta(days=1) if all_day else start
    return {"start": start.isoformat(), "end": end.isoformat(), "all_day": all_day, "name": name,
            "importance": importance or HIGH, "scope": scope or "*", "kind": kind or "inne", "amount": amount,
            "note": note, "source": source, "published": published or None,
            "fetched_at": _utc(fetched_at).isoformat()}


def load_csv_events(path: str, fetched_at) -> list:
    """Kolumny: time, name (wymagane), importance, scope, kind, amount, source, published."""
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            row = {k: (v or "").strip() for k, v in row.items() if k}
            if not row.get("time") or not row.get("name"):
                continue
            amount = float(row["amount"]) if row.get("amount") else None
            out.append(make_event(row["time"], row["name"], row.get("source") or f"plik {os.path.basename(path)}",
                                  fetched_at, row.get("importance") or HIGH, row.get("scope") or "*",
                                  row.get("kind") or "inne", amount, row.get("published")))
    return out


def _get_json(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and ("Information" in data or "Note" in data or "error_message" in data):
        raise RuntimeError(data.get("Information") or data.get("Note") or data.get("error_message"))
    return data


def fetch_fred_releases(release_ids: list, api_key: str, now, fetched_at=None) -> list:
    """Przyszłe daty publikacji wskazanych pozycji kalendarza FRED. Nazwa publikacji pochodzi z FRED."""
    fetched_at = fetched_at or now
    today = _utc(now).strftime("%Y-%m-%d")
    out = []
    for rid in release_ids:
        base = {"release_id": rid, "api_key": api_key, "file_type": "json"}
        name = _get_json(f"{FRED_URL}/release", base)["releases"][0]["name"]
        dates = _get_json(f"{FRED_URL}/release/dates", {**base, "include_release_dates_with_no_data": "true",
                                                         "realtime_start": today, "realtime_end": "9999-12-31",
                                                         "sort_order": "asc", "limit": 50})
        for d in dates.get("release_dates", []):
            if d["date"] >= today:
                out.append(make_event(d["date"], name, f"FRED, kalendarz publikacji (release_id={rid})",
                                      fetched_at, HIGH, "USD", "makro"))
    return out


def parse_earnings_csv(text: str, fetched_at) -> list:
    """EARNINGS_CALENDAR: symbol, name, reportDate, fiscalDateEnding, estimate, currency."""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        if not row.get("reportDate"):
            continue
        note = f"prognoza EPS analityków {row['estimate']} {row.get('currency', '')}".strip() if row.get("estimate") else ""
        out.append(make_event(row["reportDate"], f"Wyniki kwartalne {row.get('name') or row['symbol']} "
                                                 f"(okres do {row.get('fiscalDateEnding', '?')})",
                              "Alpha Vantage EARNINGS_CALENDAR", fetched_at, HIGH, row["symbol"], "wyniki", note=note))
    return out


def parse_overview(payload: dict, fetched_at) -> tuple[list, dict]:
    """OVERVIEW: sektor, branża, dywidenda roczna na akcję i dzień ustalenia prawa do dywidendy."""
    clean = lambda v: None if v in (None, "", "None", "-", "0000-00-00") else v  # noqa: E731
    info = {"sector": clean(payload.get("Sector")), "industry": clean(payload.get("Industry")),
            "dividend_per_share_annual": clean(payload.get("DividendPerShare"))}
    events = []
    ex = clean(payload.get("ExDividendDate"))
    if ex:
        note = (f"roczna dywidenda na akcję {info['dividend_per_share_annual']}; kwotę tej wypłaty sprawdź u brokera"
                if info["dividend_per_share_annual"] else "kwotę sprawdź u brokera")
        events.append(make_event(ex, f"Dzień ustalenia prawa do dywidendy {payload.get('Symbol', '')}".strip(),
                                 "Alpha Vantage OVERVIEW", fetched_at, HIGH, payload.get("Symbol") or "*",
                                 "dywidenda", note=note))
    return events, info


def fetch_company(symbol: str, api_key: str, fetched_at) -> tuple[list, dict]:
    """Wyniki (3 miesiące naprzód) i dywidenda spółki z Alpha Vantage."""
    r = requests.get(AV_URL, params={"function": "EARNINGS_CALENDAR", "symbol": symbol, "horizon": "3month",
                                     "apikey": api_key}, timeout=30)
    r.raise_for_status()
    if not r.text.lstrip().startswith("symbol"):
        raise RuntimeError(f"EARNINGS_CALENDAR: nieoczekiwana odpowiedź: {r.text[:200]}")
    events = parse_earnings_csv(r.text, fetched_at)
    ov_events, info = parse_overview(_get_json(AV_URL, {"function": "OVERVIEW", "symbol": symbol, "apikey": api_key}),
                                     fetched_at)
    return events + ov_events, info


def applies(e: dict, instrument: str, symbol: str | None = None) -> bool:
    """Czy wydarzenie dotyczy instrumentu: "*", nazwa instrumentu, symbol spółki albo waluta z nazwy."""
    return e["scope"] in ("*", instrument, symbol) or e["scope"] in instrument.split("_")


def upcoming(events: list, now, hours: float, instrument: str, symbol: str | None = None) -> list:
    """Wydarzenia trwające albo zaczynające się w ciągu `hours` godzin (okno planowanego utrzymania)."""
    now = _utc(now)
    horizon = now + pd.Timedelta(hours=hours)
    out = [e for e in events if applies(e, instrument, symbol)
           and _utc(e["end"]) >= now and _utc(e["start"]) <= horizon]
    return sorted(out, key=lambda e: e["start"])


def near_now(events: list, now, guard_hours: float) -> list:
    """Wydarzenia o wysokiej wadze, od których dzieli nas mniej niż `guard_hours` godzin."""
    now, g = _utc(now), pd.Timedelta(hours=guard_hours)
    return [e for e in events if e["importance"] == HIGH and _utc(e["start"]) - g <= now <= _utc(e["end"]) + g]


def dividend_in(events: list) -> dict | None:
    """Pierwsza dywidenda w podanych (już przefiltrowanych) wydarzeniach."""
    return next((e for e in events if e["kind"] == "dywidenda"), None)
