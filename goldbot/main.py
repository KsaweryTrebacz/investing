"""Użycie:
  python main.py backtest [--demo] [--bars 5000]
  python main.py signal   [--demo] [--execute]     # --execute: zlecenie na koncie PRACTICE
"""
import argparse

import pandas as pd

import backtest
from oanda import Oanda, demo_candles
from strategy import Params, add_signals

INSTR = "XAU_USD"


def load(args):
    return (demo_candles(args.bars), None) if args.demo else (lambda o: (o.candles(INSTR, "M15", args.bars), o))(Oanda())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["backtest", "signal"])
    ap.add_argument("--demo", action="store_true", help="dane syntetyczne, bez OANDA")
    ap.add_argument("--bars", type=int, default=5000)
    ap.add_argument("--execute", action="store_true", help="wyślij zlecenie na PRACTICE")
    args = ap.parse_args()
    p = Params()
    df, api = load(args)
    df = add_signals(df, p)
    pd.set_option("display.width", 200)

    if args.cmd == "backtest":
        trades, stats = backtest.run(df, p)
        print(f"Świece: {len(df)}  ({df.time.iloc[0]} -> {df.time.iloc[-1]})")
        print(trades.tail(10).to_string(index=False) if len(trades) else "Brak transakcji.")
        print(stats)
        if args.demo:
            print("UWAGA: dane syntetyczne, wynik nie mówi nic o strategii.")
        return

    last = df.iloc[-1]  # ostatnia ZAMKNIĘTA świeca
    print(f"{last.time}  close={last.mid_c:.2f}  EMA200={last.ema:.2f}  RSI={last.rsi:.1f}  "
          f"MACDh={last.hist:.3f}  ATR={last.atr:.2f}  signal={int(last.signal)}")
    if last.signal == 0:
        print("Brak sygnału.")
        return
    side = int(last.signal)
    spread = api.spread(INSTR) if api else last.ask_c - last.bid_c
    if spread > p.max_spread_atr * last.atr:
        print(f"Sygnał odrzucony: spread {spread:.2f} > {p.max_spread_atr:.0%} ATR.")
        return
    entry = last.ask_c if side == 1 else last.bid_c
    sl, tp = entry - side * p.sl_atr * last.atr, entry + side * p.tp_atr * last.atr
    print(f"{'LONG' if side == 1 else 'SHORT'}  entry~{entry:.2f}  SL={sl:.2f}  TP={tp:.2f}  spread={spread:.2f}")
    if args.execute and api:
        # Wielkość pozycji: wymaga salda; tu stała 1 oz jako bezpieczny start (do zmiany).
        print(api.market_order(INSTR, side * 1, sl, tp))


if __name__ == "__main__":
    main()
