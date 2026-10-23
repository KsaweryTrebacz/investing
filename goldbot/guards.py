"""Zabezpieczenia: jakość danych, nieaktualne dane, blokady rad handlowych."""
import pandas as pd

from advisor import TRADE

PRICE_COLS = [f"{s}_{k}" for s in ("bid", "ask") for k in "ohlc"]
DAILY_LOSS_LIMIT_R = -2.0


class DataError(RuntimeError):
    pass


def validate_candles(df: pd.DataFrame, name: str, min_bars: int) -> None:
    """Odrzuca dane, na których nie wolno liczyć sygnału."""
    if len(df) < min_bars:
        raise DataError(f"{name}: za mało świec ({len(df)} < {min_bars}).")
    if df[PRICE_COLS].isna().any().any():
        raise DataError(f"{name}: brak cen w części świec.")
    if (df[PRICE_COLS] <= 0).any().any():
        raise DataError(f"{name}: niedodatnie ceny.")
    if (df["ask_c"] < df["bid_c"]).any() or (df["ask_o"] < df["bid_o"]).any():
        raise DataError(f"{name}: ask < bid.")
    if (df["bid_h"] < df["bid_l"]).any() or (df["ask_h"] < df["ask_l"]).any():
        raise DataError(f"{name}: high < low.")
    if not df["time"].is_monotonic_increasing or df["time"].duplicated().any():
        raise DataError(f"{name}: czas świec nie rośnie albo się powtarza.")


def is_stale(last_open, now, tf=pd.Timedelta(minutes=15), max_intervals: int = 2) -> bool:
    """Czy ostatnia zamknięta świeca jest starsza niż `max_intervals` interwałów."""
    return now - (last_open + tf) > max_intervals * tf


def macro_is_stale(s: pd.Series, now, max_days: int = 10) -> bool:
    """Czy ostatnia obserwacja makro jest starsza niż `max_days` dni."""
    last = pd.Timestamp(s.index.max()).tz_localize("UTC")
    return now - last > pd.Timedelta(days=max_days)


def apply_guards(v: dict, store, now, last_open, tf=pd.Timedelta(minutes=15)) -> dict:
    """Zamienia radę handlową na CZEKAJ, gdy dane są nieaktualne, poprzednia rada jest otwarta
    albo dzisiejsze rozliczone rady przekroczyły dzienny limit strat. Powód trafia do uzasadnienia."""
    reasons, codes = [], []
    if is_stale(last_open, now, tf):
        codes.append("stale")
        reasons.append(f"Dane nieaktualne: ostatnia zamknięta świeca z {last_open:%Y-%m-%d %H:%M} UTC.")
    if v["verdict"] in TRADE:
        for o in store.open_verdicts()[:1]:
            codes.append("open_advice")
            reasons.append(f"Poprzednia rada {o['verdict']} z {o['time'][:16].replace('T', ' ')} jest jeszcze otwarta.")
        day_start = now.normalize().isoformat()
        if store.realized_r_since(day_start) <= DAILY_LOSS_LIMIT_R:
            codes.append("daily_loss")
            reasons.append(f"Dzienny limit strat rad ({DAILY_LOSS_LIMIT_R:g}R) osiągnięty, "
                           "nowe rady handlowe wstrzymane do końca dnia UTC.")
    if not reasons:
        return v
    out = dict(v, blocked=v.get("blocked", []) + codes)
    if v["verdict"] in TRADE:
        out.update(verdict="CZEKAJ", entry=None, sl=None, tp=None, status="NONE")
        reasons.insert(0, f"Sygnał {v['verdict']} wstrzymany przez zabezpieczenia.")
    out["reasoning"] = f"{v['reasoning']} {' '.join(reasons)}"
    return out
