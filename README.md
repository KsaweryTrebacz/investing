# Doradca do złota (XAU/USD)

Lokalny program, który raz dziennie mówi, czy według modelu opłaca się teraz być w złocie, czy lepiej siedzieć w gotówce. Pokazuje poziom wejścia, stop i uzasadnienie po polsku. Nie składa zleceń, tylko podpowiada.

To nie jest porada inwestycyjna. Program jest zbudowany tak, żeby nie udawać pewności, której nie ma: rady KUP wydaje tylko wtedy, gdy model ma udowodnioną przewagę poza próbą, sprawdzaną co tydzień od nowa.

## Co jest w środku

Dwie warstwy, każda ma własne komendy:

1. **Model dzienny (główny).** Regresja logistyczna na 44 cechach z danych dziennych: zwroty 1-60 sesji, EMA, RSI, zmienność, dolar i realne rentowności, oraz kształt wykresu (korpus i cienie świec, serie, odległość od wybić 20/55 sesji, wyższe szczyty i niższe dołki, obsunięcie od szczytu roku, reżim zmienności, momentum 6 i 12 miesięcy, układ średnich, efektywność ruchu). Cel: czy złoto w 10 sesji urośnie więcej niż koszt spreadu. Model jest uczony walk-forward (pierwsze 5 lat tylko do nauki, przeuczanie co kwartał), więc każda prognoza w historii jest poza próbą.
2. **Sygnał M15 (stary).** Reguły EMA 200 / RSI / MACD. Nie był sprawdzony na prawdziwych danych M15 (wymaga OANDA). Zostaje w kodzie, nie jest zalecany.

### Tryb: w złocie albo w gotówce

