"""Status decyzji: MOZLIWA_TRANSAKCJA, OBSERWACJA albo BRAK_TRANSAKCJI, z blokadami ryzyka.

Twarde blokady (nieaktualne dane, otwarta rada, dzienny limit, spread, za mała pozycja, limit portfela)
dają brak transakcji. Miękkie (wydarzenie, brak kapitału, kursu lub danych o portfelu) dają obserwację.
"""
from advisor import TRADE
from regime import REGIME_BUY, REGIME_SELL

POSSIBLE, WATCH, NO_TRADE = "MOZLIWA_TRANSAKCJA", "OBSERWACJA", "BRAK_TRANSAKCJI"
DECISION_PL = {POSSIBLE: "możliwa transakcja", WATCH: "obserwacja", NO_TRADE: "brak transakcji"}
UNVALIDATED = ("Strategia nie ma potwierdzonej przewagi poza próbą: w badaniu na publicznych danych złota 2008-2024 "
               "średni wynik to -0,16R na transakcję po kosztach, a bez kosztów około 0R (docs/research). "
               "Rada jest tylko do obserwacji; strategy_validated=true ustaw dopiero po dodatnim wyniku "
               "validate na danych Twojego brokera.")
BLOCK_PL = {"stale": "dane są nieaktualne", "open_advice": "poprzednia rada jest jeszcze otwarta",
            "daily_loss": "osiągnięty dzienny limit strat rad", "spread": "spread jest za szeroki względem ATR"}


def risk_blocks(plan: dict, portfolio: dict, near: list, guard_hours: float) -> tuple[list, list]:
    """(twarde, miękkie) powody wstrzymania rady handlowej."""
    hard, soft = [], []
    if near:
        names = ", ".join(f"{e['name']} ({e['start'][:16].replace('T', ' ')} UTC)" for e in near)
        soft.append(f"Wydarzenie o wysokiej wadze w odległości mniejszej niż {guard_hours:g} h: {names}.")
    if plan["units"] is None:
        absent = [m for m in plan["missing"] if m.startswith(("kapitał", "kurs"))]
        soft.append("Nie można policzyć wielkości pozycji w walucie rachunku, brak: " + ", ".join(absent) + ".")
    elif plan["units"] <= 0:
        hard.append(f"Ryzyko {plan['risk_per_trade']:.1%} kapitału ({plan['budget']:.2f} {plan['currency']}) "
                    "nie wystarcza na minimalną wielkość pozycji przy tym SL i kosztach.")
    elif plan.get("free_margin") is not None and plan["free_margin"] < 0:
        hard.append(f"Brak wolnego depozytu: pozycja wymaga {plan['margin']:.2f} {plan['currency']} przy dźwigni "
                    f"{plan['leverage']:.1f}:1 (maks. {plan['max_leverage']:.0f}:1).")
    elif plan.get("sl_beyond_liquidation"):
        hard.append(f"Broker zlikwidowałby pozycję przy cenie {plan['liquidation_price']:.2f}, zanim cena dojdzie "
                    f"do SL {plan['sl']:.2f}.")
    if portfolio["exceeded"]:
        hard += [r for r in portfolio["reasons"] if "przekracza limit" in r]
    elif portfolio["ok"] is not True:
        soft += portfolio["reasons"] or ["Nie można sprawdzić limitów ryzyka portfela."]
    return hard, soft


def finalize(v: dict, plan: dict | None, portfolio: dict, near: list, guard_hours: float,
             validated: bool = True) -> dict:
    """v: werdykt po guards.apply_guards. Zwraca kopię z `decision` i `decision_reasons`.

    Rada handlowa zatrzymana przez blokadę ryzyka zamienia się w CZEKAJ, a powód trafia do uzasadnienia.
    Strategia bez walidacji (validated=False) daje najwyżej obserwację.
    """
    out = dict(v)
    if v["verdict"] in TRADE:
        hard, soft = risk_blocks(plan, portfolio, near, guard_hours)
        if not validated:
            soft.append(UNVALIDATED)
        if not (hard or soft):
            return dict(out, decision=POSSIBLE, decision_reasons=[
                "Sygnał M15 zgodny z reżimem dziennym; zabezpieczenia i limity ryzyka spełnione."])
        out.update(verdict="CZEKAJ", entry=None, sl=None, tp=None, status="NONE")
        out["reasoning"] = f"{v['reasoning']} Sygnał {v['verdict']} wstrzymany: {' '.join(hard + soft)}"
        return dict(out, decision=NO_TRADE if hard else WATCH, decision_reasons=hard + soft, held=v["verdict"])

    blocked = [BLOCK_PL[b] for b in v.get("blocked", []) if b in BLOCK_PL]
    if blocked:
        return dict(out, decision=NO_TRADE, decision_reasons=["Brak transakcji: " + ", ".join(blocked) + "."])
    if v["regime"] in (REGIME_BUY, REGIME_SELL):
        why = ("Sygnał M15 jest przeciwny do reżimu dziennego." if v.get("signal_raw")
               else "Reżim dzienny wskazuje kierunek, brak sygnału wejścia M15.")
        return dict(out, decision=WATCH, decision_reasons=[why])
    if v.get("signal_raw"):
        return dict(out, decision=WATCH, decision_reasons=["Sygnał M15 bez potwierdzenia reżimu dziennego (neutralny)."])
    return dict(out, decision=NO_TRADE, decision_reasons=["Reżim dzienny neutralny i brak sygnału M15."])
