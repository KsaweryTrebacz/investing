# Dzienny model predykcyjny dla złota: projekt

Data: 2026-11-04. Status: zatwierdzony przez użytkownika.

## Cel

Rozbudowa doradcy XAU/USD o model predykcyjny działający na danych dziennych. Program raz dziennie, po zamknięciu sesji, mówi: KUP, SPRZEDAJ, TRZYMAJ albo CZEKAJ, z poziomem wejścia, stopem, horyzontem i uzasadnieniem po polsku. Nadal tylko doradza, nie składa zleceń.

Warunek użytkownika: ma to działać na prawdziwych danych, a nie udawać. Dlatego model jest oceniany wyłącznie poza próbą (walk-forward) i sam odmawia rad handlowych, gdy nie ma udowodnionej przewagi.

## Decyzje z rozmowy

- Brak tokena OANDA na tym komputerze. Budujemy i walidujemy na darmowych, prawdziwych danych (Yahoo Finance, FRED). OANDA zostaje głównym źródłem na żywo i włącza się sama, gdy pojawi się `OANDA_TOKEN`.
- Model: uczenie maszynowe (gradient boosting) z istniejącym reżimem dziennym jako filtrem. Odrzucone: same reguły (brak prognozy), samo ML (brak wyjaśnialności, większe ryzyko przeuczenia).
- Horyzont: dni-tygodnie, jedna decyzja dziennie. Intraday M15 odrzucony, bo bez OANDA nie ma lat danych M15 do uczciwej walidacji. Istniejący kod M15 zostaje nietknięty.
- Pozycje krótkie dozwolone (SPRZEDAJ = otwórz krótką albo zamknij długą, zależnie od stanu).

## Komponenty

### 1. Źródła danych (`sources.py`)

Wspólny interfejs: `fetch_daily(years) -> DailyData` z polami `gold` (DataFrame: time, open, high, low, close, bid_c, ask_c), `usd` (Series), `yld` (Series), `source` (nazwa), `warnings` (lista).

- `FreeSource`: złoto z Yahoo Finance `GC=F` (interwał 1d, zakres 15 lat), dolar z Yahoo `DX-Y.NYB`, realne rentowności z FRED CSV `DFII10` (bez klucza, `fredgraph.csv`). Dla Yahoo bid/ask nie istnieją, więc `bid_c = close - 0.25`, `ask_c = close + 0.25` (typowy spread OANDA na XAU/USD ok. 0,5 USD). Koszt transakcji w backteście i w radach jest liczony z tego spreadu.
- `OandaSource`: istniejący klient `oanda.Oanda`, świece `D`, bid/ask prawdziwe. Dolar i rentowności z FRED (z kluczem przez `macro.py`, bez klucza przez CSV).
- Wybór: `--source auto|free|oanda`. `auto` bierze OANDA, gdy jest `OANDA_TOKEN`, inaczej `free`. Gdy aktywne jest OANDA, program pobiera też Yahoo i porównuje ostatnie 20 zamknięć; różnica mediany powyżej 2% daje ostrzeżenie w uzasadnieniu (kontrakt a spot różnią się o bazę, zwykle poniżej 1%).
- Pamięć podręczna: surowe odpowiedzi zapisywane do `goldbot/cache/*.json|csv` z datą; `train` może działać offline na ostatnim pobraniu.
- Zabezpieczenia: `guards.validate_candles` na świecach dziennych (po uzupełnieniu brakujących kolumn bid/ask o,h,l z mid), świeżość: ostatnia świeca nie starsza niż 1 dzień sesyjny (poniedziałek akceptuje piątek), makro starsze niż 10 dni = brak. Przy nieświeżych danych rada handlowa zamienia się w CZEKAJ z powodem.

### 2. Cechy (`features.py`)

`build_features(gold, usd, yld) -> DataFrame` indeksowany datą sesji. Wszystkie cechy liczone z danych dostępnych na zamknięciu dnia `t`:

