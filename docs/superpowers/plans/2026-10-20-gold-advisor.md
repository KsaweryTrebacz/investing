# Doradca XAU/USD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lokalny doradca, który co 15 minut wydaje werdykt KUP / SPRZEDAJ / CZEKAJ dla XAU/USD, pokazuje go na dashboardzie i powiadamia przez Telegram przy zmianie.

**Architecture:** Warstwa dzienna (trend złota, dolar, realne rentowności) daje reżim z histerezą. Strategia M15 z `goldbot` wydaje sygnał tylko zgodny z reżimem. Cykl zapisuje świece i werdykty w SQLite, rozstrzyga stare werdykty i wysyła powiadomienie. Dashboard to mały serwer stdlib czytający SQLite.

**Tech Stack:** Python 3.12, pandas, numpy, requests, sqlite3, http.server, pytest, Chart.js (CDN).

## Global Constraints

- Tylko środowisko OANDA Practice (`OANDA_ENV=practice`). Program nie składa zleceń.
- Sygnały liczone wyłącznie na zamkniętych świecach. Wejście w backtescie na otwarciu następnej świecy po ASK (LONG) lub BID (SHORT).
- Strategia M15: EMA 200, RSI 14 (próg 40 LONG, 60 SHORT, okno uzbrojenia 10 świec), MACD 12/26/9 histogram, SL 1,5 ATR, TP 3,0 ATR, ATR 14, filtr spreadu 25% ATR, ryzyko 1% na transakcję.
- Reżim: SPRZYJA_KUPNIE, NEUTRALNY, SPRZYJA_SPRZEDAZY. Składniki: trend (EMA 50 vs EMA 200), dolar (EMA 20 vs EMA 50, odwrócony), realne rentowności DFII10 (EMA 20 vs EMA 50, odwrócone). Zmiana reżimu po 2 kolejnych dniach. Brak danych makro daje NEUTRALNY.
- Wygaśnięcie nierozstrzygniętego werdyktu po 48 godzinach.
- Powiadomienia tylko przy zmianie. Napis "Sygnał analityczny, nie porada inwestycyjna." w każdym powiadomieniu i na dashboardzie.
- Sekrety tylko w zmiennych środowiskowych: `OANDA_TOKEN`, `FRED_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

**Komendy.** Python: `C:\Users\skywa\AppData\Local\Programs\Python\Python312\python.exe` (dalej `PY`). Git: `C:\Users\skywa\AppData\Local\GitHubDesktop\app-3.6.7\resources\app\git\cmd\git.exe` (dalej `GIT`). Wszystko uruchamiane z katalogu głównego repozytorium. Testy: `PY -m pytest goldbot/tests -q`.

**Odstępstwo od specyfikacji:** powiadomienie wychodzi, gdy werdykt jest handlowy (KUP/SPRZEDAJ) albo zmienia się reżim. Przejście z KUP na CZEKAJ jest zapisywane w bazie, ale nie powiadamia, bo dublowałoby każdy sygnał.

## File Structure

```
goldbot/
  conftest.py            # ścieżka importu dla pytest
  .gitignore
  requirements.txt, requirements-dev.txt
  indicators.py          # (istnieje) EMA, RSI, MACD, ATR
  strategy.py            # (istnieje) sygnały M15 + gate_by_regime
  backtest.py            # (istnieje) backtest; tu tylko rzutowanie na float
  regime.py              # reżim dzienny z histerezą
  pipeline.py            # prepare(): świece + makro -> ramka z sygnałami i reżimem
  advisor.py             # make_verdict(): werdykt i uzasadnienie
  resolve.py             # rozstrzyganie otwartych werdyktów
  store.py               # SQLite
  macro.py               # FRED
  notify.py              # Telegram, should_store/should_notify
  cycle.py               # run_cycle()
  dashboard.py + web/index.html
  validate.py            # walk-forward
  oanda.py               # (istnieje) klient, bez zleceń; dane demo
  main.py                # CLI: cycle, dashboard, validate
  install_task.ps1       # Harmonogram zadań
  README.md
  tests/test_*.py
