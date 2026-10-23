"""Prosty backtest: jedna pozycja naraz, wejście na open następnej świecy po ASK/BID."""
import numpy as np
import pandas as pd

from config import Costs
from costs import per_unit_costs
from resolve import stop_fill
from strategy import Params


def run(df: pd.DataFrame, p: Params = Params(), equity0: float = 10_000.0, costs: Costs | None = None,
        expire_hours: float | None = 48):
    """df: wynik strategy.add_signals. Zwraca (tabela transakcji, słownik statystyk).

    Spread jest zawsze w cenach (wejście po ASK/BID, wyjście po drugiej stronie). SL przy luce
    wykonuje się po otwarciu świecy. Prowizja, finansowanie i poślizg tylko z `costs`
    (brak danych liczy się jako zero, patrz costs.cost_coverage). Pozycja wygasa po `expire_hours`
    tak jak rada na żywo; None wyłącza wygaśnięcie.
    """
    a = {c: df[c].to_numpy() for c in df.columns if c != "time"}
    ns = pd.DatetimeIndex(df["time"]).as_unit("ns").asi8
    expire_ns = None if expire_hours is None else int(expire_hours * 3600e9)
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
        slippage = (costs.slippage_atr or 0.0) * a["atr"][i] if costs else 0.0
        units = equity * p.risk_per_trade / dist_sl

        exit_px, reason, k = None, None, j
        for k in range(j, n):
            if sig == 1:   # long wychodzi po BID
                fill = stop_fill(1, a["bid_o"][k], a["bid_l"][k], sl, slippage)
                hit_tp = a["bid_h"][k] >= tp
            else:          # short wychodzi po ASK
                fill = stop_fill(-1, a["ask_o"][k], a["ask_h"][k], sl, slippage)
                hit_tp = a["ask_l"][k] <= tp
            if fill is not None:  # gdy obie w jednej świecy: konserwatywnie SL
                exit_px, reason = fill, "SL"
                break
            if hit_tp:
                exit_px, reason = tp, "TP"
                break
            if expire_ns is not None and ns[k] - ns[j] >= expire_ns:
                exit_px, reason = (a["bid_c"][k] if sig == 1 else a["ask_c"][k]), "EXPIRED"
                break
        if exit_px is None:  # koniec danych: zamknij po rynku
            k = n - 1
            exit_px = a["bid_c"][k] if sig == 1 else a["ask_c"][k]
            reason = "END"

        unit_cost = 0.0
        if costs is not None:
            pc = per_unit_costs(costs, sig, entry, a["atr"][i], df["time"].iloc[j], df["time"].iloc[k])
            unit_cost = (pc["commission"] or 0.0) + (pc["financing"] or 0.0)
        pnl = units * (sig * (exit_px - entry) - unit_cost)
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
