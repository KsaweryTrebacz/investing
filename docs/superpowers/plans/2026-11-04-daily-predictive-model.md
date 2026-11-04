# Dzienny model predykcyjny: plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Doradca raz dziennie mówi KUP / SPRZEDAJ / TRZYMAJ / ZAMKNIJ / CZEKAJ na podstawie modelu ML walidowanego walk-forward na prawdziwych danych dziennych złota.

**Architecture:** Nowe moduły w `goldbot/`: `sources.py` (Yahoo+FRED albo OANDA za wspólnym interfejsem), `features.py` (cechy przyczynowe i cel), `model.py` (walk-forward, ocena, bramka przewagi, zapis modelu), `daily_advisor.py` (werdykt i rozliczanie), `daily_cycle.py` (jeden cykl). CLI `main.py` dostaje `train` i `daily`. Istniejący kod M15 bez zmian poza kolumną `kind` w tabeli `verdicts`.

**Tech Stack:** Python 3.12, pandas, numpy, requests, scikit-learn (HistGradientBoostingClassifier), joblib, sqlite3, pytest.

## Global Constraints

- Tylko OANDA Practice; żaden plik nie zawiera kodu składającego zlecenia (test `test_package_contains_no_order_code`).
- Wszystkie cechy liczone wyłącznie z danych znanych na zamknięciu dnia `t`; makro przesunięte o 1 dzień.
- Model uczony tylko na obserwacjach z celem znanym do `t - 10` sesji.
- Próg wybierany tylko na prognozach do 2020-12-31; okres kontrolny od 2021-01-01.
- Bramka przewagi: AUC > 0,52 i Sharpe > 0 i zwrot > 0 w okresie kontrolnym; inaczej brak rad handlowych.
- Spread Yahoo: `bid_c = close - 0.25`, `ask_c = close + 0.25`.
- Komunikaty po polsku, bez porad licencjonowanego doradcy (DISCLAIMER z `notify.py`).

---

### Task 1: Źródła danych (`sources.py`)

**Files:** Create `goldbot/sources.py`, `goldbot/tests/test_sources.py`, `goldbot/tests/fixtures/yahoo_sample.json`, `goldbot/tests/fixtures/fred_sample.csv`. Modify `goldbot/requirements.txt` (+ scikit-learn, joblib).

**Interfaces (Produces):**
- `@dataclass DailyData: gold: pd.DataFrame (time[UTC tz], bid_o,bid_h,bid_l,bid_c, ask_o..ask_c), usd: pd.Series|None, yld: pd.Series|None, source: str, warnings: list[str]`
- `parse_yahoo_chart(payload: dict) -> pd.DataFrame` (time, open, high, low, close)
- `parse_fred_csv(text: str) -> pd.Series` (naiwny DatetimeIndex)
- `with_spread(ohlc: pd.DataFrame, half: float = 0.25) -> pd.DataFrame` (bid_*/ask_*)
- `FreeSource().fetch_daily(years) -> DailyData`, `OandaSource().fetch_daily(years) -> DailyData`
- `pick_source(name: str, env=os.environ) -> str` ("free"/"oanda")
- `is_daily_stale(last_time, now) -> bool` (poniedziałek akceptuje piątek; tolerancja 1 dzień sesyjny)
- `cross_check(oanda_gold, yahoo_gold, n=20) -> str|None` ostrzeżenie gdy mediana różnicy > 2%.
- Cache: `goldbot/cache/` (w .gitignore), `fetch_json(url, name, offline)`.

- [ ] Test: parse fixtures, with_spread kolumny i ask>bid, pick_source bez/z tokenem, is_daily_stale (piątek→poniedziałek nie stale, 3 dni robocze stale), cross_check zwraca ostrzeżenie przy 3% różnicy.
- [ ] Implementacja, testy zielone, commit.

### Task 2: Cechy i cel (`features.py`)

**Interfaces (Produces):**
- `HORIZON = 10`
- `build_features(gold, usd=None, yld=None, horizon=HORIZON) -> pd.DataFrame` indeks: `time`; kolumny `FEATURES` (lista nazw) + `close`, `atr`, `fwd_ret`, `cost`, `y` (NaN w ostatnich `horizon` wierszach).
- `FEATURES_PL: dict[str,str]` nazwy po polsku.

Cechy: ret_1, ret_5, ret_10, ret_20, ret_60, dist_ema50, dist_ema200, rsi14, vol20, atr_pct, range_pos250, usd_chg5, usd_chg20, yld_chg5, yld_chg20, reg_trend, reg_dollar, reg_yields.

