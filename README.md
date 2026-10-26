# investing

Doradca i kontroler ryzyka dla CFD, domyślnie na złoto (XAU/USD). Co 15 minut liczy sygnał, sprawdza koszty, wielkość pozycji, ryzyko portfela, wydarzenia i wiadomości, a potem wydaje raport w 8 punktach ze statusem: możliwa transakcja, obserwacja albo brak transakcji. Nie składa ani nie modyfikuje zleceń, tylko podpowiada.

To nie jest porada inwestycyjna. Celem jest jakość decyzji, nie liczba transakcji.

**Wynik badań (docs/research/2026-10-26-optymalizacja-zloto.md):** na publicznych notowaniach złota 2004–2025 strategia M15 nie ma przewagi. Bez kosztów daje około 0R na transakcję, a po spreadzie i kosztach traci średnio 0,16R. Optymalizacja 2880 wariantów metodą walk-forward tego nie zmieniła. Dlatego domyślnie (`strategy_validated: false`) sygnał daje najwyżej status „obserwacja”.

## Jak liczy sygnał

Dwa poziomy:

- Dzienny reżim. Dla złota trzy składniki: trend (EMA 50 vs EMA 200), indeks dolara (FRED `DTWEXBGS`) i realne rentowności 10Y (FRED `DFII10`). Każdy daje +1, 0 albo -1. Suma >= 2 to "sprzyja kupnie", <= -2 to "sprzyja sprzedaży", reszta to "neutralny". Zmiana musi się utrzymać 2 dni. Bez danych z FRED reżim jest zawsze neutralny. Dla instrumentów bez makro (`"macro": false`) reżim to sam trend D1.
- Sygnał M15. Cena nad EMA 200, RSI schodzi pod 40 i wraca, potem histogram MACD przechodzi na plus (dla SHORT odwrotnie, próg RSI 60). SL = 1,5 ATR, TP = 3 ATR. Sygnał przechodzi tylko, jeśli zgadza się z reżimem. Przy spreadzie powyżej 25% ATR jest pomijany.

Najpierw liczy się trend wyższego interwału, wejście potwierdza niższy. Żaden pojedynczy wskaźnik nie wystarcza.

## Analiza do raportu

Nie zmienia reguł sygnału, opisuje rynek:

- EMA 20/50/200 na D1 i M15 oraz ich ułożenie, RSI 14, histogram MACD, ATR 14.
- Wolumen tickowy z OANDA (liczba zmian ceny, nie obrót) względem średniej z 20 świec i VWAP sesji UTC. Bez wolumenu: "brak danych".
- Szczyty i dołki fraktalne (potwierdzane z opóźnieniem, bez zaglądania w przyszłość), struktura wyższych lub niższych szczytów i dołków, najbliższe wsparcie i opór, wybicie i retest ostatniego poziomu.
- Każdy warunek jest potwierdzeniem, sprzecznością albo faktem bez oceny. Siła sygnału to liczba zgodnych warunków, nie prawdopodobieństwo.

## Raport

1. Kierunek trendu i siła sygnału.
2. Potwierdzenia i sygnały sprzeczne.
3. Wiadomości i nadchodzące wydarzenia, ze źródłem, datą publikacji i czasem pobrania; zmiana ceny w 24 h i od zamknięcia D1.
4. Koszty transakcji i przewidywany czas utrzymania.
5. Plan: wejście, SL, TP.
6. Zysk i strata w walucie rachunku: wielkość pozycji, strata przy SL, zysk przy TP po kosztach, depozyt, ryzyko portfela.
7. Warunki unieważniające scenariusz.
8. Status i jego powody.

Raport widać w konsoli, na dashboardzie i w Telegramie. Nagłówek podaje źródło danych i czas pobrania. Program rozróżnia fakty (nagłówek, źródło, data, liczby) od interpretacji (etykieta sentymentu Alpha Vantage) i nie ocenia, co jest już w cenie.

## Status

- **Możliwa transakcja**: sygnał zgodny z reżimem, zabezpieczenia przeszły, znane są kapitał i kurs waluty, pozycja mieści się w limitach portfela.
- **Obserwacja**: reżim wskazuje kierunek, ale brak sygnału wejścia; albo sygnał jest, ale strategia nie jest zwalidowana (`strategy_validated: false`), blokuje go reżim, ważne wydarzenie (domyślnie 2 h przed lub po), brak kapitału, kursu, pliku pozycji, albo w portfelu jest pozycja bez SL.
- **Brak transakcji**: reżim neutralny bez sygnału, nieaktualne dane, otwarta poprzednia rada, dzienny limit strat, za szeroki spread, pozycja mniejsza niż minimalna albo przekroczony limit ryzyka portfela.

