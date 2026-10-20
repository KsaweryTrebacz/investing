"""Prosty backtest: jedna pozycja naraz, wejście na open następnej świecy po ASK/BID."""
import numpy as np
import pandas as pd

from strategy import Params


def run(df: pd.DataFrame, p: Params = Params(), equity0: float = 10_000.0):
    """df: wynik strategy.add_signals. Zwraca (tabela transakcji, słownik statystyk)."""
    a = {c: df[c].to_numpy() for c in df.columns if c != "time"}
    n, equity, i = len(df), equity0, 0
    trades, curve = [], [equity0]

    while i < n - 1:
        sig = a["signal"][i]
        if sig == 0 or not a["atr"][i] > 0:
            i += 1
            continue
        j = i + 1  # wejście na otwarciu następnej świecy
        spread = a["ask_o"][j] - a["bid_o"][j]
        if spread > p.max_spread_atr * a["atr"][i]:
            i += 1
            continue
        entry = a["ask_o"][j] if sig == 1 else a["bid_o"][j]
        dist_sl, dist_tp = p.sl_atr * a["atr"][i], p.tp_atr * a["atr"][i]
        sl, tp = entry - sig * dist_sl, entry + sig * dist_tp
        units = equity * p.risk_per_trade / dist_sl

        exit_px, reason, k = None, None, j
        for k in range(j, n):
            if sig == 1:   # long wychodzi po BID
                hit_sl, hit_tp = a["bid_l"][k] <= sl, a["bid_h"][k] >= tp
            else:          # short wychodzi po ASK
                hit_sl, hit_tp = a["ask_h"][k] >= sl, a["ask_l"][k] <= tp
            if hit_sl:     # gdy obie w jednej świecy: konserwatywnie SL
                exit_px, reason = sl, "SL"
                break
            if hit_tp:
                exit_px, reason = tp, "TP"
                break
        if exit_px is None:  # koniec danych: zamknij po rynku
            k = n - 1
            exit_px = a["bid_c"][k] if sig == 1 else a["ask_c"][k]
            reason = "END"

        pnl = units * sig * (exit_px - entry)
        equity += pnl
        curve.append(equity)
        trades.append({
            "entry_time": df["time"].iloc[j], "exit_time": df["time"].iloc[k],
            "side": "LONG" if sig == 1 else "SHORT", "entry": entry, "exit": exit_px,
            "reason": reason, "R": pnl / (units * dist_sl), "pnl": pnl, "equity": equity,
        })
        i = k + 1

    t = pd.DataFrame(trades)
    curve = np.array(curve)
    dd = (curve / np.maximum.accumulate(curve) - 1).min()
    if t.empty:
        return t, {"trades": 0}
    gp, gl = t.loc[t.pnl > 0, "pnl"].sum(), -t.loc[t.pnl < 0, "pnl"].sum()
    return t, {
        "trades": int(len(t)),
        "win_rate_%": round(100 * float((t.pnl > 0).mean()), 1),
        "avg_R": round(float(t.R.mean()), 3),
        "profit_factor": round(float(gp / gl), 2) if gl > 0 else float("inf"),
        "return_%": round(100 * float(equity / equity0 - 1), 2),
        "max_drawdown_%": round(100 * float(dd), 2),
    }
