"""Wielkość pozycji, strata i zysk w walucie rachunku, depozyt oraz ryzyko całego portfela."""
import json
import math
import os

import pandas as pd

from config import Account, Config, Instrument
from costs import per_unit_costs

GAP_NOTE = ("Zlecenie stop nie gwarantuje ceny wykonania: przy luce cenowej lub gwałtownym ruchu "
            "strata może być większa niż wyliczona.")


def fx_rate(cfg: Config, quote: str, live: dict | None = None) -> dict | None:
    """Kurs waluty kwotowania na walutę rachunku: {"rate", "source", "as_of"} albo None, gdy nieznany.

    Kolejność: ta sama waluta, kurs pobrany w tym cyklu (`live`), kurs z konfiguracji (także odwrotny).
    """
    acct = cfg.account.currency
    if not acct:
        return None
    if quote == acct:
        return {"rate": 1.0, "source": "ta sama waluta", "as_of": None}
    live = live or {}
    for pair, inverse in ((quote + acct, False), (acct + quote, True)):
        info = live.get(pair) or cfg.fx_rates.get(pair)
        if info and info.get("rate"):
            rate = 1 / info["rate"] if inverse else info["rate"]
            return {"rate": rate, "source": info.get("source") or "konfiguracja", "as_of": info.get("as_of"),
                    "pair": pair}
    return None


def liquidation_price(side: int, entry: float, units_acct: float, equity: float, margin_rate: float,
                      closeout: float, other_margin: float = 0.0) -> float:
    """Cena, przy której kapitał rachunku spada do `closeout` x depozyt (broker zamyka pozycje).

    units_acct: zmiana wyniku w walucie rachunku na 1 jednostkę ceny (jednostki x kurs);
    other_margin: depozyt innych otwartych pozycji (zakłada się, że ich wynik się nie zmienia).
    """
    if side == 1:   # equity + u(P - entry) = c (other + m u P)
        return (units_acct * entry - equity + closeout * other_margin) / (units_acct * (1 - closeout * margin_rate))
    return (equity + units_acct * entry - closeout * other_margin) / (units_acct * (1 + closeout * margin_rate))


def plan_trade(v: dict, instr: Instrument, account: Account, fx: dict | None, holding: dict, now,
               dividend: dict | None = None, other_margin: float = 0.0) -> dict:
    """Plan dla werdyktu handlowego: jednostki, strata przy SL i zysk przy TP po kosztach, depozyt.

    Wielkość pozycji jest taka, żeby strata przy SL razem ze znanymi kosztami i poślizgiem
    nie przekroczyła `risk_per_trade` kapitału. `missing` wymienia składniki bez danych.
    """
    side = 1 if v["verdict"] == "KUP" else -1
    entry, sl, tp = v["entry"], v["sl"], v["tp"]
    end = now + pd.Timedelta(hours=holding["hours"])
    pc = per_unit_costs(instr.costs, side, entry, v["atr"], now, end)
    commission, financing, slippage = (pc[k] or 0.0 for k in ("commission", "financing", "slippage"))

    risk_pu = abs(entry - sl)
    loss_pu = risk_pu + slippage + commission + max(financing, 0.0)
    gain_pu = abs(tp - entry) - commission - financing
    missing = list(pc["missing"])
    div_adj = None
    if dividend is not None:  # dzień ustalenia prawa do dywidendy w trakcie utrzymania
        if dividend.get("amount") is None or instr.costs.dividend_share is None:
            missing.append("korekta dywidendowa")
        else:
            div_adj = side * dividend["amount"] * instr.costs.dividend_share  # long dostaje, short płaci
            gain_pu += div_adj
            loss_pu += max(-div_adj, 0.0)
    if instr.costs.margin_rate is None:
        missing.append("depozyt (stopa depozytu)")
    if fx is None:
        missing.append(f"kurs {instr.quote}/{account.currency or '?'}")
    if account.capital is None:
        missing.append("kapitał rachunku")

    plan = {"side": "LONG" if side == 1 else "SHORT", "entry": entry, "sl": sl, "tp": tp,
            "risk_per_unit": risk_pu, "loss_per_unit": loss_pu, "gain_per_unit": gain_pu,
            "costs_per_unit": {**pc, "dividend": div_adj}, "quote": instr.quote, "currency": account.currency,
            "fx": fx, "risk_per_trade": account.risk_per_trade, "budget": None, "units": None, "loss": None,
            "gain": None, "notional": None, "margin": None, "missing": missing, "exact": not missing,
            "holding": holding, "note": GAP_NOTE}
    if fx is None or account.capital is None or loss_pu <= 0:
        return plan
    rate, step = fx["rate"], instr.costs.units_step
    budget = account.capital * account.risk_per_trade
    units = math.floor(budget / (loss_pu * rate) / step + 1e-9) * step
    plan.update(budget=budget, units=units, loss=units * loss_pu * rate, gain=units * gain_pu * rate,
                notional=units * entry * rate)
    m = instr.costs.margin_rate
    if m is not None and units > 0:
        plan["margin"] = units * entry * m * rate
        liq = liquidation_price(side, entry, units * rate, account.capital, m, account.margin_closeout, other_margin)
        plan.update(leverage=plan["notional"] / account.capital, max_leverage=1 / m, other_margin=other_margin,
                    free_margin=account.capital - other_margin - plan["margin"], liquidation_price=liq,
                    liquidation_move=(liq - entry) / entry, sl_beyond_liquidation=side * (sl - liq) <= 0)
    return plan


