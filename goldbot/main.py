"""Doradca XAU/USD.

  python main.py cycle     [--demo]                 # jeden cykl: werdykt, zapis, powiadomienie
  python main.py dashboard [--demo] [--port 8787]   # lokalna strona z werdyktem
  python main.py validate  [--demo] [--years 3]     # walk-forward: czy reguły mają przewagę poza próbą
  python main.py train     [--source auto|free|oanda] [--years 15] [--offline]  # model dzienny: walidacja + uczenie
  python main.py daily     [--source auto|free|oanda] [--offline]               # werdykt dzienny
"""
import argparse
import os
import sys

import pandas as pd

from guards import DataError, validate_candles
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
    return m15, d1, *get_macro()


def get_macro():
    """(usd, yld) z FRED albo (None, None). Nieaktualne dane makro są traktowane jak brak."""
    from guards import macro_is_stale

    key = os.environ.get("FRED_API_KEY")
    if not key:
        print("Ostrzeżenie: brak FRED_API_KEY, reżim dzienny będzie NEUTRALNY (brak danych makro).")
        return None, None
    try:
        usd, yld = fetch_series(USD_SERIES, key), fetch_series(YIELD_SERIES, key)
    except Exception as e:
        print(f"Ostrzeżenie: nie pobrano danych makro ({e}), reżim będzie NEUTRALNY.")
        return None, None
    now = pd.Timestamp.now(tz="UTC")
    for name, s in (("dolar", usd), ("rentowności", yld)):
        if s.empty or macro_is_stale(s, now):
            print(f"Ostrzeżenie: dane makro ({name}) są nieaktualne, reżim będzie NEUTRALNY.")
            return None, None
    return usd, yld


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
    now = None
    if args.demo:
        send = None  # dane syntetyczne nigdy nie trafiają na Telegram
        now = m15["time"].iloc[-1] + pd.Timedelta(minutes=16)  # demo ma własny zegar
    try:
        res = run_cycle(m15, d1, usd, yld, Store(db_path(args.demo)), send, now=now)
    except DataError as e:
        print(f"Dane odrzucone, werdykt nie został wydany: {e}")
        return 1
    v = res["verdict"]
    print(f"{v['time']}  {v['verdict']}  reżim={v['regime']}  zapisano={res['stored']}  "
          f"rozstrzygnięto={res['resolved']}")
    print(v["reasoning"])
    if v["entry"]:
        print(f"Wejście ok. {v['entry']:.2f}  SL {v['sl']:.2f}  TP {v['tp']:.2f}")
    return 0


def _daily_data(args):
    from sources import make_source, pick_source

    name = pick_source(args.source)
    print(f"Źródło danych: {name}" + (" (offline, z pamięci podręcznej)" if args.offline else ""))
    return make_source(args.source, args.offline).fetch_daily(args.years)


def cmd_train(args):
    import model as M
    from features import build_features

    try:
        data = _daily_data(args)
        validate_candles(data.gold, "D1", 1500)
    except (DataError, Exception) as e:
        print(f"Dane odrzucone, model nie został nauczony: {e}")
        return 1
    for w in data.warnings:
        print(f"Uwaga: {w}")
    feat = build_features(data.gold, data.usd, data.yld)
    print(f"Sesje: {len(feat)} ({feat.index[0].date()} -> {feat.index[-1].date()}). Liczę walk-forward...")
    report, _ = M.evaluate(feat)
    report["source"] = data.source
    pd.set_option("display.width", 200)
    mode_pl = {"long": "w złocie albo w gotówce", "ls": "długa/krótka"}[report["mode"]]
    trail = report.get("trail_atr")
    print("\nModel {} (tryb: {}, próg {:.2f}, stop kroczący: {}):".format(
        report["model_kind"], mode_pl, report["threshold"], f"{trail:g} ATR" if trail else "brak"))
    print(pd.DataFrame({"okres strojenia": report["in_sample"], "okres kontrolny": report["out_of_sample"]}).to_string())
    print("\nSame reguły reżimu (bez ML), do porównania:")
    print(pd.DataFrame({"okres strojenia": report["regime_baseline"]["in_sample"],
                        "okres kontrolny": report["regime_baseline"]["out_of_sample"]}).to_string())
    print("\nRok po roku:")
    print(pd.DataFrame(report["by_year"]).T.to_string())
    other = [m for m in report["modes"] if m != report["mode"]][0]
    print("\nDrugi tryb ({}), tylko informacyjnie: {}".format(other, report["modes"][other]["edge_text"]))
    print("\n" + report["edge_text"])
    m, imp = M.fit_final(feat)
    M.save_model(M.MODEL_PATH, m, report["threshold"], imp, report)
    M.save_report(report)
    top = sorted(imp.items(), key=lambda kv: -kv[1])[:5]
    print("Najważniejsze cechy: " + ", ".join(f"{k} ({v:.3f})" for k, v in top))
    print(f"Zapisano {M.MODEL_PATH} i {M.REPORT_PATH}.")
    return 0


def cmd_daily(args):
    import model as M
    from daily_cycle import run_daily_cycle
    from notify import telegram_sender
    from store import Store

    bundle, report = M.load_model(), M.load_report()
    if bundle is None or report is None:
        print("Brak modelu. Najpierw: python main.py train")
        return 1
    age = (pd.Timestamp.now(tz="UTC") - pd.Timestamp(report["trained_at"])).days
    if age > 100:
        print(f"Model ma {age} dni. Uruchom ponownie: python main.py train")
    try:
        data = _daily_data(args)
    except Exception as e:
        print(f"Błąd pobierania danych, werdykt nie został wydany: {e}")
        return 1
    send = telegram_sender()
    if send is None:
        print("Telegram nieskonfigurowany (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID), bez powiadomień.")
    try:
        res = run_daily_cycle(data, bundle, report, Store(db_path(False)), send)
    except DataError as e:
        print(f"Dane odrzucone, werdykt nie został wydany: {e}")
        return 1
    v = res["verdict"]
    print(f"{v['time'][:10]}  {v['verdict']}  p(wzrost)={100 * v['p_up']:.0f}%  reżim={v['regime']}  "
          f"zapisano={res['stored']}  rozstrzygnięto={res['resolved']}")
    print(v["reasoning"])
    if v["entry"]:
        print(f"Wejście ok. {v['entry']:.2f}  stop {v['sl']:.2f}  horyzont {v['horizon']} sesji")
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
    try:
        validate_candles(m15, "M15", 1000)
        validate_candles(d1, "D1", 200)
    except DataError as e:
        print(f"Dane odrzucone: {e}")
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
    for name in ("train", "daily"):
        sp = sub.add_parser(name)
        sp.add_argument("--source", default="auto", choices=["auto", "free", "oanda"])
        sp.add_argument("--years", type=int, default=15)
        sp.add_argument("--offline", action="store_true", help="użyj pamięci podręcznej, bez sieci")
    args = ap.parse_args()
    return {"cycle": cmd_cycle, "dashboard": cmd_dashboard, "validate": cmd_validate,
            "train": cmd_train, "daily": cmd_daily}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