```

---

### Task 1: Infrastruktura testów, wskaźniki, backtest

**Files:**
- Create: `goldbot/conftest.py`, `goldbot/.gitignore`, `goldbot/requirements-dev.txt`
- Create: `goldbot/tests/test_indicators.py`, `goldbot/tests/test_backtest.py`
- Modify: `goldbot/backtest.py` (rzutowanie wyników na float)

**Interfaces:**
- Consumes: istniejące `indicators.ema/rsi/macd_hist/atr`, `backtest.run(df, p, equity0) -> (DataFrame, dict)`.
- Produces: pytest działa z korzenia repo; `backtest.run` zwraca w słowniku zwykłe `float`/`int`.

- [ ] **Step 1: Pliki infrastruktury**

`goldbot/conftest.py`:
```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```
`goldbot/.gitignore`:
```
__pycache__/
.pytest_cache/
*.db
```
`goldbot/requirements-dev.txt`:
```
-r requirements.txt
pytest
```

- [ ] **Step 2: Testy wskaźników**

`goldbot/tests/test_indicators.py`:
```python
import numpy as np
import pandas as pd

from indicators import atr, ema, macd_hist, rsi


def test_ema_of_constant_is_constant():
    assert np.allclose(ema(pd.Series([5.0] * 50), 10), 5.0)


def test_rsi_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert rsi(up).iloc[-1] == 100
    assert rsi(up[::-1].reset_index(drop=True)).iloc[-1] < 1


def test_macd_hist_of_constant_is_zero():
    assert np.allclose(macd_hist(pd.Series([100.0] * 80)), 0.0)


def test_atr_of_constant_range():
    h, l, c = (pd.Series([v] * 30) for v in (102.0, 100.0, 101.0))
    assert np.allclose(atr(h, l, c, 14), 2.0)
```

- [ ] **Step 3: Testy backtestu**

`goldbot/tests/test_backtest.py`:
```python
import pandas as pd

import backtest
from strategy import Params


def bar(t, o, h, l, c, half=0.1, atr=1.0, signal=0):
    d = {"time": pd.Timestamp("2026-01-05", tz="UTC") + pd.Timedelta(minutes=15 * t),
         "atr": atr, "signal": signal}
    for k, v in zip("ohlc", (o, h, l, c)):
        d[f"bid_{k}"], d[f"ask_{k}"] = v - half, v + half
    return d


def test_long_take_profit_is_plus_2R():
    df = pd.DataFrame([bar(0, 100, 100.5, 99.5, 100, signal=1), bar(1, 100, 100.5, 99.5, 100),
                       bar(2, 100, 104, 100, 103), bar(3, 103, 103, 103, 103)])
    t, s = backtest.run(df, Params())
    assert s["trades"] == 1 and t.iloc[0].reason == "TP"
    assert abs(t.iloc[0].R - 2.0) < 1e-9


def test_long_stop_loss_is_minus_1R():
    df = pd.DataFrame([bar(0, 100, 100.5, 99.5, 100, signal=1), bar(1, 100, 100.5, 99.5, 100),
                       bar(2, 100, 100.2, 98, 98.5), bar(3, 98, 98, 98, 98)])
    t, s = backtest.run(df, Params())
    assert t.iloc[0].reason == "SL" and abs(t.iloc[0].R + 1.0) < 1e-9


def test_wide_spread_skips_entry():
    df = pd.DataFrame([bar(0, 100, 100.5, 99.5, 100, half=0.5, signal=1),
                       bar(1, 100, 100.5, 99.5, 100, half=0.5), bar(2, 100, 104, 100, 103, half=0.5)])
    assert backtest.run(df, Params())[1] == {"trades": 0}