- [ ] Test: brak wycieku (ucięcie do t daje te same wartości w wierszu t), `y` = 1 gdy log(close[t+10]/close[t]) > cost, makro dopasowane wstecz z przesunięciem 1 dnia, NaN makro gdy None.
- [ ] Implementacja, testy, commit.

### Task 3: Model walk-forward (`model.py`)

**Interfaces (Produces):**
- `make_model() -> HistGradientBoostingClassifier` (max_depth=3, learning_rate=0.05, max_iter=200, l2_regularization=1.0, min_samples_leaf=50)
- `walk_forward(feat: pd.DataFrame, min_train=1260, step=63, horizon=10) -> pd.Series p_up` (NaN przed pierwszym oknem)
- `strategy_returns(p_up, ret_1_fwd, cost, thr) -> pd.Series` zwroty dzienne po kosztach zmiany pozycji
- `metrics(p_up, y, daily_ret, cost, thr) -> dict` (n, accuracy, auc, return_%, sharpe, max_dd_%, flips, bh_return_%)
- `choose_threshold(p_up, feat, split="2020-12-31", grid=(0.55,0.58,0.60,0.65)) -> float`
- `edge_verdict(oos: dict) -> (bool, str)`
- `evaluate(feat) -> report dict` {threshold, in_sample, out_of_sample, by_year, has_edge, edge_text, trained_at, features}
- `fit_final(feat) -> (model, importances: dict)`; `save_model(path, model, feats, thr)`, `load_model(path)`
- `predict_last(model, feat) -> float`

- [ ] Test na syntetycznych danych z wbudowanym sygnałem: p_up NaN przed min_train; pierwszy model nie widzi wierszy > t-10 (test przez monkeypatch fit rejestrujący indeksy); metrics na ręcznych wartościach; edge_verdict False dla auc 0.5.
- [ ] Implementacja, testy, commit.

### Task 4: Werdykt dzienny i rozliczanie (`daily_advisor.py`, `store.py`)

**Files:** Create `daily_advisor.py`, `tests/test_daily_advisor.py`. Modify `store.py` (kolumna `kind`, metody z filtrem kind), `tests/test_store.py`.

**Interfaces (Produces):**
- `make_daily_verdict(last_row, p_up, thr, has_edge, edge_text, open_v, importances, stats, warnings, horizon=10, stop_atr=2.0) -> dict` kolumny jak VERDICT_COLS + `kind='D1'`, `p_up`, `horizon`, verdict ∈ {KUP, SPRZEDAJ, TRZYMAJ, ZAMKNIJ, CZEKAJ}; dla ZAMKNIJ pole `close_open=True`.
- `resolve_daily(v, gold, horizon=10) -> (status, outcome_r, iso)|None` status SL/EXPIRED.
- `Store`: `verdicts.kind TEXT DEFAULT 'M15'`, `p_up REAL`, `horizon INTEGER`; `open_verdicts(kind=None)`, `last_verdict(kind=None)`, `recent_verdicts(n, kind=None)`, `stats(kind=None)`, `set_current(v, key='current')`, `get_current(key='current')`, migracja ALTER TABLE jeśli kolumny brak.

- [ ] Testy: każdy werdykt; brak przewagi → CZEKAJ z tekstem; ZAMKNIJ gdy otwarta długa i p_up <= 1-thr; resolve_daily SL i EXPIRED; migracja starej bazy.
- [ ] Implementacja, testy, commit.

### Task 5: Cykl dzienny, CLI, Telegram, dashboard, scheduler

**Files:** Create `daily_cycle.py`, `install_daily_task.ps1`, `tests/test_daily_cycle.py`. Modify `main.py` (train, daily, --source, --offline), `notify.py` (`format_daily_message`), `dashboard.py` + `web/index.html` (sekcja dzienna), `README.md`, `.gitignore` (cache/, model files).

**Interfaces:** `run_daily_cycle(data: DailyData, model_bundle, report, store, send=None, now=None) -> dict`.

- [ ] Test cyklu na syntetycznych danych z fałszywym modelem (klasa z predict_proba) i raportem has_edge True/False.
- [ ] Implementacja, testy, commit.

### Task 6: Walidacja na prawdziwych danych

- [ ] `python main.py train --source free` i zapis raportu; `python main.py daily --source free`; dashboard sprawdzony w przeglądarce; wynik opisany w README (uczciwie, także gdy brak przewagi). Commit.
