"""Dane makro z FRED: realne rentowności USA i szeroki indeks dolara."""
import pandas as pd
import requests

URL = "https://api.stlouisfed.org/fred/series/observations"
YIELD_SERIES = "DFII10"    # 10-letnie realne rentowności (TIPS)
USD_SERIES = "DTWEXBGS"    # szeroki nominalny indeks dolara, dzienny


def parse_observations(payload: dict) -> pd.Series:
    """Odpowiedź FRED -> Series z naiwnym indeksem dat. Brak wartości (".") jest pomijany."""
    obs = [(o["date"], float(o["value"])) for o in payload.get("observations", []) if o["value"] != "."]
    return pd.Series([v for _, v in obs], index=pd.DatetimeIndex([d for d, _ in obs]), dtype=float)


def fetch_series(series_id: str, api_key: str, start: str = "2015-01-01") -> pd.Series:
    r = requests.get(URL, params={"series_id": series_id, "api_key": api_key, "file_type": "json",
                                  "observation_start": start}, timeout=30)
    r.raise_for_status()
    return parse_observations(r.json())
