"""Doradca i kontroler ryzyka CFD (domyślnie XAU/USD). Tylko doradza, nie składa zleceń.

  python main.py cycle     [--demo] [--instrument X]                 # cykl dla instrumentów z konfiguracji
  python main.py dashboard [--demo] [--instrument X] [--port 8787]   # lokalna strona z raportem
  python main.py validate  [--demo] [--instrument X] [--years 3]     # walk-forward: przewaga poza próbą?
"""
import argparse
import os
import sys

import pandas as pd

from config import DEFAULT_INSTRUMENT, Config, Instrument, load_config
from costs import cost_coverage
from guards import DataError, validate_candles
from macro import USD_SERIES, YIELD_SERIES, fetch_series
from oanda import Oanda, demo_candles, demo_daily, demo_macro

HERE = os.path.dirname(os.path.abspath(__file__))


def db_path(demo: bool, instrument: str = DEFAULT_INSTRUMENT) -> str:
    """Osobna baza na instrument. Tryb demo ma własne bazy, żeby dane syntetyczne nie mieszały się z prawdziwymi."""
    suffix = "" if instrument == DEFAULT_INSTRUMENT else f"-{instrument}"
    return os.path.join(HERE, f"goldbot{'-demo' if demo else ''}{suffix}.db")


def get_inputs(cfg: Config, instr: Instrument, demo: bool, n_m15: int, n_d1: int, api=None):
    """Zwraca (m15, d1, usd, yld, meta). Brak/awaria makro daje None, a reżim złota będzie NEUTRALNY."""
    now = pd.Timestamp.now(tz="UTC")
    if demo:
        m15 = demo_candles(40000)
        d1 = demo_daily(m15)
        print("UWAGA: dane syntetyczne. Wyniki nie mówią nic o strategii ani o rynku.")
        usd, yld = demo_macro(d1) if instr.macro else (None, None)
        return m15, d1, usd, yld, {"świece": {"źródło": "dane demo (syntetyczne, nie rynkowe)"}}
    if instr.source == "csv":
        from tradingview import load_csv
        spread = instr.csv.get("spread")
        m15 = load_csv(cfg.resolve_path(instr.csv["m15"]), spread, "M15", now)
        d1 = load_csv(cfg.resolve_path(instr.csv["d1"]), spread, "D", now)
        source = f"eksport CSV z TradingView (bid/ask z typowego spreadu {spread}, nie bieżące)"
    else:
        api = api or Oanda()
        m15, d1 = api.candles(instr.name, "M15", n_m15), api.candles(instr.name, "D", n_d1)
        source = "OANDA Practice (bid/ask)"
    meta = {"świece": {"źródło": source, "pobrano": now.strftime("%Y-%m-%d %H:%M UTC")}}
    usd, yld, meta["makro"] = get_macro() if instr.macro else (None, None, None)
    return m15, d1, usd, yld, meta


def get_macro():
    """(usd, yld, meta) z FRED albo (None, None, meta). Nieaktualne dane makro są traktowane jak brak."""
    from guards import macro_is_stale

    key = os.environ.get("FRED_API_KEY")
    if not key:
        print("Ostrzeżenie: brak FRED_API_KEY, reżim dzienny będzie NEUTRALNY (brak danych makro).")
        return None, None, {"źródło": "brak (FRED_API_KEY), reżim neutralny"}
    try:
        usd, yld = fetch_series(USD_SERIES, key), fetch_series(YIELD_SERIES, key)
    except Exception as e:
        print(f"Ostrzeżenie: nie pobrano danych makro ({e}), reżim będzie NEUTRALNY.")
        return None, None, {"źródło": f"FRED, błąd pobierania ({e}), reżim neutralny"}
    now = pd.Timestamp.now(tz="UTC")
    for name, s in (("dolar", usd), ("rentowności", yld)):
        if s.empty or macro_is_stale(s, now):
            print(f"Ostrzeżenie: dane makro ({name}) są nieaktualne, reżim będzie NEUTRALNY.")
            return None, None, {"źródło": f"FRED, dane nieaktualne ({name}), reżim neutralny"}
    return usd, yld, {"źródło": "FRED", f"{USD_SERIES} ostatnia obserwacja": str(usd.index.max().date()),
                      f"{YIELD_SERIES} ostatnia obserwacja": str(yld.index.max().date()),
                      "pobrano": now.strftime("%Y-%m-%d %H:%M UTC")}


