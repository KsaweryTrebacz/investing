"""Raport w 8 punktach według roli analityka i kontrolera ryzyka CFD oraz jego wersja tekstowa."""
import pandas as pd

from analysis import DIRECTION_PL, direction, strength
from config import Account, Instrument
from costs import per_unit_costs
from decision import DECISION_PL
from regime import REGIME_PL
from risk import GAP_NOTE
from strategy import Params

DISCLAIMER = "Sygnał analityczny, nie porada inwestycyjna. Program nie składa zleceń."
FACTS_NOTE = ("Nagłówki, źródła i daty to fakty. Etykieta sentymentu to automatyczna ocena Alpha Vantage, "
              "czyli interpretacja. Program nie ocenia, co jest już w cenie; zmiana ceny to tylko fakt rynkowy.")
TELEGRAM_LIMIT = 4000


def _invalidation(v, facts, plan, d, holding, window, p: Params) -> list:
    """Warunki, przy których scenariusz przestaje obowiązywać."""
    if d == 0:
        return ["Nie dotyczy: brak scenariusza kierunkowego."]
    s = facts["m15"]["structure"]
    out = []
    if plan:
        out.append(f"Cena dotknie SL {plan['sl']:.2f}; przy luce cenowej wyjście może nastąpić dalej niż SL.")
        out.append(f"Przed wejściem cena przekroczy SL albo spread wzrośnie powyżej {p.max_spread_atr:.0%} ATR.")
        out.append(f"Brak TP w ciągu {holding['max_hours']} h: rada wygasa i jest rozliczana po cenie rynkowej.")
    else:
        out.append(f"Cena M15 zamknie się po drugiej stronie EMA 200 ({facts['m15']['ema200']:.2f}).")
    level = s["last_low"] if d == 1 else s["last_high"]
    if level is not None:
        out.append(f"Zamknięcie M15 {'poniżej ostatniego dołka' if d == 1 else 'powyżej ostatniego szczytu'} {level:.2f} "
                   "(zmiana struktury).")
    out.append("Reżim dzienny zmieni się na neutralny albo przeciwny." if v["regime"] != "NEUTRALNY"
               else "Trend D1 (EMA 50 vs 200) przestanie wskazywać ten kierunek.")
    high = [e for e in window if e["importance"] == "wysoka"]
    if high:
        out.append("Wydarzenie o wysokiej wadze w oknie utrzymania (ryzyko luki): "
                   + "; ".join(f"{e['name']} {e['start'][:16].replace('T', ' ')} UTC" for e in high) + ".")
    return out


def build_report(*, instrument: str, v: dict, facts: dict, rows: list, plan: dict | None, portfolio: dict,
                 holding: dict, window: list, news: list, errors: list, meta: dict, instr: Instrument,
                 account: Account, now, p: Params = Params()) -> dict:
    d = direction(facts)
    c = instr.costs
    if plan:
        pc, missing = plan["costs_per_unit"], plan["missing"]
    elif d != 0:  # szacunek kosztów jednej jednostki dla obserwowanego kierunku
        pc = per_unit_costs(c, d, facts["price"], facts["m15"]["atr"], now, now + pd.Timedelta(hours=holding["hours"]))
        missing = pc["missing"] + ([] if c.margin_rate is not None else ["depozyt (stopa depozytu)"])
    else:
        pc, missing = None, []
    d1_atr = facts["d1"]["atr"]
    pnl = None
    if plan:
        pnl = {k: plan.get(k) for k in ("units", "loss", "gain", "margin", "notional", "budget", "currency", "fx",
                                         "exact", "missing", "risk_per_trade", "leverage", "max_leverage",
                                         "liquidation_price", "liquidation_move", "free_margin")}
        pnl["loss_pct"] = plan["loss"] / account.capital if plan["loss"] is not None else None
    return {
        "instrument": instrument, "currency": account.currency, "time": v["time"], "generated_at": pd.Timestamp(now).isoformat(),
        "decision": v["decision"], "decision_reasons": v["decision_reasons"], "verdict": v["verdict"],
        "data": meta,
        "trend": {"direction": DIRECTION_PL[d], "regime": REGIME_PL[v["regime"]], "strength": strength(rows)},
        "checks": rows,
        "events": {"upcoming": window, "news": news, "errors": errors, "note": FACTS_NOTE,
                   "change_24h": facts["change_24h"], "change_since_d1": facts["change_since_d1"],
                   "d1_atr": d1_atr, "d1_close_time": facts["d1_close_time"]},
        "costs": {"spread": facts["spread"], "spread_atr": facts["spread"] / facts["m15"]["atr"],
                  "per_unit": pc, "quote": instr.quote, "holding": holding, "source": c.source, "as_of": c.as_of,
                  "missing": missing},
        "plan": None if not plan else {"side": plan["side"], "verdict": v.get("held") or v["verdict"],
                                       "entry": plan["entry"], "sl": plan["sl"], "tp": plan["tp"],
                                       "rr": p.tp_atr / p.sl_atr, "held": "held" in v},
        "pnl": pnl, "portfolio": portfolio, "gap_note": GAP_NOTE,
        "invalidation": _invalidation(v, facts, plan, d, holding, window, p),
        "reasoning": v["reasoning"],
    }


