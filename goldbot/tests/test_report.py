import pandas as pd

from config import Account, Config, Costs, Instrument
from cycle import Context, run_cycle
from events import make_event
from oanda import demo_candles, demo_daily, demo_macro
from report import TELEGRAM_LIMIT, render_telegram, render_text
from store import Store

FULL = demo_candles(40000)
D1_ALL = demo_daily(FULL)
USD_ALL, YLD_ALL = demo_macro(D1_ALL)


def inputs(n):
    """Stan rynku demo po n świecach: tylko zamknięte dni D1 i makro sprzed bieżącego dnia."""
    m15 = FULL.iloc[n - 1500:n].reset_index(drop=True)
    now = m15["time"].iloc[-1] + pd.Timedelta(minutes=16)
    d1 = D1_ALL[D1_ALL["time"] + pd.Timedelta(days=1) <= now].reset_index(drop=True)
    day = now.normalize().tz_localize(None)
    return m15, d1, USD_ALL[USD_ALL.index < day], YLD_ALL[YLD_ALL.index < day], now


def config():
    cfg = Config(account=Account(currency="PLN", capital=20_000),
                 fx_rates={"USDPLN": {"rate": 3.65, "as_of": "2026-10-22", "source": "NBP"}})
    cfg.instruments = {"XAU_USD": Instrument(group="metale", strategy_validated=True, costs=Costs(
        source="tabela opłat", as_of="2026-10-01", margin_rate=0.05, commission_per_unit=0.0,
        financing_long_rate=-0.065, financing_short_rate=0.02, slippage_atr=0.1))}
    return cfg


SIGNAL_AT = 28065  # świeca demo z sygnałem SPRZEDAJ zgodnym z reżimem (2026-10-20 08:00)


def run(n=SIGNAL_AT, **ctx_kw):
    m15, d1, usd, yld, now = inputs(n)
    ctx = Context(cfg=config(), positions={"as_of": "x", "positions": []}, **ctx_kw)
    return run_cycle(m15, d1, usd, yld, Store(), now=now, ctx=ctx)["verdict"], now


def test_possible_trade_report_has_all_sections():
    v, _ = run()
    r = v["report"]
    assert v["decision"] == "MOZLIWA_TRANSAKCJA" and v["verdict"] == "SPRZEDAJ"
    assert r["pnl"]["units"] > 0 and r["pnl"]["loss"] <= r["pnl"]["budget"] and r["pnl"]["exact"]
    text = render_text(r)
    for i in range(1, 9):
        assert f"\n{i}. " in text, i
    assert "PLN" in text and "nie porada inwestycyjna" in text and "nie gwarantuje" in text


def test_event_nearby_holds_the_trade():
    m15, *_, now = inputs(SIGNAL_AT)
    ev = make_event((now + pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"), "FOMC", "plik", now, scope="USD")
    v, _ = run(events=[ev], events_known=True)
    assert v["decision"] == "OBSERWACJA" and v["verdict"] == "CZEKAJ"
    assert v["report"]["plan"]["held"] and "WSTRZYMANY" in render_text(v["report"])
    assert any(r["name"].startswith("Wydarzenia o wysokiej wadze") and r["ok"] is False for r in v["report"]["checks"])


def test_without_positions_file_trade_is_only_watch():
    m15, d1, usd, yld, now = inputs(SIGNAL_AT)
    v = run_cycle(m15, d1, usd, yld, Store(), now=now, ctx=Context(cfg=config()))["verdict"]
    assert v["decision"] == "OBSERWACJA" and "Brak pliku" in " ".join(v["decision_reasons"])


def test_missing_costs_are_flagged_as_approximate():
    m15, d1, usd, yld, now = inputs(SIGNAL_AT)
    cfg = config()
    cfg.instruments["XAU_USD"].costs = Costs()
    v = run_cycle(m15, d1, usd, yld, Store(), now=now,
                  ctx=Context(cfg=cfg, positions={"positions": []}))["verdict"]
    text = render_text(v["report"])
    assert "ORIENTACYJNIE" in text and "BRAK DANYCH" in text and "prowizja" in text


def test_news_and_errors_are_shown_with_sources():
    news = [{"title": "Fed holds", "source": "Reuters", "url": "", "published": "2026-10-20 07:00",
             "sentiment": "Neutral", "fetched_at": "2026-10-20T08:10:00+00:00"}]
    v, _ = run(news=news, errors=["Kalendarz FRED: timeout."])
    text = render_text(v["report"])
    assert "„Fed holds” (Reuters, 2026-10-20 07:00 wg Alpha Vantage" in text and "interpretacja" in text
    assert "Nie pobrano: Kalendarz FRED: timeout." in text


def test_telegram_message_is_limited_and_keeps_disclaimer():
    v, _ = run()
    r = dict(v["report"], decision_reasons=["x" * 5000])
    msg = render_telegram(r)
    assert len(msg) <= TELEGRAM_LIMIT and msg.endswith("Program nie składa zleceń.")


def test_default_config_does_not_recommend_unvalidated_strategy():
    m15, d1, usd, yld, now = inputs(SIGNAL_AT)
    cfg = config()
    cfg.instruments["XAU_USD"].strategy_validated = False
    v = run_cycle(m15, d1, usd, yld, Store(), now=now, ctx=Context(cfg=cfg, positions={"positions": []}))["verdict"]
    assert v["decision"] == "OBSERWACJA" and "WSTRZYMANY" in render_text(v["report"])