Model ma dwa tryby: „long" (w złocie, gdy prawdopodobieństwo wzrostu przekracza próg, inaczej w gotówce) i „ls" (długa/krótka). Tryb, próg i rodzaj modelu zostały wybrane **wyłącznie po okresie strojenia** (prognozy do końca 2020). Lata 2021-2026 to okres kontrolny, który nie brał udziału w wyborze. Gra na spadki (tryb „ls") nie ma przewagi i jest wyłączona.

### Stop kroczący

Przy otwartej radzie KUP program wyjście podpowiada w dwóch sytuacjach: prognoza spada pod próg albo zamknięcie spada o 2 ATR poniżej najwyższego zamknięcia od wejścia (stop kroczący). Po stopie nowe wejście dopiero, gdy sygnał zgaśnie i wróci. Wielkość stopu jest wybierana z siatki (brak, 2, 3, 4 ATR) po Sharpe w okresie strojenia, tak samo jak próg. Sprawdzone alternatywy, odrzucone: filtr zmienności i skalowanie pozycji do zmienności (wynik zależy od parametru, sąsiedni szkodzi), dodatkowe rynki jako cechy (srebro, VIX, S&P 500, stopy nominalne, ropa, wolumen: obniżają Sharpe w okresie strojenia z 1,07 do 0,54).

### Bramka przewagi

Model „ma przewagę" tylko, gdy w **obu** okresach (strojenia i kontrolnym) strategia zarabia i ma lepszy Sharpe niż kup-i-trzymaj, a w okresie kontrolnym t-stat dziennych zwrotów > 1,65. Dobry wynik w jednym okresie to za mało. Gdy bramka nie przepuszcza, `daily` zawsze daje CZEKAJ i mówi dlaczego.

### Wynik walidacji z 2026-11-04 (prawdziwe dane, 2011-2026)

| w złocie albo w gotówce, stop kroczący 2 ATR | okres strojenia 2016-2020 | okres kontrolny 2021-2026 |
|---|---|---|
| Sharpe strategii | 1,15 | 1,33 |
| Sharpe kup-i-trzymaj | 0,71 | 0,65 |
| t-stat | 2,34 | 3,20 |
| zwrot strategii | +39% | +113% |
| zwrot kup-i-trzymaj | +53% | +102% |
| maks. obsunięcie | -6,6% | -13,9% |
| czas w rynku | 22% dni | 28% dni |

Bez stopu kroczącego (sam sygnał): Sharpe 1,07 / 0,95, obsunięcie -8,6% / -23,9%, zwrot +37% / +93%. Co to znaczy: w okresie kontrolnym model z stopem daje nieco więcej niż trzymanie złota, przy mniej niż 1/3 czasu w rynku i obsunięciu o połowę mniejszym. Słaby rok: 2021 (-7%). Zastrzeżenie: wyniki kontrolne nakładek ryzyka były widoczne, zanim ustalono kryterium wyboru (poprawa w strojeniu dla wszystkich sąsiednich parametrów), więc ten jeden wybór nie jest tak czysty jak wybór modelu. Najważniejsze cechy: odległość od dołka 20 sesji, odległość od szczytu 55 sesji, wzrost od dołka roku, czyli model lubi złoto po wybiciu w górę i unika go po załamaniu. Kierunku pojedynczego dnia model nie przewiduje (AUC ok. 0,5); przewaga bierze się z unikania złych okresów.

Historia: pierwsza wersja (gradient boosting, bez cech kształtu wykresu, tryb długa/krótka) nie miała przewagi i program mówił tylko CZEKAJ. Obecny wariant został wybrany eksperymentem z 18 kombinacji (horyzont, cechy, model), gdzie kryterium wyboru był wyłącznie okres strojenia.

Sprawdzone później i odrzucone (2026-11-04): pozycjonowanie spekulantów z raportów COT (CFTC), dzienny indeks ryzyka geopolitycznego GPR (Caldara i Iacoviello) i oczekiwana inflacja (FRED T10YIE). COT pogarsza okres strojenia (Sharpe 0,78). GPR, inflacja i wszystkie trzy razem poprawiają okres strojenia (1,37, 1,35, 1,48), ale pogarszają kontrolny (1,23, 1,06, 0,97 wobec 1,33) i zwiększają obsunięcie. Im więcej cech, tym lepiej w strojeniu i gorzej poza nim, czyli dopasowanie do szumu. Wniosek: na tym zbiorze danych okres strojenia przestał odróżniać poprawę od przypadku, więc dokładanie danych zostało zakończone. Wynik kontrolny obecnego modelu (Sharpe 1,33) należy traktować jako lekko zawyżony, bo decyzja „zostaw" też korzystała z tej wiedzy.

## Dane

Źródło wybiera się samo (`--source auto`):

- **free** (domyślnie, gdy nie ma `OANDA_TOKEN`): złoto z Yahoo Finance (kontrakt GC=F, 15 lat), indeks dolara DX-Y.NYB, realne rentowności DFII10 z FRED (CSV bez klucza). Prawdziwe notowania, zero kont. Spread przyjęty 0,50 USD (typowy dla OANDA).
- **oanda**: świece dzienne XAU/USD z bid/ask z konta OANDA Practice. Yahoo służy wtedy jako kontrola krzyżowa (ostrzeżenie przy rozjeździe cen > 2%).

Zabezpieczenia: walidacja świec (brakujące ceny, ask < bid, high < low, czas), odrzucenie świecy z sesji, która jeszcze trwa, świeżość danych (brak świecy z ostatniego dnia sesyjnego zamienia radę w CZEKAJ), makro starsze niż 10 dni traktowane jak brak, pamięć podręczna w `goldbot/cache/` na wypadek awarii sieci (z ostrzeżeniem w uzasadnieniu). Nic w kodzie nie składa zleceń; pilnuje tego test.

## Instalacja

Python 3.12.

```
cd goldbot
python -m pip install -r requirements-dev.txt
```

Zmienne środowiskowe (opcjonalne, jako zmienne użytkownika Windows):

```
OANDA_TOKEN          token API v20 z konta OANDA Practice (bez niego: Yahoo + FRED)
FRED_API_KEY         klucz FRED dla starej warstwy M15 (model dzienny go nie potrzebuje)
TELEGRAM_BOT_TOKEN   token bota od @BotFather
TELEGRAM_CHAT_ID     id czatu z botem
```

Według dokumentacji OANDA, API v20 nie działa dla kont prowadzonych przez OANDA TMS Brokers.

## Użycie

Z katalogu `goldbot`:

```
python main.py train              # walidacja walk-forward + uczenie; zapisuje model.joblib i model_report.json
python main.py daily              # werdykt dzienny: KUP / TRZYMAJ / ZAMKNIJ / CZEKAJ
python main.py dashboard          # http://localhost:8787
python -m pytest tests -q
```

Flagi `--source auto|free|oanda`, `--years 15`, `--offline` (tylko pamięć podręczna). Najpierw `train`, potem `daily`.

Werdykty: KUP (wejdź w złoto, podany poziom stopu kroczącego), TRZYMAJ (prognoza nadal nad progiem, stop kroczący podniesiony), ZAMKNIJ (prognoza spadła pod próg albo stop kroczący, wyjdź do gotówki), CZEKAJ (w gotówce). Rady lądują w `goldbot/goldbot.db` i są rozliczane po fakcie, z czego dashboard liczy skuteczność.

Stara warstwa M15: `python main.py cycle`, `python main.py validate`, oba z `--demo` na danych syntetycznych.

## Uruchamianie automatyczne

`install_daily_task.ps1` rejestruje w Harmonogramie zadań Windows `GoldAdvisorDaily` (wt-sob 01:30, po zamknięciu sesji) i `GoldAdvisorTrain` (sobota 08:00). Trzeba go uruchomić ręcznie:

```
powershell -ExecutionPolicy Bypass -File goldbot\install_daily_task.ps1
```

Usunięcie:

```
Unregister-ScheduledTask -TaskName GoldAdvisorDaily,GoldAdvisorTrain -Confirm:$false
```

## Pliki

```
goldbot/
  main.py            komendy (train, daily, dashboard, cycle, validate)
  sources.py         dane dzienne: Yahoo+FRED albo OANDA, cache, świeżość, kontrola krzyżowa
  features.py        cechy bazowe i cel prognozy
  patterns.py        cechy kształtu wykresu
  model.py           walk-forward, metryki, tryby, stop kroczący, bramka przewagi, zapis modelu
  daily_advisor.py   werdykt dzienny i rozliczanie rad
  daily_cycle.py     jeden cykl dzienny
  install_daily_task.ps1
  cycle.py, strategy.py, regime.py, advisor.py, resolve.py, backtest.py, validate.py, guards.py
                     stara warstwa M15 i wspólne zabezpieczenia
  indicators.py      EMA, RSI, MACD, ATR
  oanda.py           klient OANDA v20 (tylko odczyt) + dane demo
  macro.py           FRED z kluczem (warstwa M15)
  notify.py          Telegram
  store.py           SQLite (rady M15 i D1 w jednej tabeli, kolumna kind)
  dashboard.py       serwer dashboardu (web/index.html)
docs/superpowers/    specyfikacje i plany
```
