"""Koszty CFD na jednostkę pozycji: prowizja, finansowanie za noc, poślizg; szacunek czasu utrzymania."""
import statistics

import pandas as pd

from config import Costs

ROLLOVER_TZ = "America/New_York"
ROLLOVER_HOUR = 17


def financing_days(start, end, triple_weekday: int = 2) -> int:
    """Dni finansowania naliczone w (start, end]: rollover o 17:00 w Nowym Jorku, od poniedziałku do piątku.

    Rollover w dniu `triple_weekday` liczy się potrójnie (pokrywa weekend).
    """
    if end <= start:
        return 0
    s, e = start.tz_convert(ROLLOVER_TZ), end.tz_convert(ROLLOVER_TZ)
    days = 0
    for d in pd.date_range(s.normalize().tz_localize(None), e.normalize().tz_localize(None), freq="D"):
        if d.weekday() >= 5:
            continue
        roll = (d + pd.Timedelta(hours=ROLLOVER_HOUR)).tz_localize(ROLLOVER_TZ)
        if s < roll <= e:
            days += 3 if d.weekday() == triple_weekday else 1
    return days


def per_unit_costs(c: Costs, side: int, price: float, atr: float, start, end) -> dict:
    """Koszty jednej jednostki w walucie kwotowania (dodatnie = koszt, ujemne = przychód).

    Składnik jest None, gdy brakuje danych; jego nazwa trafia wtedy do `missing`.
    Spreadu tu nie ma: jest już w cenie wejścia (ask/bid) i w cenie wyjścia.
    """
    missing = []
    if c.commission_per_unit is None and c.commission_rate is None:
        commission = None
        missing.append("prowizja")
    else:
        commission = 2 * ((c.commission_per_unit or 0.0) + (c.commission_rate or 0.0) * price)

    days = financing_days(start, end, c.triple_financing_weekday)
    swap = c.swap_long_per_unit if side == 1 else c.swap_short_per_unit
    rate = c.financing_long_rate if side == 1 else c.financing_short_rate
    if days == 0:
        financing = 0.0
    elif swap is not None:
        financing = -swap * days
    elif rate is not None:
        financing = -price * rate / 365 * days
    else:
        financing = None
        missing.append("finansowanie overnight")

    slippage = None if c.slippage_atr is None else c.slippage_atr * atr
    if slippage is None:
        missing.append("poślizg na SL")
    return {"commission": commission, "financing": financing, "financing_days": days,
            "slippage": slippage, "missing": missing}


def holding_estimate(resolved: list, expire_hours: int = 48, min_n: int = 10) -> dict:
    """Przewidywany czas utrzymania: mediana z rozliczonych rad albo górna granica (wygaśnięcie)."""
    hours = [(pd.Timestamp(r["resolved_time"]) - pd.Timestamp(r["time"])).total_seconds() / 3600
             for r in resolved if r.get("resolved_time")]
    if len(hours) >= min_n:
        return {"hours": round(statistics.median(hours), 1), "n": len(hours), "max_hours": expire_hours,
                "basis": f"mediana z {len(hours)} rozliczonych rad"}
    return {"hours": float(expire_hours), "n": len(hours), "max_hours": expire_hours,
            "basis": f"za mało rozliczonych rad ({len(hours)} < {min_n}), przyjęto górną granicę {expire_hours} h"}