## Koszty i ryzyko

- Ryzyko na transakcję domyślnie 0,5% kapitału. Wielkość pozycji jest taka, żeby strata przy SL razem ze znanymi kosztami i poślizgiem nie przekroczyła tego budżetu.
- Koszty: spread (z cen bid/ask), prowizja w obie strony, finansowanie za noc (rollover 17:00 w Nowym Jorku, potrójne naliczenie w konfigurowalny dzień, domyślnie środa), poślizg na SL, przewalutowanie, korekta dywidendowa dla CFD na akcje. Każdy brakujący składnik jest wypisany, a wynik oznaczony jako orientacyjny.
- Czas utrzymania: mediana z co najmniej 10 rozliczonych rad, inaczej górna granica 48 h.
- Portfel: łączne ryzyko otwartych pozycji z `positions.json` i ryzyko w tej samej grupie (sektorze), z limitami 2% i 1% kapitału (założenia robocze, do zmiany w konfiguracji).
- Stop nie gwarantuje ceny: przy luce cenowej rozliczenie rad i backtest wykonują SL po cenie otwarcia świecy, z założonym poślizgiem. Strata może więc przekroczyć 1R.
- Bez dokładania do strat i bez przesuwania SL: ryzyko jest stałe, SL ustalany raz, po -2R w ciągu dnia nowe rady są wstrzymane.

## Zabezpieczenia

- Dane są sprawdzane przed liczeniem: za mało świec, brakujące lub niedodatnie ceny, ask < bid, high < low, czas, który się cofa albo powtarza. Wtedy cykl kończy się błędem i nic nie zapisuje.
- Jeśli ostatnia zamknięta świeca M15 jest starsza niż 30 minut, rada handlowa zamienia się w CZEKAJ, a uzasadnienie mówi, że dane są nieaktualne.
- Dopóki poprzednia rada KUP/SPRZEDAJ jest otwarta, nowej nie ma.
- Gdy rady rozliczone danego dnia (UTC) dały łącznie -2R lub gorzej, nowe rady handlowe są wstrzymane do końca dnia.
- Dane z FRED starsze niż 10 dni są traktowane jak brak, więc reżim jest neutralny.
- Błąd pobierania wydarzeń, wiadomości albo kursu nie przerywa cyklu; trafia do raportu. Starsze dane z bufora są oznaczone czasem ich pobrania.
- W kodzie nie ma niczego, co składa zlecenia. Pilnuje tego test.

## Instalacja

Python 3.12.

```
cd goldbot
python -m pip install -r requirements-dev.txt
```

Zmienne środowiskowe (najlepiej jako zmienne użytkownika Windows):

```
OANDA_TOKEN            token API v20 z konta OANDA Practice
FRED_API_KEY           darmowy klucz z fred.stlouisfed.org (makro i kalendarz publikacji)
ALPHAVANTAGE_API_KEY   klucz z alphavantage.co (wiadomości, wyniki, dywidendy; opcjonalnie)
TELEGRAM_BOT_TOKEN     token bota od @BotFather (opcjonalnie)
TELEGRAM_CHAT_ID       id czatu z botem (opcjonalnie)
GOLDBOT_CONFIG         inna ścieżka do config.json (opcjonalnie)
```

Obsługiwane jest tylko konto Practice. Token generuje się w panelu konta w *Manage API Access*. Według dokumentacji OANDA, API v20 nie działa dla kont prowadzonych przez OANDA TMS Brokers.

## Konfiguracja

W katalogu `goldbot` (te pliki nie trafiają do repozytorium):

- `config.json` (wzór `config.example.json`): waluta i kapitał rachunku, ryzyko i limity, kursy walut, instrumenty z kosztami z tabeli opłat brokera, źródła wydarzeń. `null` oznacza brak danych.
- `positions.json` (wzór `positions.example.json`): otwarte pozycje z platformy brokera. Pusta lista oznacza brak pozycji; brak pliku oznacza, że łączne ryzyko jest nieznane.
- `events.csv` (wzór `events.example.csv`): własny kalendarz wydarzeń, np. FOMC czy wyniki spółek, ze źródłem.

Bez `config.json` program działa, ale nie zna kapitału ani kosztów, więc rada handlowa kończy się co najwyżej obserwacją.

## Użycie

Z katalogu `goldbot`:

```
python main.py validate --years 3   # backtest: 70% danych do strojenia, 30% kontrolne
python main.py cycle                # jeden cykl dla instrumentów z config.json: raport, zapis, Telegram
python main.py dashboard            # http://localhost:8787
python -m pytest tests -q
```

