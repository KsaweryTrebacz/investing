"""Jeden cykl doradcy: kontrola danych -> rozliczenie starych rad -> werdykt -> zabezpieczenia
-> analiza, koszty i ryzyko -> status decyzji i raport -> zapis i powiadomienie."""
from dataclasses import dataclass, field

import pandas as pd

from advisor import TRADE, make_verdict
from analysis import checks, direction, market_facts
from config import DEFAULT_INSTRUMENT, Config
from costs import holding_estimate
from decision import finalize, finalize_trend
from events import HIGH, applies, dividend_in, near_now, upcoming
from guards import apply_guards, validate_candles
from momentum import MODE, RESEARCH_NOTE, TrendParams, advise, current_units, recent_backtest, signal
from notify import format_message, should_notify, should_store
from pipeline import prepare
from regime import REGIME_BUY, REGIME_NEUTRAL, REGIME_SELL
from report import build_report, build_trend_report
from resolve import resolve
from risk import fx_rate, liquidation_price, plan_trade, portfolio_check, positions_margin
from strategy import Params

MIN_D1 = 200
EXPIRE_HOURS = 48


@dataclass
class Context:
    """Wszystko poza świecami. Wartości domyślne oznaczają brak danych i raport to wypisze."""
    cfg: Config = field(default_factory=Config)
    instrument: str = DEFAULT_INSTRUMENT
    fx_live: dict = field(default_factory=dict)   # kursy pobrane w tym cyklu
    positions: dict | None = None                 # plik otwartych pozycji
    events: list = field(default_factory=list)
    news: list = field(default_factory=list)
    errors: list = field(default_factory=list)    # błędy pobierania danych dodatkowych
    meta: dict = field(default_factory=dict)      # źródła danych i czasy pobrania
    events_known: bool = False                    # czy jakiekolwiek źródło wydarzeń jest skonfigurowane


def run_cycle(m15, d1, usd, yld, store, send=None, p: Params | None = None, now=None,
              ctx: Context | None = None) -> dict:
    """Rzuca guards.DataError, gdy dane są uszkodzone. Wtedy nic nie jest zapisywane.

    Bez `p` parametry strategii pochodzą z konfiguracji instrumentu (sekcja strategy) i wartości domyślnych.
    """
    ctx = ctx or Context()
    cfg, instr = ctx.cfg, ctx.cfg.instrument(ctx.instrument)
    if instr.mode == MODE:
        return run_trend_cycle(m15, d1, usd, yld, store, send, now, ctx)
    p = p or Params(**instr.strategy)
    validate_candles(m15, "M15", p.ema_len + 50)
    validate_candles(d1, "D1", MIN_D1)
    now = now if now is not None else pd.Timestamp.now(tz="UTC")

    store.upsert_candles("M15", m15)
    store.upsert_candles("D", d1)

    resolved = 0
    for open_v in store.open_verdicts():
        res = resolve(open_v, m15, EXPIRE_HOURS, instr.costs)
        if res:
            store.close_verdict(open_v["id"], *res)
            resolved += 1

    df = prepare(m15, d1, usd, yld, p, macro=instr.macro)
    v = make_verdict(df, p, macro=instr.macro)
    v = apply_guards(v, store, now, m15["time"].iloc[-1])

    facts = market_facts(df, d1)
    holding = holding_estimate(store.resolved_verdicts(50), EXPIRE_HOURS)
    mine = [e for e in ctx.events if applies(e, ctx.instrument, instr.symbol)]
    window = upcoming(mine, now, holding["max_hours"], ctx.instrument, instr.symbol)
    guard_hours = cfg.events.get("guard_hours", 2)
    plan = None
    if v["verdict"] in TRADE:
        held = upcoming(mine, now, holding["hours"], ctx.instrument, instr.symbol)
        plan = plan_trade(v, instr, cfg.account, fx_rate(cfg, instr.quote, ctx.fx_live), holding, now,
                          dividend=dividend_in(held), other_margin=positions_margin(cfg, ctx.positions, ctx.fx_live)[0])
    portfolio = portfolio_check(plan["loss"] if plan else None, ctx.instrument, cfg, ctx.positions, ctx.fx_live)
    v = finalize(v, plan, portfolio, near_now(mine, now, guard_hours), guard_hours, instr.strategy_validated)

    d = direction(facts)
    rows = checks(facts, d, instr.macro, tp=plan["tp"] if plan else None)
    if ctx.events_known and d != 0:
        high = [e["name"] for e in window if e["importance"] == HIGH]
        rows.append({"name": f"Wydarzenia o wysokiej wadze w ciągu {holding['max_hours']} h",
                     "value": ", ".join(high) if high else "brak", "ok": not high})
    v["report"] = build_report(instrument=ctx.instrument, v=v, facts=facts, rows=rows, plan=plan,
                               portfolio=portfolio, holding=holding, window=window, news=ctx.news,
                               errors=ctx.errors, meta=ctx.meta, instr=instr, account=cfg.account, now=now, p=p)

    prev = store.last_verdict()
    stored = should_store(prev, v)
    if stored:
        store.add_verdict(v)
        if send and should_notify(prev, v):
            send(format_message(v))
    store.set_current(v)
    return {"verdict": v, "stored": stored, "resolved": resolved}


