"""Rozstrzyganie otwartych werdyktów po fakcie: TP, SL albo wygaśnięcie po 48 h."""
import pandas as pd

from config import Costs
from costs import per_unit_costs


def stop_fill(side: int, open_px: float, extreme: float, sl: float, slippage: float = 0.0):
    """Cena wykonania SL w świecy albo None, gdy SL nie został dotknięty.

    Stop nie gwarantuje ceny: gdy świeca otwiera się już za SL (luka), wykonanie jest po otwarciu.
    `open_px` i `extreme` to BID open/low dla pozycji długiej albo ASK open/high dla krótkiej.
    """
    if side == 1:
        if open_px <= sl:
            return open_px - slippage
        return sl - slippage if extreme <= sl else None
    if open_px >= sl:
        return open_px + slippage
    return sl + slippage if extreme >= sl else None


def cost_in_r(costs: Costs | None, side: int, entry: float, atr: float, risk: float, start, end):
    """Prowizja i finansowanie w jednostkach R. None, gdy brakuje któregoś z tych kosztów."""
    if costs is None:
        return None
    pc = per_unit_costs(costs, side, entry, atr, start, end)
    if pc["commission"] is None or pc["financing"] is None:
        return None
    return (pc["commission"] + pc["financing"]) / risk


def resolve(v: dict, candles: pd.DataFrame, expire_hours: int = 48, costs: Costs | None = None):
    """Zwraca (status, outcome_r, iso_time, cost_r) albo None, gdy werdykt wciąż otwarty.

    outcome_r liczy się z ceny (spread jest w cenach bid/ask), z luką i poślizgiem na SL,
    więc strata może przekroczyć 1R. cost_r to prowizja i finansowanie w R albo None.
    """
    t0 = pd.Timestamp(v["time"])
    side = 1 if v["verdict"] == "KUP" else -1
    entry, sl, tp, atr = v["entry"], v["sl"], v["tp"], v.get("atr") or 0.0
    risk, reward = abs(entry - sl), abs(tp - entry)
    slippage = (costs.slippage_atr or 0.0) * atr if costs else 0.0
    deadline = t0 + pd.Timedelta(hours=expire_hours)

    def done(status, r, t):
        return status, r, t.isoformat(), cost_in_r(costs, side, entry, atr, risk, t0, t)

    for row in candles[candles["time"] > t0].itertuples():
        if side == 1:   # pozycja długa zamykana po BID
            fill = stop_fill(side, row.bid_o, row.bid_l, sl, slippage)
            hit_tp = row.bid_h >= tp
        else:           # pozycja krótka zamykana po ASK
            fill = stop_fill(side, row.ask_o, row.ask_h, sl, slippage)
            hit_tp = row.ask_l <= tp
        if fill is not None:  # gdy SL i TP w jednej świecy: konserwatywnie SL
            return done("SL", side * (fill - entry) / risk, row.time)
        if hit_tp:
            return done("TP", reward / risk, row.time)
        if row.time >= deadline:
            px = row.bid_c if side == 1 else row.ask_c
            return done("EXPIRED", side * (px - entry) / risk, row.time)
    return None
