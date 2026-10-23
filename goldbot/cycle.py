"""Jeden cykl doradcy: kontrola danych -> rozliczenie starych rad -> werdykt -> zabezpieczenia -> zapis."""
import pandas as pd

from advisor import make_verdict
from guards import apply_guards, validate_candles
from notify import format_message, should_notify, should_store
from pipeline import prepare
from resolve import resolve
from strategy import Params

MIN_D1 = 200


def run_cycle(m15, d1, usd, yld, store, send=None, p: Params = Params(), now=None, costs=None) -> dict:
    """Rzuca guards.DataError, gdy dane są uszkodzone. Wtedy nic nie jest zapisywane."""
    validate_candles(m15, "M15", p.ema_len + 50)
    validate_candles(d1, "D1", MIN_D1)
    now = now if now is not None else pd.Timestamp.now(tz="UTC")

    store.upsert_candles("M15", m15)
    store.upsert_candles("D", d1)

    resolved = 0
    for open_v in store.open_verdicts():
        res = resolve(open_v, m15, costs=costs)
        if res:
            store.close_verdict(open_v["id"], *res)
            resolved += 1

    v = make_verdict(prepare(m15, d1, usd, yld, p), p)
    v = apply_guards(v, store, now, m15["time"].iloc[-1])

    prev = store.last_verdict()
    stored = should_store(prev, v)
    if stored:
        store.add_verdict(v)
        if send and should_notify(prev, v):
            send(format_message(v))
    store.set_current(v)
    return {"verdict": v, "stored": stored, "resolved": resolved}
