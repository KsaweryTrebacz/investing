# Doradca do złota (XAU/USD)

Lokalny program, który raz dziennie mówi, czy według modelu warto złoto kupić, sprzedać, trzymać, czy czekać. Pokazuje poziom wejścia, stop i uzasadnienie po polsku. Nie składa zleceń, tylko podpowiada.

To nie jest porada inwestycyjna. Program jest zbudowany tak, żeby nie udawać pewności, której nie ma: rady handlowe KUP/SPRZEDAJ wydaje tylko wtedy, gdy model ma udowodnioną przewagę poza próbą. Dziś jej **nie ma** (patrz niżej), więc program mówi CZEKAJ i pokazuje prognozę tylko informacyjnie.

## Co jest w środku

Dwie warstwy, każda ma własne komendy:

1. **Model dzienny (nowy, główny).** Gradient boosting (scikit-learn) na ok. 18 cechach z danych dziennych: zwroty 1-60 sesji, odległość od EMA 50/200, RSI, zmienność, pozycja w zakresie roku, zmiany indeksu dolara i realnych rentowności 10Y, składniki reżimu. Cel: czy złoto w 10 sesji urośnie więcej niż koszt spreadu. Model jest uczony walk-forward (okno rozszerzające, pierwsze 5 lat tylko do nauki, przeuczanie co kwartał), więc każda prognoza w historii jest poza próbą. Próg rady jest wybierany wyłącznie na prognozach do końca 2020, a lata 2021-2026 to okres kontrolny.
2. **Sygnał M15 (stary).** Reguły EMA 200 / RSI / MACD z reżimem dziennym. Nie był sprawdzony na prawdziwych danych M15 (wymaga OANDA). Zostaje w kodzie, ale nie jest zalecany.

### Bramka przewagi

Model „ma przewagę" tylko, gdy w **obu** okresach (strojenia i kontrolnym) AUC > 0,52, Sharpe > 0 i zwrot > 0, a w okresie kontrolnym t-stat dziennych zwrotów > 1,65. Dobry wynik w jednym okresie to za mało: może być hossą złota, nie umiejętnością modelu. Gdy bramka nie przepuszcza, `daily` zawsze daje CZEKAJ i mówi dlaczego.

### Wynik walidacji z 2026-11-04 (prawdziwe dane, 2011-2026)

| | okres strojenia 2016-2020 | okres kontrolny 2021-2026 |
|---|---|---|
| AUC | 0,465 | 0,539 |
| Sharpe po kosztach | -0,03 | 0,23 |
| t-stat | -0,05 | 0,55 |
| zwrot strategii | -1,2% | +21,5% |
| kup i trzymaj | +53,0% | +108,1% |

Same reguły reżimu (bez ML) są równie słabe: Sharpe 0,02 i 0,13. Wniosek: na tych cechach kierunek złota w horyzoncie 10 sesji nie jest przewidywalny w sposób, na którym można zarabiać. Program to mówi i nie wydaje rad handlowych. Komenda `train` liczy to od nowa na świeżych danych, więc jeśli kiedyś przewaga się pojawi, bramka się otworzy sama.

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
python main.py daily              # werdykt dzienny: KUP / SPRZEDAJ / TRZYMAJ / ZAMKNIJ / CZEKAJ
python main.py dashboard          # http://localhost:8787
python -m pytest tests -q
```

Flagi `--source auto|free|oanda`, `--years 15`, `--offline` (tylko pamięć podręczna). Najpierw `train`, potem `daily`. Rady dzienne lądują w `goldbot/goldbot.db` i są rozliczane po fakcie (stop albo koniec horyzontu 10 sesji), z czego dashboard liczy skuteczność.

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
  features.py        cechy przyczynowe i cel prognozy
  model.py           walk-forward, metryki, bramka przewagi, zapis modelu
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