def test_stats_are_plain_python_numbers():
    df = pd.DataFrame([bar(0, 100, 100.5, 99.5, 100, signal=1), bar(1, 100, 100.5, 99.5, 100),
                       bar(2, 100, 104, 100, 103), bar(3, 103, 103, 103, 103)])
    s = backtest.run(df, Params())[1]
    assert all(type(v) in (int, float) for v in s.values())
```

- [ ] **Step 4: Uruchom testy, backtest ma failować tylko na typach**

Run: `PY -m pip install pytest -q; PY -m pytest goldbot/tests -q`
Expected: test_stats_are_plain_python_numbers FAIL (np.float64), reszta PASS.

- [ ] **Step 5: Rzutowanie w backtest.py**

W `goldbot/backtest.py` zamień końcowy `return {...}` na:
```python
    return t, {
        "trades": int(len(t)),
        "win_rate_%": round(100 * float((t.pnl > 0).mean()), 1),
        "avg_R": round(float(t.R.mean()), 3),
        "profit_factor": round(float(gp / gl), 2) if gl > 0 else float("inf"),
        "return_%": round(100 * float(equity / equity0 - 1), 2),
        "max_drawdown_%": round(100 * float(dd), 2),
    }
```

- [ ] **Step 6: Testy przechodzą, commit**

Run: `PY -m pytest goldbot/tests -q` → Expected: 8 passed.
```
GIT add goldbot; GIT commit -m "Add goldbot core (indicators, strategy, backtest) with tests"
```

---

### Task 2: Reżim dzienny

**Files:**
- Create: `goldbot/regime.py`, `goldbot/tests/test_regime.py`

**Interfaces:**
- Produces: stałe `REGIME_BUY="SPRZYJA_KUPNIE"`, `REGIME_NEUTRAL="NEUTRALNY"`, `REGIME_SELL="SPRZYJA_SPRZEDAZY"`, słownik `REGIME_PL`; `trend_dir(s, fast, slow) -> Series float` (+1/-1/0, NaN w rozgrzewce); `apply_hysteresis(raw: Series, confirm=2) -> Series`; `build_regime(d1: DataFrame, usd: Series|None, yld: Series|None, enter=2, confirm=2) -> DataFrame[time, known_from, trend, dollar, yields, total, regime]`; `attach_regime(df15, reg) -> DataFrame` (dokłada `regime, trend, dollar, yields, total`).
- Consumes: `indicators.ema`; `d1` ma kolumny `time` (tz UTC), `bid_c`, `ask_c`; `usd`/`yld` to Series z naiwnym DatetimeIndex (data obserwacji).

- [ ] **Step 1: Testy**

`goldbot/tests/test_regime.py`:
```python
import numpy as np
import pandas as pd

from regime import (REGIME_BUY, REGIME_NEUTRAL, REGIME_SELL, apply_hysteresis,
                    attach_regime, build_regime, trend_dir)


def test_trend_dir_up_down_flat():
    up = pd.Series(np.arange(300, dtype=float))
    assert trend_dir(up, 50, 200).iloc[-1] == 1
    assert trend_dir(up[::-1].reset_index(drop=True), 50, 200).iloc[-1] == -1
    assert trend_dir(pd.Series([5.0] * 300), 50, 200).iloc[-1] == 0
    assert trend_dir(up, 50, 200).iloc[:200].isna().all()


def test_hysteresis_needs_two_consecutive_days():
    raw = pd.Series([REGIME_NEUTRAL, REGIME_BUY, REGIME_NEUTRAL, REGIME_BUY, REGIME_BUY, REGIME_BUY])
    out = apply_hysteresis(raw, confirm=2).tolist()
    assert out == [REGIME_NEUTRAL] * 4 + [REGIME_BUY] * 2


def _d1(n=400, start=1800.0, end=2200.0):
    px = np.linspace(start, end, n)
    return pd.DataFrame({"time": pd.date_range("2025-01-01", periods=n, tz="UTC"),
                         "bid_c": px, "ask_c": px})