- zwroty logarytmiczne złota za 1, 5, 10, 20, 60 sesji,
- odległość zamknięcia od EMA 50 i EMA 200 (w procentach),
- RSI 14,
- zmienność: odchylenie std zwrotów dziennych z 20 sesji, ATR 14 jako procent ceny,
- pozycja zamknięcia w zakresie 250 sesji (0..1),
- zmiana indeksu dolara za 5 i 20 sesji,
- zmiana realnych rentowności za 5 i 20 sesji (w punktach procentowych),
- składniki reżimu z `regime.py` (trend, dolar, rentowności: -1/0/1).

Makro jest dopasowywane do daty sesji złota metodą `merge_asof` wstecz (wartość znana najpóźniej w dniu `t`). FRED publikuje z opóźnieniem jednego dnia, więc dodatkowo stosowane jest przesunięcie o 1 dzień.

Cel: `y = 1`, gdy zwrot logarytmiczny od zamknięcia `t` do zamknięcia `t + 10 sesji` przekracza koszt (spread / cena), inaczej `0`. Ostatnie 10 wierszy nie ma celu i służą tylko do prognozy.

Test braku wycieku: cechy dla wiersza `t` liczone na danych uciętych do `t` muszą być identyczne jak na pełnej ramce.

### 3. Model (`model.py`)

- Klasyfikator: `sklearn.ensemble.HistGradientBoostingClassifier` z konserwatywnymi parametrami (max_depth 3, learning_rate 0.05, max_iter 200, l2_regularization 1.0, min_samples_leaf 50). Parametry stałe, nie strojone na danych kontrolnych.
- Walk-forward: okno rozszerzające. Pierwsze uczenie po 5 latach danych. Co 63 sesje (kwartał) model jest uczony od początku na wszystkich danych do dnia `t - 10` (żeby cel ostatnich obserwacji był znany) i prognozuje kolejne 63 sesje. Wynik: szereg `p_up` poza próbą dla całej historii od roku 6.
- Ocena (`evaluate`): trafność, AUC, i wynik strategii dziennej: pozycja +1 gdy `p_up >= thr`, -1 gdy `p_up <= 1 - thr`, 0 inaczej; zwrot dzienny = pozycja × zwrot złota minus koszt przy zmianie pozycji. Raport rok po roku: zwrot, Sharpe, maksymalne obsunięcie, liczba zmian pozycji, kontra kup i trzymaj.
- Próg `thr` wybierany z siatki {0.55, 0.58, 0.60, 0.65} wyłącznie na okresie strojenia (prognozy do końca 2020). Okres kontrolny: 2021 do dziś. Raport pokazuje oba osobno.
- Werdykt o przewadze (`edge_verdict`): model „ma przewagę", gdy w okresie kontrolnym AUC > 0,52 i Sharpe strategii po kosztach > 0 i zwrot strategii > 0. Inaczej „brak udowodnionej przewagi". Wynik zapisany w `goldbot/model_report.json` razem z datą, progiem i metrykami.
- Model produkcyjny: po walidacji uczony na całej historii, zapisany `joblib` do `goldbot/model.joblib` wraz z listą cech i progiem. Cykl dzienny wczytuje go, a gdy plik jest starszy niż 100 dni, uczy ponownie.

### 4. Werdykt dzienny (`daily_advisor.py`)

Wejście: ostatni wiersz cech, `p_up`, próg, reżim, raport przewagi, otwarta rada ze sklepu.

- Brak przewagi w raporcie: werdykt CZEKAJ, uzasadnienie zaczyna się od „Model nie ma udowodnionej przewagi poza próbą (AUC x, Sharpe y)". Prognoza jest pokazywana informacyjnie.
- KUP: `p_up >= thr` i reżim nie jest SPRZYJA_SPRZEDAZY i brak otwartej rady. Wejście po ask, stop = wejście - 2 ATR, horyzont 10 sesji.
- SPRZEDAJ: `p_up <= 1 - thr` i reżim nie jest SPRZYJA_KUPNIE i brak otwartej rady. Wejście po bid, stop = wejście + 2 ATR.
- TRZYMAJ: otwarta rada istnieje i prognoza nadal po jej stronie (`p_up > 0.5` dla długiej, `< 0.5` dla krótkiej).
- ZAMKNIJ: otwarta rada istnieje i prognoza przeszła na przeciwną stronę progu. Rada zostaje rozliczona po bieżącej cenie, a w tym samym cyklu nie otwiera się nowej (nowa najwcześniej następnego dnia).
- CZEKAJ: pozostałe przypadki.

