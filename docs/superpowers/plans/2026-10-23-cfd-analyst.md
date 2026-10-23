# Analityk i kontroler ryzyka CFD: plan

**Cel:** doprowadzić `goldbot` do specyfikacji `docs/superpowers/specs/2026-10-23-cfd-analyst-design.md`.

**Zasady:** program nie składa zleceń (test `test_package_contains_no_order_code` zostaje). Reguły sygnału M15 i reżimu bez zmian. Każdy moduł ma testy na małych, ręcznie policzonych przykładach. Integracje sieciowe testowane na przykładowych odpowiedziach, bez sieci.

## Task 1: Konfiguracja, koszty, ryzyko
- `config.py`: `Account`, `Costs`, `Instrument`, `load_config()`; brak pliku daje wartości domyślne i braki danych.
- `costs.py`: liczba naliczeń finansowania (17:00 Nowy Jork, potrójne w wybrany dzień), koszty na jednostkę (prowizja w obie strony, finansowanie, poślizg), lista braków, szacunek czasu utrzymania.
- `risk.py`: `plan_trade()` (jednostki, strata przy SL, zysk przy TP po kosztach, depozyt, wartość nominalna, w walucie rachunku), `load_positions()`, `portfolio_check()` (łącznie i w grupie).
- `Params.risk_per_trade` = 0.005.

## Task 2: Wykonanie SL i koszty w rozliczaniu i backteście
- `resolve.py`: SL po cenie otwarcia przy luce, poślizg, `cost_r` z prowizji i finansowania.
- `backtest.py`: to samo plus wygaśnięcie po 48 h jak na żywo, koszty z profilu.
- `validate.py`, `main.py`: wypisanie, które koszty są uwzględnione, a których brakuje, zamiast ogólnego „po kosztach”.

## Task 3: Analiza techniczna
- `oanda.py`: kolumna `volume`; dane demo z wolumenem.
- `indicators.py`: `vwap()` sesji UTC, stosunek wolumenu do średniej.
- `structure.py`: szczyty i dołki fraktalne, struktura, wsparcie i opór, wybicie i retest.
- `analysis.py`: EMA 20/50/200 na D1 i M15, lista potwierdzeń i sprzeczności dla kierunku, siła jako liczba zgodnych potwierdzeń.

## Task 4: Wydarzenia i wiadomości
- `events.py`: plik CSV, kalendarz FRED, wyniki i dywidendy z Alpha Vantage; nadchodzące w oknie utrzymania; blokada wokół ważnego wydarzenia.
- `news.py`: nagłówki Alpha Vantage ze źródłem, czasem publikacji i pobrania; sentyment jako interpretacja dostawcy.
- Błędy sieci nie przerywają cyklu, trafiają do raportu.

## Task 5: Raport, status, cykl
- `decision.py`: blokady ryzyka (wydarzenie, kapitał, kurs, portfel, minimalna pozycja) i `decide()`.
- `report.py`: raport w 8 punktach i jego wersja tekstowa (CLI, Telegram).
- `cycle.py`: kontekst (`Context`) z konfiguracją, kursem, pozycjami, wydarzeniami, wiadomościami i metadanymi danych.
- `store.py`: kolumny `volume`, `decision`, `report`, `cost_r` z migracją istniejącej bazy; statystyki po kosztach.
- `notify.py`: zapis także przy zmianie statusu; wiadomość z raportu.
- `dashboard.py`, `web/index.html`: status i sekcje raportu.

## Task 6: Wiele instrumentów i źródła
- `regime.py`, `pipeline.py`: reżim z samego trendu dla instrumentów bez makro.
- `tradingview.py`: import eksportu CSV z TradingView.
- `main.py`: `--instrument`, cykl dla wszystkich instrumentów z konfiguracji, osobna baza na instrument, kurs walut z OANDA lub konfiguracji.

## Task 7: Dokumentacja
- README, `config.example.json`, `positions.example.json`, `events.example.csv`, `.gitignore`.