D1_STALE_DAYS = 4  # dłużej bez nowej zamkniętej świecy D1 niż weekend z dniem wolnym = dane nieaktualne


def trend_plan(sig: dict, adv: dict, cfg: Config, instr, equity: float, equity_source: str, fx: dict,
               positions: dict | None, fx_live: dict, instrument: str) -> dict:
    """Wartość, depozyt, dźwignia i likwidacja pozycji docelowej w walucie rachunku."""
    m, price, rate = instr.costs.margin_rate, sig["close"], fx["rate"]
    units = abs(adv["target_units"])
    other = positions_margin(cfg, positions, fx_live, exclude=instrument)[0]
    notional = units * price * rate
    fin_rate = instr.costs.financing_long_rate if sig["side"] >= 0 else instr.costs.financing_short_rate
    plan = {"equity": equity, "equity_source": equity_source, "currency": cfg.account.currency, "fx": fx,
            "notional": notional, "margin": notional * m, "leverage": notional / equity, "max_leverage": sig["cap"],
            "free_margin": equity - other - notional * m, "other_margin": other,
            "day_sigma": notional * sig["vol"] / 252 ** 0.5, "move5": notional * 0.05,
            "financing_day": None if fin_rate is None else notional * fin_rate / 365,
            "liquidation_price": None, "liquidation_move": None}
    if units:
        liq = liquidation_price(sig["side"], price, units * rate, equity, m, cfg.account.margin_closeout, other)
        plan.update(liquidation_price=liq, liquidation_move=(liq - price) / price)
    return plan