Uzasadnienie: prawdopodobieństwo, trzy cechy o największym wkładzie (z `permutation_importance` liczonej raz przy uczeniu, nazwy po polsku), tekst reżimu z `advisor.regime_text`, historyczna skuteczność rad tego typu ze sklepu, ostrzeżenia ze źródła danych.

Rozliczanie (`resolve_daily`): stop po low/high dnia, inaczej po 10 sesjach po zamknięciu; wynik w R (ryzyko = 2 ATR) tak jak w `resolve.py`. Rady dzienne trzymane w tej samej tabeli `verdicts` z kolumną `kind = 'D1'` (istniejące wiersze dostają `M15`).

### 5. CLI, dashboard, uruchamianie

- `python main.py train [--source auto|free|oanda] [--years 15] [--offline]`: pobiera dane, liczy walk-forward, drukuje raport, zapisuje `model_report.json` i `model.joblib`.
- `python main.py daily [--source ...]`: jeden cykl dzienny: dane, zabezpieczenia, rozliczenie otwartej rady, werdykt, zapis, Telegram przy zmianie werdyktu.
- `python main.py dashboard`: istniejąca strona dostaje na górze sekcję dziennego werdyktu, prawdopodobieństwo, status przewagi i tabelę rad dziennych.
- `install_daily_task.ps1`: zadanie Harmonogramu `GoldAdvisorDaily` o 23:30 UTC (po zamknięciu sesji w Nowym Jorku), od poniedziałku do piątku, plus `train` w sobotę o 08:00.
- Nowe zależności: `scikit-learn`, `joblib`.

## Obsługa błędów

- Awaria Yahoo albo FRED: cykl kończy się bez werdyktu, ostatni werdykt na dashboardzie oznaczony jako nieaktualny. Gdy jest pamięć podręczna z dzisiaj, używana jest ona.
- Brak makro: cechy makro ustawione jako NaN (HistGradientBoosting obsługuje NaN), reżim NEUTRALNY, uzasadnienie to mówi.
- Brak `model.joblib` albo `model_report.json`: `daily` kończy się komunikatem, żeby najpierw uruchomić `train`.

## Testy

- `test_sources.py`: parsowanie zapisanej odpowiedzi Yahoo i CSV FRED z plików w `tests/fixtures`, uzupełnianie bid/ask, świeżość z weekendem, wybór źródła `auto`.
- `test_features.py`: brak wycieku (ucięcie do `t`), poprawne przesunięcie celu, dopasowanie makro wstecz.
- `test_model.py`: walk-forward na syntetycznych danych: liczba okien, brak prognoz przed 5. rokiem, model uczony tylko na danych sprzed `t - 10`; `edge_verdict` na ręcznych metrykach.
- `test_daily_advisor.py`: każdy werdykt (KUP, SPRZEDAJ, TRZYMAJ, ZAMKNIJ, CZEKAJ, brak przewagi) na ręcznie zadanych wejściach; rozliczanie stopu i horyzontu.
- Istniejący test, że kod nie składa zleceń, rozszerzony o nowe pliki.

## Kryterium sukcesu

`python main.py train --source free` działa na prawdziwych danych i drukuje raport z okresem kontrolnym 2021-2026. `python main.py daily --source free` wydaje werdykt z uzasadnieniem. Jeśli model nie ma przewagi, program to mówi i nie wydaje rad handlowych. To jest wynik poprawny, a nie błąd.

## Poza zakresem

Składanie zleceń, konto live, dane M15 z OANDA (zostają jak są), FinBERT i wiadomości, złoto w PLN, aplikacja mobilna.