def run_instrument(cfg: Config, name: str, demo: bool, send, api=None) -> int:
    from cycle import run_cycle
    from report import render_text
    from sources import gather
    from store import Store

    instr = cfg.instrument(name)
    try:
        if api is None and not demo and instr.source == "oanda":
            api = Oanda()
        m15, d1, usd, yld, meta = get_inputs(cfg, instr, demo, 1500, 600, api)
    except Exception as e:
        print(f"{name}: błąd pobierania danych, werdykt nie został wydany: {e}")
        return 1
    store = Store(db_path(demo, name))
    now = m15["time"].iloc[-1] + pd.Timedelta(minutes=16) if demo else pd.Timestamp.now(tz="UTC")  # demo: własny zegar
    ctx = gather(cfg, name, store, now, demo, api, meta)
    try:
        res = run_cycle(m15, d1, usd, yld, store, None if demo else send, now=now, ctx=ctx)
    except DataError as e:
        print(f"{name}: dane odrzucone, werdykt nie został wydany: {e}")
        return 1
    v = res["verdict"]
    print(f"zapisano={res['stored']}  rozstrzygnięto={res['resolved']}")
    print(render_text(v["report"]))
    print()
    return 0


def cmd_cycle(args):
    from notify import telegram_sender

    cfg = load_config()
    names = [args.instrument] if args.instrument else list(cfg.instruments)
    send = None if args.demo else telegram_sender()  # dane syntetyczne nigdy nie trafiają na Telegram
    if send is None and not args.demo:
        print("Telegram nieskonfigurowany (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID), bez powiadomień.")
    if cfg.path is None:
        print("Brak config.json: kapitał, waluta rachunku i koszty nieznane (wzór w config.example.json).")
    return max(run_instrument(cfg, n, args.demo, send) for n in names)


def cmd_dashboard(args):
    from dashboard import serve
    serve(db_path(args.demo, args.instrument or DEFAULT_INSTRUMENT), args.port)
    return 0


def cmd_validate(args):
    from pipeline import prepare
    from strategy import Params
    from validate import walk_forward

    cfg = load_config()
    instr = cfg.instrument(args.instrument or DEFAULT_INSTRUMENT)
    try:
        m15, d1, usd, yld, _ = get_inputs(cfg, instr, args.demo, int(args.years * 24000), int(args.years * 365 + 300))
    except Exception as e:
        print(f"Błąd pobierania danych: {e}")
        return 1
    try:
        validate_candles(m15, "M15", 1000)
        validate_candles(d1, "D1", 200)
    except DataError as e:
        print(f"Dane odrzucone: {e}")
        return 1
    p = Params(**{**instr.strategy, "risk_per_trade": cfg.account.risk_per_trade})
    df = prepare(m15, d1, usd, yld, p, macro=instr.macro)
    res = walk_forward(df, p, split=args.split, costs=instr.costs)
    pd.set_option("display.width", 200)
    print(f"{instr.name}: świece M15 {len(df)}  ({df.time.iloc[0]} -> {df.time.iloc[-1]}), "
          f"podział {args.split:.0%}/{1 - args.split:.0%}, ryzyko {cfg.account.risk_per_trade:.1%} na transakcję")
    print(pd.DataFrame(res).T.fillna(0).to_string())
    included, missing = cost_coverage(instr.costs)
    print("Uwzględnione koszty: " + ", ".join(included) + ".")
    if missing:
        print("BRAK DANYCH o kosztach: " + ", ".join(missing) + ". Wynik jest zawyżony o te koszty, "
              "uzupełnij je w config.json (sekcja costs instrumentu).")
    print("Liczy się okres out_of_sample. Mało transakcji oznacza wynik bez znaczenia statystycznego.")
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cycle")
    c.add_argument("--demo", action="store_true")
    c.add_argument("--instrument", help="tylko ten instrument (domyślnie wszystkie z konfiguracji)")
    d = sub.add_parser("dashboard")
    d.add_argument("--port", type=int, default=8787)
    d.add_argument("--demo", action="store_true", help="pokaż bazę z danymi syntetycznymi")
    d.add_argument("--instrument")
    v = sub.add_parser("validate")
    v.add_argument("--demo", action="store_true")
    v.add_argument("--instrument")
    v.add_argument("--years", type=float, default=3.0)
    v.add_argument("--split", type=float, default=0.7)
    args = ap.parse_args(argv)
    return {"cycle": cmd_cycle, "dashboard": cmd_dashboard, "validate": cmd_validate}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