def run_trend_cycle(m15, d1, usd, yld, store, send, now, ctx: Context) -> dict:
    """Cykl strategii trendowej D1: pozycja docelowa z momentum i dźwigni, raport, zapis, powiadomienie.

    Rada zmienia się raz dziennie (czas werdyktu = świeca D1), więc zapis i powiadomienie są raz na dzień.
    """
    cfg, instr = ctx.cfg, ctx.cfg.instrument(ctx.instrument)
    tp = TrendParams(**instr.trend)
    validate_candles(m15, "M15", Params().ema_len + 50)
    validate_candles(d1, "D1", max(MIN_D1, tp.lookback + tp.vol_window + 1))
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    store.upsert_candles("M15", m15)
    store.upsert_candles("D", d1)
    d1 = d1[d1["time"] + pd.Timedelta(days=1) <= m15["time"].iloc[-1] + pd.Timedelta(minutes=15)]  # zamknięte dni
    d1 = d1.reset_index(drop=True)

    sig = signal(d1, tp, instr.costs.margin_rate)
    stale = now - (d1["time"].iloc[-1] + pd.Timedelta(days=1)) > pd.Timedelta(days=D1_STALE_DAYS)
    fx = fx_rate(cfg, instr.quote, ctx.fx_live)
    pos_eq = (ctx.positions or {}).get("equity")
    equity, eq_src = (pos_eq, "plik pozycji") if pos_eq else (cfg.account.capital, "konfiguracja")
    missing = [name for name, val in (("kapitał rachunku", equity), (f"kurs {instr.quote}/{cfg.account.currency or '?'}", fx),
                                      ("stopa depozytu (dźwignia)", instr.costs.margin_rate)) if val is None]
    fin_missing = ["finansowanie overnight"] if (instr.costs.financing_long_rate if sig["side"] >= 0
                                                 else instr.costs.financing_short_rate) is None else []
    adv = plan = None
    if not missing:
        adv = advise(sig["side"], sig["leverage"], equity, sig["close"], fx["rate"], instr.costs.units_step,
                     current_units(ctx.positions, ctx.instrument), tp.rebalance_band)
        plan = trend_plan(sig, adv, cfg, instr, equity, eq_src, fx, ctx.positions, ctx.fx_live, ctx.instrument)
    decision, reasons = finalize_trend(sig, adv, plan, stale, missing, tp.rebalance_band)
    regime = {1: REGIME_BUY, -1: REGIME_SELL}.get(sig["side"], REGIME_NEUTRAL)
    v = {"time": sig["time"], "verdict": adv["verdict"] if adv and decision == "MOZLIWA_TRANSAKCJA" else "CZEKAJ",
         "regime": regime, "entry": None, "sl": None, "tp": None, "atr": None, "status": "NONE",
         "signal_raw": sig["side"], "action": adv["action"] if adv else None, "decision": decision,
         "decision_reasons": reasons,
         "reasoning": (f"Momentum {sig['lookback']} dni {sig['momentum']:+.1%}, zmienność {sig['vol']:.1%}, dźwignia "
                       f"docelowa {sig['leverage']:.2f}:1 (cel {sig['target_vol']:.0%}, limit {sig['cap']:.0f}:1)."
                       + (f" Rada: {adv['action']}." if adv else ""))}

    facts = market_facts(prepare(m15, d1, usd, yld, Params(), macro=instr.macro), d1)
    rows = [{"name": f"Momentum {sig['lookback']} dni", "value": f"{sig['momentum']:+.1%}",
             "ok": None if sig["side"] == 0 else sig["momentum"] * sig["side"] > 0},
            {"name": "Zmienność 20 dni (roczna)", "value": f"{sig['vol']:.1%} → dźwignia {sig['leverage']:.2f}:1",
             "ok": None}] + checks(facts, sig["side"], instr.macro)
    mine = [e for e in ctx.events if applies(e, ctx.instrument, instr.symbol)]
    window = upcoming(mine, now, EXPIRE_HOURS, ctx.instrument, instr.symbol)
    rates = (instr.costs.financing_long_rate, instr.costs.financing_short_rate)
    hist_fin = (rates[0] if rates[0] is not None else -0.05, rates[1] if rates[1] is not None else -0.01)
    history = {"research": RESEARCH_NOTE,
               "recent": recent_backtest(d1, tp, instr.costs.margin_rate or 0.02, cfg.account.margin_closeout, *hist_fin)}
    v["report"] = build_trend_report(instrument=ctx.instrument, v=v, sig=sig, adv=adv, plan=plan, facts=facts,
                                     rows=rows, window=window, news=ctx.news, errors=ctx.errors, meta=ctx.meta,
                                     instr=instr, account=cfg.account, now=now, missing=missing + fin_missing,
                                     history=history)
    prev = store.last_verdict()
    stored = should_store(prev, v)
    if stored:
        store.add_verdict(v)
        if send and should_notify(prev, v):
            send(format_message(v))
    store.set_current(v)
    return {"verdict": v, "stored": stored, "resolved": 0}
