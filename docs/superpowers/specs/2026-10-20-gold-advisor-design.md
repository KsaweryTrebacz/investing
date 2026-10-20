# Doradca XAU/USD: projekt

Data: 2026-10-20. Status: zatwierdzony przez użytkownika, czeka na przegląd pliku.

## Cel

Lokalny program, który mówi, kiedy opłaca się kupić i sprzedać złoto (XAU/USD, CFD na OANDA). Tylko doradza. Nie składa zleceń. Rady to sygnały analityczne, nie porada licencjonowanego doradcy.

## Podejście

Reguły jawne w dwóch warstwach (podejście A). Odrzucone: model uczenia maszynowego jako rdzeń (ryzyko przeuczenia, brak wyjaśnialności) i głosowanie wielu wskaźników (skorelowane wskaźniki dają fałszywe poczucie pewności). Uczenie maszynowe i FinBERT mogą wrócić później jako filtr, jeśli wykażą poprawę poza próbą.

## Komponenty

### 1. Silnik analizy (`goldbot`, rozbudowa istniejącego kodu)
- **Warstwa dzienna (D1).** Trzy składniki, każdy daje +1, 0 lub -1:
  - trend: EMA 50 względem EMA 200 oraz nachylenie EMA 50,
  - siła dolara: indeks USD lub EUR/USD,
  - realne rentowności USA (FRED, szereg DFII10).
- **Reżim.** Suma składników daje: SPRZYJA_KUPNIE, NEUTRALNY, SPRZYJA_SPRZEDAZY. Zmiana reżimu z histerezą (wymaga utrzymania nowego stanu przez co najmniej 2 kolejne zamknięte dni), żeby unikać migotania.
- **Warstwa M15.** Obecna strategia: EMA 200, RSI 14 (próg 40 dla LONG, 60 dla SHORT), histogram MACD, SL 1,5 ATR, TP 3 ATR, filtr spreadu. LONG tylko w reżimie kupna, SHORT tylko w reżimie sprzedaży, w neutralnym brak wejść.
- **Werdykt.** KUP, SPRZEDAJ lub CZEKAJ, z poziomami wejścia, SL, TP oraz uzasadnieniem w kilku zdaniach, wygenerowanym z wartości wskaźników.

### 2. Dane i magazyn
- Źródła: OANDA Practice (świece M15 i D1, bid/ask), FRED (rentowności, dolar), klucz darmowy, trzymany w zmiennych środowiskowych.
- SQLite: tabele świec, werdyktów i wyników werdyktów. Wynik werdyktu to rozstrzygnięcie po fakcie (TP, SL lub wygaśnięcie), liczone w jednostkach R.
- Z tej tabeli liczone są skuteczność i maksymalny spadek rad.

### 3. Dashboard
- Lokalna strona serwowana przez mały serwer Pythona.
- Zawartość: werdykt i reżim na górze, wykres M15 z sygnałami, uzasadnienie, tabela ostatnich rad.
- Obok werdyktu zawsze: skuteczność historyczna tego typu sygnału, liczba transakcji, maksymalny spadek.
- Odświeżanie po zamknięciu każdej świecy M15.
- Stały napis, że to sygnały analityczne.

### 4. Powiadomienia
- Telegram (token bota i chat id w zmiennych środowiskowych).
- Wysyłka tylko przy zmianie werdyktu lub reżimu: poziomy i uzasadnienie.
- Praca w tle: Harmonogram zadań Windows uruchamia sprawdzenie co 15 minut, po zamknięciu świecy.
- E-mail jako późniejsze rozszerzenie.

## Przepływ danych

Harmonogram uruchamia cykl: pobranie zamkniętych świec i danych makro, zapis do SQLite, wyliczenie reżimu i sygnału, zapis werdyktu, rozstrzygnięcie otwartych werdyktów, powiadomienie przy zmianie, odświeżenie danych dla dashboardu.

## Obsługa błędów
- Brak odpowiedzi OANDA lub FRED: cykl kończy się bez nowego werdyktu, ostatni werdykt na dashboardzie jest oznaczony jako nieaktualny z czasem ostatniej aktualizacji.
- Brak danych makro: warstwa dzienna zwraca NEUTRALNY, a uzasadnienie to mówi. Nigdy nie zgaduje.
- Wszystkie sygnały liczone wyłącznie na zamkniętych świecach.
- Wyłącznie środowisko OANDA Practice.

## Walidacja
- Backtest na kilku latach danych z podziałem: okres do ustawiania reguł oraz okres kontrolny, którego nie używa się do strojenia.
- Testy jednostkowe wskaźników i reguł reżimu na małych, ręcznie policzonych przykładach.
- Śledzenie rad na żywo przez tabelę wyników. Po kilku miesiącach daje prawdziwą skuteczność.
- Kryterium sensu: przewaga po kosztach spreadu na okresie kontrolnym. Bez niej reguły są przepisywane, nie wdrażane.

## Założenia do potwierdzenia przy implementacji
- Próg SHORT RSI 60, okno uzbrojenia sygnału 10 świec, filtr spreadu 25% ATR i ryzyko 1% na transakcję to założenia robocze, do sprawdzenia backtestem.
- Dokładne instrumenty makro (indeks dolara) zależą od dostępności w OANDA i FRED.
- Wygaśnięcie werdyktu bez rozstrzygnięcia: domyślnie po 48 godzinach.

## Poza zakresem
Składanie zleceń, konto live, uczenie maszynowe, FinBERT, złoto fizyczne w PLN, aplikacja mobilna.
