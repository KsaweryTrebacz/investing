"""Jeden cykl doradcy: dane -> reżim i sygnał -> werdykt -> zapis -> powiadomienie."""
from advisor import make_verdict
from notify import format_message, should_notify, should_store
from pipeline import prepare
from resolve import resolve
from strategy import Params


def run_cycle(m15, d1, usd, yld, store, send=None, p: Params = Params()) -> dict:
    store.upsert_candles("M15", m15)
    store.upsert_candles("D", d1)

    v = make_verdict(prepare(m15, d1, usd, yld, p), p)

    resolved = 0
    for open_v in store.open_verdicts():
        res = resolve(open_v, m15)
        if res:
            store.close_verdict(open_v["id"], *res)
            resolved += 1

    prev = store.last_verdict()
    stored = should_store(prev, v)
    if stored:
        store.add_verdict(v)
        if send and should_notify(prev, v):
            send(format_message(v))
    store.set_current(v)
    return {"verdict": v, "stored": stored, "resolved": resolved}
