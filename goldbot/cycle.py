"""Jeden cykl doradcy: kontrola danych -> rozliczenie starych rad -> werdykt -> zabezpieczenia
-> analiza, koszty i ryzyko -> status decyzji i raport -> zapis i powiadomienie."""
from dataclasses import dataclass, field

import pandas as pd

from advisor import TRADE, make_verdict
from analysis import checks, direction, market_facts
from config import DEFAULT_INSTRUMENT, Config
from costs import holding_estimate
from decision import finalize
from events import HIGH, applies, dividend_in, near_now, upcoming
from guards import apply_guards, validate_candles
from notify import format_message, should_notify, should_store
from pipeline import prepare
from report import build_report
from resolve import resolve
from risk import fx_rate, plan_trade, portfolio_check
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
                          dividend=dividend_in(held))
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