def load_positions(path: str | None) -> dict | None:
    """Plik otwartych pozycji: {"as_of", "source", "positions": [...]}. None, gdy pliku nie ma."""
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("positions", [])
    return data


def _side(p: dict) -> int:
    return 1 if str(p["side"]).upper() in ("LONG", "KUP", "BUY") else -1


def position_risk(p: dict, cfg: Config, fx_live: dict | None = None) -> float | None:
    """Strata otwartej pozycji przy jej SL w walucie rachunku. None, gdy brak SL albo kursu."""
    if p.get("sl") is None:
        return None
    fx = fx_rate(cfg, cfg.instrument(p["instrument"]).quote, fx_live)
    if fx is None:
        return None
    return float(p["units"]) * max(0.0, _side(p) * (p["entry"] - p["sl"])) * fx["rate"]


def positions_margin(cfg: Config, positions: dict | None, fx_live: dict | None = None) -> tuple[float, list]:
    """Depozyt zajęty przez otwarte pozycje w walucie rachunku i lista pozycji, dla których jest nieznany."""
    total, unknown = 0.0, []
    for p in (positions or {}).get("positions", []):
        instr = cfg.instrument(p["instrument"])
        fx = fx_rate(cfg, instr.quote, fx_live)
        if instr.costs.margin_rate is None or fx is None:
            unknown.append(p["instrument"])
            continue
        total += float(p["units"]) * p["entry"] * instr.costs.margin_rate * fx["rate"]
    return total, unknown


def portfolio_check(new_loss: float | None, instrument: str, cfg: Config, positions: dict | None,
                    fx_live: dict | None = None) -> dict:
    """Łączne ryzyko otwartych pozycji i ryzyko w grupie instrumentu, razem z nową pozycją.

    `ok` jest None, gdy limitów nie da się sprawdzić (brak pliku pozycji, kapitału albo ryzyka nowej pozycji).
    """
    acc = cfg.account
    group = cfg.instrument(instrument).group or instrument
    out = {"available": positions is not None, "as_of": (positions or {}).get("as_of"),
           "source": (positions or {}).get("source"), "count": 0, "total": 0.0, "group": group,
           "group_total": 0.0, "unknown": [], "total_limit": None, "group_limit": None, "ok": None,
           "exceeded": False, "reasons": []}
    if positions is None:
        out["reasons"].append("Brak pliku otwartych pozycji: łączne ryzyko portfela nieznane.")
        return out
    for p in positions["positions"]:
        out["count"] += 1
        r = position_risk(p, cfg, fx_live)
        label = f"{p['instrument']} {p['side']} {p['units']}"
        if r is None:
            out["unknown"].append(label)
            continue
        out["total"] += r
        if (p.get("group") or cfg.instrument(p["instrument"]).group or p["instrument"]) == group:
            out["group_total"] += r
    if out["unknown"]:
        out["reasons"].append("Ryzyko nieznane (brak SL albo kursu waluty): " + ", ".join(out["unknown"]) + ".")
    if acc.capital is None or new_loss is None:
        return out
    out["total_limit"], out["group_limit"] = acc.capital * acc.max_total_risk, acc.capital * acc.max_group_risk
    over_total = out["total"] + new_loss > out["total_limit"]
    over_group = out["group_total"] + new_loss > out["group_limit"]
    if over_total:
        out["reasons"].append(f"Łączne ryzyko z nową pozycją {out['total'] + new_loss:.2f} przekracza limit "
                              f"{out['total_limit']:.2f} ({acc.max_total_risk:.1%} kapitału).")
    if over_group:
        out["reasons"].append(f"Ryzyko w grupie „{group}” z nową pozycją {out['group_total'] + new_loss:.2f} "
                              f"przekracza limit {out['group_limit']:.2f} ({acc.max_group_risk:.1%} kapitału).")
    out["exceeded"] = over_total or over_group
    out["ok"] = not out["exceeded"] and not out["unknown"]
    return out