def _money(x, cur):
    return "?" if x is None else f"{x:,.2f} {cur or ''}".replace(",", " ").strip()


def _num(x, fmt="{:+.2f}"):
    return "brak danych" if x is None else fmt.format(x)


def render_text(r: dict) -> str:
    """Raport jako tekst (konsola, Telegram)."""
    L = [f"{r['instrument']} | świeca M15 {r['time'][:16].replace('T', ' ')} UTC | "
         f"STATUS: {DECISION_PL[r['decision']].upper()}"]
    data = r["data"] or {}
    for name, info in data.items():
        if info:
            L.append(f"Dane, {name}: " + ", ".join(f"{k} {v}" for k, v in info.items() if v is not None))

    t = r["trend"]
    L.append(f"1. Trend i siła sygnału: {t['direction']}; reżim dzienny {t['regime']}; {t['strength']['text']} "
             "(liczba warunków, nie prawdopodobieństwo).")

    L.append("2. Potwierdzenia i sprzeczności:")
    for mark, ok in (("✓", True), ("✗", False), ("·", None)):
        for row in (x for x in r["checks"] if x["ok"] is ok):
            L.append(f"   {mark} {row['name']}: {row['value']}")

    e = r["events"]
    L.append("3. Wiadomości i wydarzenia:")
    L.append(f"   Rynek: zmiana 24 h {_num(e['change_24h'])}, od zamknięcia D1 ({e['d1_close_time'][:10]}) "
             f"{_num(e['change_since_d1'])}" + (f", ATR D1 {e['d1_atr']:.2f}." if e["d1_atr"] else "."))
    if e["upcoming"]:
        for ev in e["upcoming"]:
            when = ev["start"][:10] + (" (cały dzień)" if ev["all_day"] else " " + ev["start"][11:16] + " UTC")
            note = f"; {ev['note']}" if ev.get("note") else ""
            L.append(f"   Wydarzenie {when}: {ev['name']} [waga {ev['importance']}{note}] "
                     f"źródło: {ev['source']}, pobrano {ev['fetched_at'][:16].replace('T', ' ')} UTC")
    else:
        L.append("   Brak znanych wydarzeń w oknie utrzymania (albo brak skonfigurowanego źródła).")
    for n in e["news"]:
        L.append(f"   Nagłówek: „{n['title']}” ({n['source']}, {n['published']} wg Alpha Vantage, "
                 f"pobrano {n['fetched_at'][:16].replace('T', ' ')} UTC; sentyment wg dostawcy: {n['sentiment']})")
    for err in e["errors"]:
        L.append(f"   Nie pobrano: {err}")
    L.append(f"   {e['note']}")

    c = r["costs"]
    q = c["quote"]
    hold = c["holding"]
    L.append(f"4. Koszty i czas utrzymania: spread {c['spread']:.2f} {q} ({c['spread_atr']:.0%} ATR M15, "
             "wliczony w ceny bid/ask)")
    if c["per_unit"]:
        pu = c["per_unit"]
        fmt = lambda k: "brak danych" if pu[k] is None else f"{pu[k]:.4f} {q}"  # noqa: E731
        L.append(f"   na jednostkę (dodatnie = koszt, ujemne = przychód): prowizja (obie strony) {fmt('commission')}, finansowanie {fmt('financing')} "
                 f"({pu['financing_days']} dn.), poślizg na SL {fmt('slippage')}"
                 + (f", korekta dywidendowa {pu['dividend']:+.4f} {q}" if pu.get("dividend") is not None else ""))
    L.append(f"   czas utrzymania: ok. {hold['hours']:g} h ({hold['basis']}), najdłużej {hold['max_hours']} h.")
    L.append(f"   źródło kosztów: {c['source'] or 'brak'}, stan na {c['as_of'] or 'brak daty'}.")
    if c["missing"]:
        L.append("   BRAK DANYCH: " + ", ".join(c["missing"]) + ". Wyniki poniżej są orientacyjne, nie dokładne.")

    pl = r["plan"]
    if pl:
        held = " (WSTRZYMANY, tylko do wglądu)" if pl["held"] else ""
        L.append(f"5. Plan{held}: {pl['verdict']} ok. {pl['entry']:.2f}, SL {pl['sl']:.2f}, TP {pl['tp']:.2f} "
                 f"(zysk do ryzyka 1:{pl['rr']:g}).")
    else:
        L.append("5. Plan: brak, nie ma sygnału wejścia.")

    m = r["pnl"]
    if m:
        cur = m["currency"]
        if m["units"] is None:
            L.append("6. Zysk i strata w walucie rachunku: nie da się policzyć, brak kapitału albo kursu waluty.")
        else:
            fx = m["fx"]
            how = "szacunek, dane o kosztach kompletne" if m["exact"] else "ORIENTACYJNIE, brak części danych"
            L.append(f"6. Zysk i strata ({how}): pozycja {m['units']:g} jedn., "
                     f"strata przy SL ok. {_money(m['loss'], cur)} ({m['loss_pct']:.2%} kapitału, budżet "
                     f"{m['risk_per_trade']:.1%} = {_money(m['budget'], cur)}), zysk przy TP po kosztach ok. "
                     f"{_money(m['gain'], cur)}, depozyt {_money(m['margin'], cur)}, wartość {_money(m['notional'], cur)}; "
                     f"kurs {fx['rate']:.4f} ({fx['source']}{', ' + str(fx['as_of']) if fx.get('as_of') else ''}).")
            if m.get("leverage") is not None:
                L.append(f"   Dźwignia: {m['leverage']:.1f}:1 z dostępnych {m['max_leverage']:.0f}:1; wolny depozyt po "
                         f"otwarciu {_money(m['free_margin'], cur)}; broker zlikwiduje pozycję przy cenie "
                         f"{m['liquidation_price']:.2f} (ruch {m['liquidation_move']:+.1%} od wejścia).")
            else:
                L.append("   Dźwignia i poziom likwidacji: nieznane (brak stopy depozytu w konfiguracji).")
    else:
        L.append("6. Zysk i strata: nie dotyczy, brak planu transakcji.")
    pf = r["portfolio"]
    if pf["available"]:
        cur = r["currency"]
        L.append(f"   Portfel ({pf['count']} poz., stan na {pf['as_of'] or 'brak daty'}): ryzyko otwartych pozycji "
                 f"{_money(pf['total'], cur)}, w grupie „{pf['group']}” {_money(pf['group_total'], cur)}"
                 + (f"; limity {_money(pf['total_limit'], cur)} / {_money(pf['group_limit'], cur)}"
                    if pf["total_limit"] else "") + ".")
    for reason in pf["reasons"]:
        L.append(f"   {reason}")
    L.append(f"   {r['gap_note']}")

    L.append("7. Warunki unieważniające scenariusz:")
    L += [f"   - {x}" for x in r["invalidation"]]
    L.append(f"8. Status: {DECISION_PL[r['decision']].upper()}. " + " ".join(r["decision_reasons"]))
    L.append(DISCLAIMER)
    return "\n".join(L)


def render_telegram(r: dict) -> str:
    text = render_text(r)
    if len(text) <= TELEGRAM_LIMIT:
        return text
    return text[:TELEGRAM_LIMIT - 150] + "\n[…] pełny raport na dashboardzie.\n" + DISCLAIMER
