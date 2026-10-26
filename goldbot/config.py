"""Konfiguracja: rachunek, kursy walut, koszty brokera i instrumenty (plik JSON, bez sekretów).

Wartość None oznacza brak danych. Raport wypisuje każdy brak, a wynik policzony bez niego
jest oznaczony jako orientacyjny. Klucze zaczynające się od "_" są komentarzami i są pomijane.
"""
import json
import os
from dataclasses import dataclass, field, fields

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INSTRUMENT = "XAU_USD"


@dataclass
class Account:
    currency: str | None = None    # waluta rachunku, np. "PLN"
    capital: float | None = None   # wartość rachunku w walucie rachunku
    risk_per_trade: float = 0.005  # 0,5% kapitału na transakcję
    max_total_risk: float = 0.02   # łączne ryzyko otwartych pozycji (założenie)
    max_group_risk: float = 0.01   # ryzyko w jednej grupie lub sektorze (założenie)
    margin_closeout: float = 0.5   # broker zamyka pozycje, gdy kapitał < 50% depozytu (zasada ESMA)


@dataclass
class Costs:
    """Koszty brokera dla instrumentu, w walucie kwotowania. Stopy jako ułamki (0.05 = 5%)."""
    source: str | None = None                 # skąd dane, np. "tabela opłat brokera"
    as_of: str | None = None                  # na kiedy dane są aktualne
    margin_rate: float | None = None          # depozyt jako ułamek wartości nominalnej
    commission_per_unit: float | None = None  # za stronę: otwarcie i zamknięcie liczone osobno
    commission_rate: float | None = None      # ułamek wartości nominalnej, za stronę
    financing_long_rate: float | None = None  # roczna stopa jak w OANDA: ujemna = płacisz
    financing_short_rate: float | None = None
    swap_long_per_unit: float | None = None   # zamiast stopy: kwota za dzień za jednostkę, ujemna = płacisz
    swap_short_per_unit: float | None = None
    triple_financing_weekday: int = 2         # dzień potrójnego naliczenia, 0 = poniedziałek (założenie)
    slippage_atr: float | None = None         # zakładany poślizg na SL jako ułamek ATR
    units_step: float = 1.0                   # najmniejszy krok wielkości pozycji
    dividend_share: float | None = None       # część dywidendy księgowana przez brokera (CFD na akcje)


@dataclass
class Instrument:
    name: str = DEFAULT_INSTRUMENT
    group: str | None = None           # grupa lub sektor do limitu ekspozycji
    quote_currency: str | None = None  # domyślnie z nazwy: XAU_USD -> USD
    macro: bool = True                 # reżim z dolarem i rentownościami (ma sens dla złota)
    source: str = "oanda"              # "oanda" albo "csv" (eksport z TradingView)
    csv: dict = field(default_factory=dict)   # {"m15": ścieżka, "d1": ścieżka, "spread": typowy spread}
    symbol: str | None = None          # symbol spółki w Alpha Vantage (wyniki, dywidendy)
    news: dict = field(default_factory=dict)  # parametry NEWS_SENTIMENT: {"tickers": ..., "topics": ...}
    strategy: dict = field(default_factory=dict)  # nadpisania strategy.Params, np. {"sl_atr": 2.0}
    strategy_validated: bool = False   # True dopiero po dodatnim wyniku poza próbą (validate na danych brokera)
    costs: Costs = field(default_factory=Costs)

    @property
    def quote(self) -> str:
        return self.quote_currency or self.name.rsplit("_", 1)[-1]


def _default_instruments():
    return {DEFAULT_INSTRUMENT: Instrument(group="metale szlachetne")}


@dataclass
class Config:
    account: Account = field(default_factory=Account)
    instruments: dict = field(default_factory=_default_instruments)
    fx_rates: dict = field(default_factory=dict)  # {"USDPLN": {"rate": ..., "as_of": ..., "source": ...}}
    positions_file: str | None = "positions.json"
    events: dict = field(default_factory=dict)    # {"file": ..., "fred_releases": [...], "guard_hours": 2}
    path: str | None = None                       # skąd wczytano; None = brak pliku, wartości domyślne

    def resolve_path(self, p: str | None) -> str | None:
        """Ścieżka względna liczona od katalogu pliku konfiguracji (albo katalogu programu)."""
        if not p:
            return None
        base = os.path.dirname(self.path) if self.path else HERE
        return p if os.path.isabs(p) else os.path.join(base, p)

    def instrument(self, name: str) -> Instrument:
        return self.instruments.get(name) or Instrument(name=name, macro=False)


def _build(cls, data: dict):
    data = {k: v for k, v in data.items() if not k.startswith("_")}
    unknown = set(data) - {f.name for f in fields(cls)}
    if unknown:
        raise ValueError(f"Konfiguracja, sekcja {cls.__name__}: nieznane pola {sorted(unknown)}.")
    return cls(**data)


def load_config(path: str | None = None) -> Config:
    path = path or os.environ.get("GOLDBOT_CONFIG") or os.path.join(HERE, "config.json")
    if not os.path.exists(path):
        return Config()
    with open(path, encoding="utf-8") as f:
        raw = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    instruments = {}
    for name, spec in raw.pop("instruments", {}).items():
        if name.startswith("_"):
            continue
        spec = dict(spec)
        costs = _build(Costs, spec.pop("costs", {}))
        instruments[name] = _build(Instrument, {**spec, "name": name, "costs": costs})
    cfg = _build(Config, {**raw, "account": _build(Account, raw.get("account", {})), "path": path})
    if instruments:
        cfg.instruments = instruments
    return cfg
