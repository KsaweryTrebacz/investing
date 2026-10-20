from macro import parse_observations
from notify import format_message, should_notify, should_store, telegram_sender


def v(t, verdict="CZEKAJ", regime="NEUTRALNY"):
    return {"time": t, "verdict": verdict, "regime": regime, "entry": 2000.0, "sl": 1991.0, "tp": 2018.0,
            "reasoning": "powód"}


def test_parse_observations_skips_missing_values():
    s = parse_observations({"observations": [{"date": "2026-01-02", "value": "1.5"},
                                             {"date": "2026-01-05", "value": "."},
                                             {"date": "2026-01-06", "value": "1.7"}]})
    assert s.tolist() == [1.5, 1.7]
    assert str(s.index[0].date()) == "2026-01-02"


def test_first_verdict_is_stored_and_notified():
    assert should_store(None, v("t1")) and should_notify(None, v("t1"))


def test_same_candle_is_ignored():
    assert not should_store(v("t1"), v("t1", "KUP")) and not should_notify(v("t1"), v("t1", "KUP"))


def test_new_trade_verdict_is_stored_and_notified():
    assert should_store(v("t1"), v("t2", "KUP")) and should_notify(v("t1"), v("t2", "KUP"))


def test_wait_after_trade_is_stored_but_silent():
    prev, new = v("t1", "KUP"), v("t2", "CZEKAJ")
    assert should_store(prev, new) and not should_notify(prev, new)


def test_regime_change_is_stored_and_notified():
    prev, new = v("t1"), v("t2", "CZEKAJ", "SPRZYJA_KUPNIE")
    assert should_store(prev, new) and should_notify(prev, new)


def test_unchanged_wait_is_neither():
    assert not should_store(v("t1"), v("t2")) and not should_notify(v("t1"), v("t2"))


def test_message_has_levels_and_disclaimer():
    m = format_message(v("t1", "KUP", "SPRZYJA_KUPNIE"))
    assert "KUP" in m and "SL 1991.00" in m and "nie porada inwestycyjna" in m


def test_telegram_sender_none_without_config(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert telegram_sender() is None
