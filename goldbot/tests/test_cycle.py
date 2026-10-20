from cycle import run_cycle
from oanda import demo_candles, demo_daily, demo_macro
from store import Store


def inputs():
    m15 = demo_candles(30000)
    d1 = demo_daily(m15)
    usd, yld = demo_macro(d1)
    return m15, d1, usd, yld


def test_first_cycle_stores_and_notifies_once_then_stays_quiet():
    store, sent = Store(), []
    m15, d1, usd, yld = inputs()

    r1 = run_cycle(m15, d1, usd, yld, store, sent.append)
    assert r1["stored"] and len(sent) == 1
    assert r1["verdict"]["verdict"] in ("KUP", "SPRZEDAJ", "CZEKAJ")

    r2 = run_cycle(m15, d1, usd, yld, store, sent.append)
    assert not r2["stored"] and len(sent) == 1
    assert store.get_current()["time"] == r1["verdict"]["time"]


def test_cycle_without_notifier_still_stores():
    store = Store()
    m15, d1, usd, yld = inputs()
    assert run_cycle(m15, d1, usd, yld, store)["stored"]
    assert store.last_verdict() is not None
    assert len(store.load_candles("M15", 10**6)) == len(m15)
