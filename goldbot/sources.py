"""Dane spoza świec dla cyklu: kurs walut, pozycje, wydarzenia, wiadomości. Z buforem w bazie (limity API).

Błąd pobierania nie przerywa cyklu: trafia do raportu, a jeśli w buforze są starsze dane, są użyte
z ich prawdziwym czasem pobrania.
"""
import os

import pandas as pd

from config import Config
from cycle import Context
from events import fetch_company, fetch_fred_releases, load_csv_events
from news import fetch_news
from risk import load_positions


def cached(store, key: str, max_age_hours: float, now, fetch, errors: list, label: str):
    """Wartość z bufora, jeśli młodsza niż `max_age_hours`, inaczej świeżo pobrana. None, gdy brak obu."""
    entry = store.get_state(key)
    if entry and pd.Timestamp(now) - pd.Timestamp(entry["fetched_at"]) < pd.Timedelta(hours=max_age_hours):
        return entry["value"]
    try:
        value = fetch()
    except Exception as e:  # sieć, limit API, zły klucz: raport ma to pokazać, cykl ma działać dalej
        old = f" Użyto danych z bufora pobranych {entry['fetched_at'][:16]} UTC." if entry else ""
        errors.append(f"{label}: {e}.{old}")
        return entry["value"] if entry else None
    store.set_state(key, {"fetched_at": pd.Timestamp(now).isoformat(), "value": value})
    return value


def live_fx(api, cfg: Config, quote: str, errors: list) -> dict:
    """Kurs waluty kwotowania na walutę rachunku z ostatniej zamkniętej świecy M15 w OANDA."""
    acct = cfg.account.currency
    if not acct or acct == quote:
        return {}
    for pair, inverse in ((f"{quote}_{acct}", False), (f"{acct}_{quote}", True)):
        try:
            c = api.candles(pair, "M15", 3).iloc[-1]
        except Exception:
            continue
        mid = (c["bid_c"] + c["ask_c"]) / 2
        return {quote + acct: {"rate": 1 / mid if inverse else mid, "as_of": c["time"].isoformat()[:16],
                               "source": f"OANDA {pair}, świeca M15"}}
    errors.append(f"Kurs {quote}/{acct}: OANDA nie zwróciła pary, użyty zostanie kurs z konfiguracji (jeśli jest).")
    return {}


def gather(cfg: Config, instrument: str, store, now, demo: bool = False, api=None, meta: dict | None = None) -> Context:
    """Kontekst cyklu dla instrumentu. W trybie demo bez zapytań sieciowych."""
    instr = cfg.instrument(instrument)
    ev_cfg = cfg.events
    ctx = Context(cfg=cfg, instrument=instrument, meta=meta or {})
    ctx.positions = load_positions(cfg.resolve_path(cfg.positions_file))
    if api is not None and not demo:
        ctx.fx_live = live_fx(api, cfg, instr.quote, ctx.errors)

    path = cfg.resolve_path(ev_cfg.get("file"))
    if path and os.path.exists(path):
        ctx.events += load_csv_events(path, now)
        ctx.events_known = True
    if demo:
        return ctx

    fred_key, av_key = os.environ.get("FRED_API_KEY"), os.environ.get("ALPHAVANTAGE_API_KEY")
    if ev_cfg.get("fred_releases") and fred_key:
        ctx.events_known = True
        ctx.events += cached(store, "fred_releases", 24, now,
                             lambda: fetch_fred_releases(ev_cfg["fred_releases"], fred_key, now),
                             ctx.errors, "Kalendarz FRED") or []
    if instr.symbol and av_key:
        ctx.events_known = True
        company = cached(store, f"company_{instr.symbol}", ev_cfg.get("company_refresh_hours", 24), now,
                         lambda: fetch_company(instr.symbol, av_key, now), ctx.errors, "Alpha Vantage (spółka)")
        if company:
            ctx.events += company[0]
            ctx.meta["spółka"] = {k: v for k, v in company[1].items() if v}
    if instr.news and av_key:
        ctx.news = cached(store, "news", ev_cfg.get("news_refresh_hours", 3), now,
                          lambda: fetch_news(instr.news, av_key, now), ctx.errors, "Alpha Vantage (wiadomości)") or []
    elif instr.news:
        ctx.errors.append("Wiadomości: brak ALPHAVANTAGE_API_KEY.")
    return ctx