Każda komenda przyjmuje `--instrument X` (np. `--instrument SPX500_USD`); każdy instrument ma osobną bazę. `cycle`, `dashboard` i `validate` mają flagę `--demo`: losowe dane, osobna baza `goldbot-demo.db`, bez Telegrama i bez zapytań do API. Służy tylko do sprawdzenia, czy program działa.

`validate` wypisuje, które koszty są uwzględnione, a których brakuje. Najpierw `validate` na prawdziwych danych. Jeśli wynik na okresie kontrolnym (`out_of_sample`) jest na minusie, nie ma sensu odpalać reszty.

## Źródła danych

- **OANDA Practice**: świece M15 i D1 z cenami bid/ask i wolumenem tickowym, kurs waluty rachunku (np. `USD_PLN`).
- **FRED**: realne rentowności i indeks dolara; kalendarz publikacji (`fred/release/dates`) dla `release_id` z konfiguracji. Daty bez godziny obejmują cały dzień UTC.
- **Alpha Vantage**: wiadomości (`NEWS_SENTIMENT`), kalendarz wyników (`EARNINGS_CALENDAR`), sektor i dywidendy (`OVERVIEW`). Darmowy klucz ma niski dzienny limit, więc odpowiedzi są buforowane w bazie (wiadomości co 3 h, dane spółki raz na dobę).
- **TradingView**: nie ma publicznego API. Można użyć eksportu CSV wykresu (`"source": "csv"`). Eksport ma jedną cenę, więc bid i ask są przybliżone typowym spreadem z konfiguracji, co raport zaznacza.

Formaty odpowiedzi FRED (kalendarz) i Alpha Vantage są przyjęte z dokumentacji i przetestowane na przykładowych odpowiedziach, nie na żywym API.

## Badania na danych historycznych

`goldbot/research/` testuje strategię na publicznych notowaniach złota: pobranie danych (`download.sh`), przeliczenie czasu serwera na UTC, model spreadu z prawdziwych bid/ask Dukascopy, optymalizacja walk-forward (`study.py`), Monte Carlo ryzyka utraty kapitału, porównanie z losowymi wejściami, alternatywna strategia trendowa na D1 (`trend.py`) oraz inne rodziny strategii bez ograniczeń ryzyka: sesje, momentum, średnie, RSI(2), wybicia (`edges.py`). Wyniki i wnioski: `docs/research/`.

Filtry strategii (sesja, zgodność EMA 20/50, zapas do szczytu lub dołka, wyłączenie reżimu) ustawia się w `config.json` w sekcji `strategy` instrumentu; domyślnie są wyłączone. `strategy_validated: true` ustaw dopiero wtedy, gdy `validate` na danych Twojego brokera da dodatni wynik na okresie kontrolnym po kosztach.

## Uruchamianie co 15 minut

`install_task.ps1` dodaje zadanie do Harmonogramu zadań Windows (`GoldAdvisorCycle`), które odpala `main.py cycle` co 15 minut. Trzeba go uruchomić ręcznie:

```
powershell -ExecutionPolicy Bypass -File goldbot\install_task.ps1
```

Usunięcie zadania:

```
Unregister-ScheduledTask -TaskName GoldAdvisorCycle -Confirm:$false
```

## Pliki

```
goldbot/
  main.py          komendy
  cycle.py         jeden cykl doradcy i jego kontekst
  regime.py        reżim dzienny
  strategy.py      sygnał M15
  indicators.py    EMA, RSI, MACD, ATR, VWAP, wolumen
  structure.py     szczyty i dołki, wsparcia i opory, wybicia i retesty
  analysis.py      fakty do raportu, potwierdzenia i sprzeczności
  advisor.py       werdykt i uzasadnienie
  guards.py        zabezpieczenia danych i rad
  decision.py      status decyzji i blokady ryzyka
  report.py        raport w 8 punktach
  config.py        konfiguracja rachunku, kosztów i instrumentów
  costs.py         koszty CFD i czas utrzymania
  risk.py          wielkość pozycji, depozyt, ryzyko portfela
  events.py        wydarzenia: CSV, FRED, Alpha Vantage
  news.py          wiadomości z Alpha Vantage
  sources.py       pobieranie danych dodatkowych z buforem
  resolve.py       rozliczanie rad
  backtest.py      backtest
  validate.py      podział na okres do strojenia i kontrolny
  oanda.py         pobieranie świec z OANDA + dane demo
  tradingview.py   import eksportu CSV z TradingView
  macro.py         dane z FRED
  notify.py        Telegram
  store.py         SQLite
  dashboard.py     serwer dashboardu (web/index.html)
  research/        badania na danych historycznych (dane, walk-forward, Monte Carlo, trend D1)
docs/superpowers/  specyfikacje i plany
docs/research/     wyniki badań
```
