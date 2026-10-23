import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from cycle import run_cycle
from dashboard import build_state, make_handler
from oanda import demo_candles, demo_daily, demo_macro
from store import Store


def filled_store(path=":memory:"):
    store = Store(path)
    m15 = demo_candles(30000)
    d1 = demo_daily(m15)
    run_cycle(m15, d1, *demo_macro(d1), store)
    return store


def test_build_state_keys_and_limits():
    s = build_state(filled_store(), n_candles=200)
    assert {"last_update", "latest", "recent", "stats", "candles", "marks"} <= set(s)
    assert len(s["candles"]) == 200
    assert s["latest"]["verdict"] in ("KUP", "SPRZEDAJ", "CZEKAJ")


def test_build_state_on_empty_store():
    s = build_state(Store())
    assert s["latest"] is None and s["candles"] == [] and s["last_update"] is None


def test_http_serves_page_and_state(tmp_path):
    db = str(tmp_path / "t.db")
    filled_store(db).db.close()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(db))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert b"DORADCA CFD" in urllib.request.urlopen(base + "/").read()
        state = json.loads(urllib.request.urlopen(base + "/api/state").read())
        assert state["latest"]["verdict"] in ("KUP", "SPRZEDAJ", "CZEKAJ")
    finally:
        server.shutdown()
