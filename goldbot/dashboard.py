"""Dashboard: mały lokalny serwer (tylko 127.0.0.1) czytający bazę SQLite."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from advisor import TRADE
from store import Store

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def build_state(store: Store, n_candles: int = 200) -> dict:
    c = store.load_candles("M15", n_candles)
    mid = ((c["bid_c"] + c["ask_c"]) / 2).round(2)
    recent = store.recent_verdicts(20)
    return {
        "last_update": c["time"].iloc[-1].isoformat() if len(c) else None,
        "latest": store.get_current(),
        "recent": recent,
        "stats": store.stats(),
        "candles": [{"t": t.isoformat(), "c": float(v)} for t, v in zip(c["time"], mid)],
        "marks": [{"t": r["time"], "verdict": r["verdict"], "entry": r["entry"]}
                  for r in recent if r["verdict"] in TRADE],
    }


def make_handler(db_path: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                with open(os.path.join(WEB, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                body = json.dumps(build_state(Store(db_path)), default=str).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            else:
                self._send(404, b"404", "text/plain")

        def log_message(self, *args):
            pass
    return Handler


def serve(db_path: str, port: int = 8787):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(db_path))
    print(f"Dashboard: http://localhost:{port}/  (Ctrl+C aby zatrzymać)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