def test_all_three_components_bullish_gives_buy():
    d1 = _d1()
    idx = pd.date_range("2025-01-01", periods=500)
    usd = pd.Series(np.linspace(120, 100, 500), index=idx)
    yld = pd.Series(np.linspace(2.5, 1.0, 500), index=idx)
    reg = build_regime(d1, usd, yld)
    assert reg.regime.iloc[-1] == REGIME_BUY
    assert reg.total.iloc[-1] == 3
    assert (reg.known_from == reg.time + pd.Timedelta(days=1)).all()


def test_falling_gold_and_bearish_macro_gives_sell():
    d1 = _d1(start=2200.0, end=1800.0)
    idx = pd.date_range("2025-01-01", periods=500)
    usd = pd.Series(np.linspace(100, 120, 500), index=idx)
    yld = pd.Series(np.linspace(1.0, 2.5, 500), index=idx)
    assert build_regime(d1, usd, yld).regime.iloc[-1] == REGIME_SELL


def test_missing_macro_is_always_neutral():
    reg = build_regime(_d1(), None, None)
    assert (reg.regime == REGIME_NEUTRAL).all()
    assert reg.dollar.isna().all()


def test_attach_regime_uses_only_known_days():
    reg = pd.DataFrame({
        "known_from": pd.to_datetime(["2026-01-06 00:00"], utc=True),
        "regime": [REGIME_BUY], "trend": [1.0], "dollar": [1.0], "yields": [1.0], "total": [3.0]})
    df15 = pd.DataFrame({"time": pd.to_datetime(["2026-01-05 23:45", "2026-01-06 00:00"], utc=True)})
    out = attach_regime(df15, reg)
    assert out.regime.tolist() == [REGIME_NEUTRAL, REGIME_BUY]
