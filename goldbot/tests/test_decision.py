from decision import NO_TRADE, POSSIBLE, WATCH, finalize

TRADE = {"time": "t", "verdict": "KUP", "regime": "SPRZYJA_KUPNIE", "entry": 2000.0, "sl": 1990.0, "tp": 2020.0,
         "atr": 6.0, "reasoning": "Powód.", "status": "OPEN", "signal_raw": 1}
PLAN = {"units": 2.0, "missing": [], "risk_per_trade": 0.005, "budget": 50.0, "currency": "PLN"}
PF_OK = {"ok": True, "exceeded": False, "reasons": []}


def test_clean_trade_is_possible():
    v = finalize(TRADE, PLAN, PF_OK, [], 2)
    assert v["decision"] == POSSIBLE and v["verdict"] == "KUP" and v["entry"] == 2000.0


def test_event_nearby_downgrades_to_watch():
    near = [{"name": "FOMC", "start": "2026-10-23T18:00:00+00:00"}]
    v = finalize(TRADE, PLAN, PF_OK, near, 2)
    assert v["decision"] == WATCH and v["verdict"] == "CZEKAJ" and v["entry"] is None and v["held"] == "KUP"
    assert "FOMC" in v["reasoning"] and v["status"] == "NONE"


def test_unknown_capital_is_watch_and_too_small_is_no_trade():
    v = finalize(TRADE, {**PLAN, "units": None, "missing": ["kapitał rachunku"]}, PF_OK, [], 2)
    assert v["decision"] == WATCH and "kapitał rachunku" in v["decision_reasons"][0]
    v = finalize(TRADE, {**PLAN, "units": 0}, PF_OK, [], 2)
    assert v["decision"] == NO_TRADE and "minimalną" in v["decision_reasons"][0]


def test_portfolio_limit_is_no_trade_unknown_is_watch():
    over = {"ok": False, "exceeded": True, "reasons": ["Łączne ryzyko z nową pozycją 250.00 przekracza limit 200.00."]}
    assert finalize(TRADE, PLAN, over, [], 2)["decision"] == NO_TRADE
    unknown = {"ok": None, "exceeded": False, "reasons": ["Brak pliku otwartych pozycji: łączne ryzyko portfela nieznane."]}
    v = finalize(TRADE, PLAN, unknown, [], 2)
    assert v["decision"] == WATCH and "Brak pliku" in v["decision_reasons"][0]


def wait(**kw):
    return {**TRADE, "verdict": "CZEKAJ", "entry": None, "sl": None, "tp": None, "status": "NONE", "signal_raw": 0, **kw}


def test_guard_blocks_are_no_trade():
    v = finalize(wait(blocked=["open_advice"]), None, PF_OK, [], 2)
    assert v["decision"] == NO_TRADE and "otwarta" in v["decision_reasons"][0]
    assert finalize(wait(blocked=["spread"], signal_raw=1), None, PF_OK, [], 2)["decision"] == NO_TRADE


def test_waiting_states():
    assert finalize(wait(), None, PF_OK, [], 2)["decision"] == WATCH                    # reżim wskazuje kierunek
    assert finalize(wait(regime="SPRZYJA_SPRZEDAZY", signal_raw=1), None, PF_OK, [], 2)["decision"] == WATCH
    assert finalize(wait(regime="NEUTRALNY", signal_raw=1), None, PF_OK, [], 2)["decision"] == WATCH
    v = finalize(wait(regime="NEUTRALNY"), None, PF_OK, [], 2)
    assert v["decision"] == NO_TRADE and "neutralny" in v["decision_reasons"][0]
