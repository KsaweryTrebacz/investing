# Analityk i kontroler ryzyka CFD: projekt

Data: 2026-10-23. Rozszerza `2026-10-20-gold-advisor-design.md`. Zasada nadrzędna bez zmian: program tylko doradza i nie składa zleceń.

## Cel

Doradca ma oceniać możliwe transakcje CFD tak, jak opisuje to rola „analityk i kontroler ryzyka portfela CFD”: trend wyższego interwału z potwierdzeniem na niższym, koszty brokera, wielkość pozycji przy ryzyku 0,5% kapitału, łączne ryzyko portfela, wydarzenia i wiadomości ze źródłem i datą, raport w 8 punktach i jeden z trzech statusów. Celem jest jakość decyzji, nie liczba transakcji.

## Mapowanie wymagań

| Wymaganie | Rozwiązanie |
|---|---|
| Źródła danych ze źródłem i czasem | Każdy raport ma sekcję danych: dostawca, czas ostatniej świecy, czas pobrania, data ostatniej obserwacji makro, źródło i data kosztów, kursu walut i pliku pozycji. Nieaktualne dane nadal blokują rady. |
| TradingView | Brak publicznego API. Obsługa eksportu CSV z wykresu TradingView jako źródła świec. |
| Alpha Vantage | Wiadomości (`NEWS_SENTIMENT`), kalendarz wyników (`EARNINGS_CALENDAR`), dane spółki i dywidendy (`OVERVIEW`). Klucz `ALPHAVANTAGE_API_KEY`. |
| Wydarzenia makro | Kalendarz publikacji FRED (`fred/release/dates`) dla wskazanych publikacji oraz własny plik `events.csv`. |
| EMA 20/50/200, RSI, MACD, ATR | EMA 20/50/200 liczone na D1 i M15 i raportowane, reszta jak dotąd. Reguły sygnału bez zmian, żeby wyniki backtestu dało się porównać. |
| Wolumen i VWAP | Wolumen tickowy z OANDA (opisany jako tickowy, nie obrót), VWAP sesji UTC. Bez wolumenu: „brak danych”. |
| Wsparcia, opory, wybicia, retesty, struktura | Szczyty i dołki fraktalne potwierdzane z opóźnieniem (bez zaglądania w przyszłość), najbliższe wsparcie i opór, wybicie i retest ostatniego poziomu, struktura wyższych lub niższych szczytów i dołków. |
| Fakty a interpretacja | Nagłówki, daty i liczby są faktami. Etykieta sentymentu Alpha Vantage jest opisana jako interpretacja dostawcy. Program nie zgaduje, co jest w cenie; podaje zmianę ceny w ostatnich 24 h i od zamknięcia D1. |
| Koszty CFD | Spread z bid/ask, prowizja, finansowanie za noc (rollover 17:00 Nowy Jork, potrójne naliczenie w konfigurowalny dzień), poślizg, przewalutowanie, korekta dywidendowa. Każdy brakujący składnik jest wypisany, a wynik oznaczony jako orientacyjny. |
| Czas utrzymania | Mediana z rozliczonych rad (co najmniej 10), inaczej górna granica 48 h (wygaśnięcie). |
| Ryzyko 0,5% | Domyślne `risk_per_trade = 0.005`. Wielkość pozycji liczona tak, żeby strata przy SL razem ze znanymi kosztami i poślizgiem nie przekroczyła budżetu. |
| Strata, pozycja, depozyt, zysk po kosztach | W walucie rachunku, z kursem i jego źródłem. Bez kapitału lub kursu nie ma „możliwej transakcji”, tylko obserwacja. |
| Łączne ryzyko i sektory | Plik `positions.json` z otwartymi pozycjami. Limity łącznego ryzyka i ryzyka grupy (sektora) w konfiguracji. Pozycja bez SL ma ryzyko nieznane. |
| Stop nie gwarantuje ceny | Rozliczenie rad i backtest wykonują SL po cenie otwarcia przy luce i odejmują założony poślizg. Raport zawsze o tym przypomina. |
| Bez dokładania do strat, bez przesuwania SL | Bez zmian: stałe ryzyko, dzienny limit −2R, SL ustalany raz. |
| Format 8 punktów | `report.py`: trend i siła, potwierdzenia i sprzeczności, wiadomości i wydarzenia, koszty i czas, plan, zysk i strata, warunki unieważnienia, status. |
| Status | `MOZLIWA_TRANSAKCJA`, `OBSERWACJA`, `BRAK_TRANSAKCJI`. |
| Portfel wielu instrumentów | Instrumenty w konfiguracji, osobna baza na instrument, reżim bez makro (sam trend D1) dla instrumentów innych niż złoto. |

## Status decyzji

- `MOZLIWA_TRANSAKCJA`: sygnał M15 zgodny z reżimem, wszystkie zabezpieczenia przeszły, znane są kapitał i kurs, pozycja mieści się w limitach portfela.
- `OBSERWACJA`: reżim wskazuje kierunek, ale nie ma sygnału wejścia; albo sygnał jest, lecz zablokował go reżim, ważne wydarzenie, brak kapitału, kursu lub pliku pozycji, albo pozycja bez SL w portfelu.
- `BRAK_TRANSAKCJI`: reżim neutralny bez sygnału, nieaktualne dane, otwarta poprzednia rada, dzienny limit strat, za szeroki spread, pozycja mniejsza niż minimalna albo przekroczony limit ryzyka portfela.

## Konfiguracja

`goldbot/config.json` (poza repozytorium, wzór w `config.example.json`): rachunek (waluta, kapitał, ryzyko, limity), kursy walut, plik pozycji, wydarzenia, instrumenty z kosztami. Wartość `null` oznacza brak danych i jest tak raportowana. Sekrety tylko w zmiennych środowiskowych.

## Założenia do sprawdzenia

- Limity portfela 2% łącznie i 1% na grupę oraz blokada 2 h wokół ważnego wydarzenia to założenia robocze.
- Potrójne finansowanie w środę to konwencja rynku walutowego; trzeba ją potwierdzić u brokera.
- Format odpowiedzi FRED i Alpha Vantage przyjęty z dokumentacji, nie sprawdzony na żywym API z tego środowiska.
- Czas publikacji wiadomości jest pokazywany tak, jak podaje go Alpha Vantage.

## Poza zakresem

Składanie i modyfikowanie zleceń, konto live, łączenie się z rachunkiem brokera, ocena „co jest w cenie” wymagająca interpretacji (zostaje dla analityka), uczenie maszynowe.
