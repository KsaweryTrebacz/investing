"""Doradca XAU/USD.

  python main.py cycle     [--demo]                 # jeden cykl: werdykt, zapis, powiadomienie
  python main.py dashboard [--demo] [--port 8787]   # lokalna strona z werdyktem
  python main.py validate  [--demo] [--years 3]     # walk-forward: czy reguły mają przewagę poza próbą
"""
import argparse
import os
import sys

import pandas as pd

from macro import USD_SERIES, YIELD_SERIES, fetch_series
from oanda import Oanda, demo_candles, demo_daily, demo_macro

INSTR = "XAU_USD"
HERE = os.path.dirname(os.path.abspath(__file__))


def db_path(demo: bool) -> str:
    """Tryb demo ma osobną bazę, żeby dane syntetyczne nie mieszały się z prawdziwymi radami."""
    return os.path.join(HERE, "goldbot-demo.db" if demo else "goldbot.db")


def get_inputs(demo: bool, n_m15: int, n_d1: int):
    """Zwraca (m15, d1, usd, yld). Brak/awaria makro daje None, a reżim będzie NEUTRALNY."""
    if demo:
        m15 = demo_candles(40000)
        d1 = demo_daily(m15)
        print("UWAGA: dane syntetyczne. Wyniki nie mówią nic o strategii ani o rynku.")
        return (m15, d1, *demo_macro(d1))
    api = Oanda()
    m15, d1 = api.candles(INSTR, "M15", n_m15), api.candles(INSTR, "D", n_d1)
    usd = yld = None
    key = os.environ.get("FRED_API_KEY")
    if not key:
        print("Ostrzeżenie: brak FRED_API_KEY, reżim dzienny będzie NEUTRALNY (brak danych makro).")
    else:
        try:
            usd, yld = fetch_series(USD_SERIES, key), fetch_series(YIELD_SERIES, key)
        except Exception as e:
            usd = yld = None
            print(f"Ostrzeżenie: nie pobrano danych makro ({e}), reżim będzie NEUTRALNY.")
    return m15, d1, usd, yld


def cmd_cycle(args):
    from cycle import run_cycle
    from notify import telegram_sender
    from store import Store

    try:
        m15, d1, usd, yld = get_inputs(args.demo, 1500, 600)
    except Exception as e:
        print(f"Błąd pobierania danych, werdykt nie został wydany: {e}")
        return 1
    send = telegram_sender()
    if send is None:
        print("Telegram nieskonfigurowany (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID), bez powiadomień.")
    if args.demo:
        send = None  # dane syntetyczne nigdy nie trafiają na Telegram
    res = run_cycle(m15, d1, usd, yld, Store(db_path(args.demo)), send)
    v = res["verdict"]
    print(f"{v['time']}  {v['verdict']}  reżim={v['regime']}  zapisano={res['stored']}  "
          f"rozstrzygnięto={res['resolved']}")
    print(v["reasoning"])
    if v["entry"]:
        print(f"Wejście ok. {v['entry']:.2f}  SL {v['sl']:.2f}  TP {v['tp']:.2f}")
    return 0


def cmd_dashboard(args):
    from dashboard import serve
    serve(db_path(args.demo), args.port)
    return 0


def cmd_validate(args):
    from pipeline import prepare
    from validate import walk_forward

    try:
        m15, d1, usd, yld = get_inputs(args.demo, int(args.years * 24000), int(args.years * 365 + 300))
    except Exception as e:
        print(f"Błąd pobierania danych: {e}")
        return 1
    df = prepare(m15, d1, usd, yld)
    res = walk_forward(df, split=args.split)
    pd.set_option("display.width", 200)
    print(f"Świece M15: {len(df)}  ({df.time.iloc[0]} -> {df.time.iloc[-1]}), podział {args.split:.0%}/{1 - args.split:.0%}")
    print(pd.DataFrame(res).T.fillna(0).to_string())
    print("Liczy się okres out_of_sample po kosztach. Mało transakcji oznacza wynik bez znaczenia statystycznego.")
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cycle")
    c.add_argument("--demo", action="store_true")
    d = sub.add_parser("dashboard")
    d.add_argument("--port", type=int, default=8787)
    d.add_argument("--demo", action="store_true", help="pokaż bazę z danymi syntetycznymi")
    v = sub.add_parser("validate")
    v.add_argument("--demo", action="store_true")
    v.add_argument("--years", type=float, default=3.0)
    v.add_argument("--split", type=float, default=0.7)
    args = ap.parse_args()
    return {"cycle": cmd_cycle, "dashboard": cmd_dashboard, "validate": cmd_validate}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