```

- [ ] **Step 2: Uruchom, ma failować** (`ModuleNotFoundError: regime`): `PY -m pytest goldbot/tests/test_regime.py -q`
- [ ] **Step 3: Zaimplementuj `goldbot/regime.py`** według Interfaces. Reguły: `trend_dir` = +1 gdy `ema(fast) > ema(slow)` i EMA fast rośnie, -1 symetrycznie, 0 w pozostałych; pierwsze `slow` wartości NaN. Trend złota `trend_dir(close, 50, 200)`, dolar `-trend_dir(usd, 20, 50)`, rentowności `-trend_dir(yld, 20, 50)`. Makro liczone na własnym szeregu, potem `reindex(method="ffill")` na datę `known_from` (czas świecy D1 + 1 dzień, UTC, bez strefy). `total` = suma trzech (NaN gdy którykolwiek brak), surowy reżim: `total >= enter` KUPNO, `<= -enter` SPRZEDAŻ, inaczej NEUTRALNY, `apply_hysteresis` z `confirm=2`. `attach_regime` robi `merge_asof` (backward) po `known_from` na `time`, rzutując obie kolumny na `datetime64[ns, UTC]`, braki: reżim NEUTRALNY.
- [ ] **Step 4: Testy przechodzą**, commit `Add daily regime engine`.

---

### Task 3: Bramka reżimu, pipeline, dane demo, usunięcie zleceń

**Files:**
- Modify: `goldbot/strategy.py` (dodaj `gate_by_regime`), `goldbot/oanda.py` (usuń `market_order`, `spread`, `OANDA_ACCOUNT_ID`; dodaj `demo_daily`, `demo_macro`)
- Create: `goldbot/pipeline.py`, `goldbot/tests/test_pipeline.py`

**Interfaces:**
- Produces: `gate_by_regime(df) -> df` (dodaje `signal_raw`, zeruje `signal` niezgodny z reżimem); `prepare(m15, d1, usd, yld, p=Params()) -> DataFrame` (`add_signals` + `attach_regime` + `gate_by_regime`); `demo_daily(m15) -> DataFrame D1`; `demo_macro(d1, seed=11) -> (usd, yld)`.

- [ ] **Step 1: Testy** w `goldbot/tests/test_pipeline.py`: (a) `gate_by_regime` zostawia LONG w KUPNIE i SHORT w SPRZEDAŻY, zeruje LONG w NEUTRALNYM i zachowuje go w `signal_raw`; (b) `prepare(demo_candles(30000), demo_daily(...), *demo_macro(...))` zwraca kolumny `signal`, `signal_raw`, `regime`, `atr` i `signal` tylko w {-1,0,1}, a bez makro (`None, None`) wszystkie `signal == 0`.
- [ ] **Step 2: Uruchom, ma failować.**
- [ ] **Step 3: Implementacja** wg Interfaces. `demo_daily` agreguje bid/ask: open=first, high=max, low=min, close=last po `resample("1D")`. `demo_macro` zwraca dwa błądzenia losowe z indeksem dat D1 (UTC bez strefy).
- [ ] **Step 4: Testy przechodzą**, commit `Add regime gate, pipeline, demo data; drop order placement`.

---

### Task 4: Magazyn SQLite

**Files:** Create `goldbot/store.py`, `goldbot/tests/test_store.py`

**Interfaces (klasa `Store(path=":memory:")`):**
- `upsert_candles(granularity: str, df)`, `load_candles(granularity, limit) -> DataFrame` (kolumny `time` tz UTC, `bid_*`, `ask_*`)
- `add_verdict(v: dict) -> int`, `last_verdict() -> dict|None`, `recent_verdicts(n) -> list[dict]`, `open_verdicts() -> list[dict]` (status `OPEN`), `close_verdict(id, status, outcome_r, resolved_time)`
- `set_current(v)`, `get_current() -> dict|None` (ostatni werdykt cyklu, także niezapisany)
- `stats() -> dict` (`trades`, `win_rate_%`, `avg_R`, `total_R`, `max_drawdown_R` z zamkniętych TP/SL/EXPIRED; `{"trades": 0}` gdy brak)

- [ ] **Step 1: Testy:** zapis i odczyt świec (kolejność rosnąca, `limit`, upsert nie dubluje); cykl życia werdyktu (add → open → close → nie jest już otwarty); `stats` na R = [+2, -1, -1, +2] daje win rate 50, total_R 2, max_drawdown_R -2; `set_current/get_current` round trip.
- [ ] **Step 2: Uruchom, ma failować.** **Step 3: Implementacja** (`sqlite3`, `time` jako ISO tekst, tabele `candles(granularity, time, bid_o..ask_c, PK(granularity,time))`, `verdicts(id, time UNIQUE, verdict, regime, entry, sl, tp, atr, reasoning, status, outcome_r, resolved_time)`, `state(key PK, value)`). **Step 4: Testy, commit** `Add SQLite store`.

---

### Task 5: Werdykt i rozstrzyganie

**Files:** Create `goldbot/advisor.py`, `goldbot/resolve.py`, `goldbot/tests/test_advisor.py`, `goldbot/tests/test_resolve.py`

**Interfaces:**
- `make_verdict(df, p=Params()) -> dict` z kluczami `time` (ISO), `verdict` (`KUP`/`SPRZEDAJ`/`CZEKAJ`), `regime`, `entry`, `sl`, `tp`, `atr`, `reasoning`, `status` (`OPEN` dla handlowych, `NONE` dla CZEKAJ). Używa ostatniego wiersza `df` z `prepare`. Handlowy: `entry` = `ask_c` (KUP) lub `bid_c` (SPRZEDAJ), `sl = entry ∓ 1.5*atr`, `tp = entry ± 3*atr`. Spread `ask_c - bid_c > 0.25*atr` zamienia sygnał w CZEKAJ z wzmianką o spreadzie. `signal_raw != 0` przy `signal == 0` daje zdanie z "zablokowany". Uzasadnienie zawsze zaczyna od reżimu i trzech składników ("brak danych" dla NaN).
- `resolve(v, candles, expire_hours=48) -> (status, outcome_r, iso_time) | None`. Świece o `time > v.time`; KUP: SL gdy `bid_l <= sl`, TP gdy `bid_h >= tp`; SPRZEDAJ: SL gdy `ask_h >= sl`, TP gdy `ask_l <= tp`; SL ma pierwszeństwo; TP daje `+|tp-entry|/|entry-sl|`, SL daje -1; po terminie `EXPIRED` z R z ceny zamknięcia.

- [ ] **Step 1: Testy** na ręcznie zbudowanych ramkach: KUP ma poprawne poziomy; CZEKAJ bez sygnału; odrzucenie przez spread; blokada przez reżim; `resolve` zwraca TP (+2), SL (-1), SL gdy obie w jednej świecy, EXPIRED po 48 h, `None` gdy jeszcze otwarty.
- [ ] **Step 2-4:** failuje, implementacja, przechodzi, commit `Add verdict builder and resolver`.

---

### Task 6: Makro (FRED) i powiadomienia

**Files:** Create `goldbot/macro.py`, `goldbot/notify.py`, `goldbot/tests/test_macro_notify.py`

**Interfaces:**
- `macro.USD_SERIES="DTWEXBGS"`, `macro.YIELD_SERIES="DFII10"`, `parse_observations(payload: dict) -> Series` (naiwny DatetimeIndex, pomija `"."`), `fetch_series(series_id, api_key, start="2015-01-01") -> Series`
- `notify.should_store(prev, new) -> bool` (prev None, albo inny czas i (werdykt handlowy lub zmiana pary werdykt+reżim)), `should_notify(prev, new) -> bool` (prev None, albo nowa świeca i (werdykt handlowy lub zmiana reżimu)), `format_message(v) -> str` (zawiera werdykt, reżim, poziomy dla handlowych, uzasadnienie i napis "Sygnał analityczny, nie porada inwestycyjna."), `telegram_sender() -> callable|None` (None gdy brak `TELEGRAM_BOT_TOKEN` lub `TELEGRAM_CHAT_ID`)

- [ ] **Step 1: Testy:** parsowanie ze `"."`; `should_store/should_notify` dla: brak prev, ten sam czas, KUP po CZEKAJ, CZEKAJ po KUP (zapis tak, powiadomienie nie), zmiana reżimu; `format_message` zawiera "KUP" i "SL"; `telegram_sender()` zwraca None po `monkeypatch.delenv`.
- [ ] **Step 2-4:** failuje, implementacja (`requests`), przechodzi, commit `Add FRED client and notifier`.

---

### Task 7: Cykl

**Files:** Create `goldbot/cycle.py`, `goldbot/tests/test_cycle.py`

**Interfaces:** `run_cycle(m15, d1, usd, yld, store, send=None, p=Params()) -> {"verdict": dict, "stored": bool, "resolved": int}`. Kolejność: zapis świec, `prepare`, `make_verdict`, rozstrzygnięcie otwartych werdyktów, `should_store` i zapis, `should_notify` i wysyłka, `set_current`.

- [ ] **Step 1: Test** na danych demo (`demo_candles(30000)`, `demo_daily`, `demo_macro`) i `Store()`: pierwszy cykl `stored=True` i dokładnie jedna wiadomość w liście `sent`; drugi cykl na tych samych danych `stored=False` i nadal jedna wiadomość; `store.get_current()` nie jest None.
- [ ] **Step 2-4:** failuje, implementacja, przechodzi, commit `Add cycle runner`.

---

### Task 8: Dashboard

**Files:** Create `goldbot/dashboard.py`, `goldbot/web/index.html`, `goldbot/tests/test_dashboard.py`

**Interfaces:** `build_state(store, n_candles=200) -> dict` z kluczami `last_update`, `latest` (z `get_current`), `recent` (20 ostatnich), `stats`, `candles` (`[{"t","c"}]` z ceną mid), `marks` (handlowe werdykty `{"t","verdict","entry"}`); `serve(db_path, port=8787)` (`ThreadingHTTPServer` na `127.0.0.1`, `GET /` strona, `GET /api/state` JSON, nowe `Store` na żądanie).
Strona: werdykt i reżim na górze, wykres Chart.js (linia ceny + znaczniki), uzasadnienie, tabela ostatnich rad, statystyki, odświeżanie co 60 s, znacznik "nieaktualne" gdy ostatnia świeca starsza niż 60 minut ("rynek może być zamknięty"), stały napis o sygnałach analitycznych. Dane wstawiane przez `textContent`.

- [ ] **Step 1: Test** `build_state` po `run_cycle` na danych demo: klucze obecne, `len(candles) <= 200`, `latest["verdict"]` w {KUP, SPRZEDAJ, CZEKAJ}.
- [ ] **Step 2-4:** failuje, implementacja, przechodzi, ręczne otwarcie strony w przeglądarce, commit `Add dashboard`.

---

### Task 9: Walidacja i CLI

**Files:** Create `goldbot/validate.py`, `goldbot/tests/test_validate.py`; Rewrite `goldbot/main.py`

**Interfaces:** `walk_forward(df, p=Params(), split=0.7) -> dict` z kluczami `in_sample`, `out_of_sample`, `in_sample_bez_rezimu`, `out_of_sample_bez_rezimu` (statystyki z `backtest.run`; wersje "bez reżimu" używają `signal_raw`). CLI: `main.py cycle [--demo]`, `main.py dashboard [--port 8787]`, `main.py validate [--demo] [--years 3] [--split 0.7]`. Kodowanie stdout UTF-8. Błąd pobierania danych: komunikat i kod wyjścia 1, bez zapisu werdyktu. Brak `FRED_API_KEY` lub błąd FRED: ostrzeżenie, makro `None`.

- [ ] **Step 1: Test** `walk_forward(prepare(demo...))` zwraca cztery klucze, każdy słownik ma `trades`.
- [ ] **Step 2-4:** failuje, implementacja, przechodzi; `PY goldbot/main.py validate --demo` drukuje tabelę z ostrzeżeniem o danych syntetycznych; commit `Add walk-forward validation and CLI`.

---

### Task 10: Harmonogram i dokumentacja

**Files:** Create `goldbot/install_task.ps1`, `goldbot/README.md`

- [ ] **Step 1:** `install_task.ps1` rejestruje zadanie `GoldAdvisorCycle`: `python main.py cycle` w katalogu `goldbot`, co 15 minut od najbliższej pełnej kwarty plus 1 minuta, `-RepetitionDuration 3650 dni`. Skrypt nie jest uruchamiany automatycznie.
- [ ] **Step 2:** `README.md`: zmienne środowiskowe, komendy, jak założyć klucz FRED i bota Telegram, jak zainstalować zadanie, ostrzeżenie o sygnałach analitycznych.
- [ ] **Step 3:** pełny przebieg `PY -m pytest goldbot/tests -q`, `PY goldbot/main.py cycle --demo`, uruchomienie dashboardu, commit `Add scheduler script and README`.

---

## Self-Review

- **Pokrycie specyfikacji:** silnik (Task 2, 3, 5), dane i magazyn (4, 6), dashboard (8), powiadomienia (6, 7), harmonogram (10), walidacja z podziałem próby (9), obsługa błędów i nieaktualność (8, 9). Brak luk.
- **Placeholdery:** Zadania 3 do 10 opisują interfejsy i zachowanie, pełny kod powstaje w plikach źródłowych z testami pisanymi najpierw. Zadania 1 i 2 mają pełny kod testów.
- **Spójność typów:** stałe reżimu, `prepare`, `make_verdict`, `resolve`, `Store` mają te same nazwy i sygnatury w całym planie.
