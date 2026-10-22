# investing

Doradca do złota (XAU/USD). Co 15 minut liczy sygnał i wypisuje KUP, SPRZEDAJ albo CZEKAJ, z poziomami SL/TP i krótkim uzasadnieniem. Nie składa zleceń, tylko podpowiada.

To nie jest porada inwestycyjna. Strategia nie była jeszcze sprawdzona na prawdziwych danych.

## Jak liczy

Dwa poziomy:

- Dzienny reżim. Trzy składniki: trend złota (EMA 50 vs EMA 200), indeks dolara (FRED `DTWEXBGS`) i realne rentowności 10Y (FRED `DFII10`). Każdy daje +1, 0 albo -1. Suma >= 2 to "sprzyja kupnie", <= -2 to "sprzyja sprzedaży", reszta to "neutralny". Zmiana musi się utrzymać 2 dni. Bez danych z FRED reżim jest zawsze neutralny.
- Sygnał M15. Cena nad EMA 200, RSI schodzi pod 40 i wraca, potem histogram MACD przechodzi na plus (dla SHORT odwrotnie, próg RSI 60). SL = 1,5 ATR, TP = 3 ATR. Sygnał przechodzi tylko, jeśli zgadza się z reżimem. Przy spreadzie powyżej 25% ATR jest pomijany.

Rady lądują w SQLite (`goldbot/goldbot.db`). Otwarte rady są potem rozliczane: TP, SL albo wygaśnięcie po 48 h. Z tego liczy się skuteczność na dashboardzie.

Telegram dostaje wiadomość przy nowym KUP/SPRZEDAJ albo przy zmianie reżimu.

## Zabezpieczenia

- Dane są sprawdzane przed liczeniem: za mało świec, brakujące lub niedodatnie ceny, ask < bid, high < low, czas, który się cofa albo powtarza. Wtedy cykl kończy się błędem i nic nie zapisuje.
- Jeśli ostatnia zamknięta świeca M15 jest starsza niż 30 minut, rada handlowa zamienia się w CZEKAJ, a uzasadnienie mówi, że dane są nieaktualne.
- Dopóki poprzednia rada KUP/SPRZEDAJ jest otwarta, nowej nie ma.
- Gdy rady rozliczone danego dnia (UTC) dały łącznie -2R lub gorzej, nowe rady handlowe są wstrzymane do końca dnia.
- Dane z FRED starsze niż 10 dni są traktowane jak brak, więc reżim jest neutralny.
- W kodzie nie ma niczego, co składa zlecenia. Pilnuje tego test.

## Instalacja

Python 3.12.

```
cd goldbot
python -m pip install -r requirements-dev.txt
```

Zmienne środowiskowe (najlepiej jako zmienne użytkownika Windows):

```
OANDA_TOKEN          token API v20 z konta OANDA Practice
FRED_API_KEY         darmowy klucz z fred.stlouisfed.org
TELEGRAM_BOT_TOKEN   token bota od @BotFather (opcjonalnie)
TELEGRAM_CHAT_ID     id czatu z botem (opcjonalnie)
```

Obsługiwane jest tylko konto Practice. Token generuje się w panelu konta w *Manage API Access*. Według dokumentacji OANDA, API v20 nie działa dla kont prowadzonych przez OANDA TMS Brokers.

## Użycie

Z katalogu `goldbot`:

```
python main.py validate --years 3   # backtest: 70% danych do strojenia, 30% kontrolne
python main.py cycle                # jeden cykl: werdykt, zapis do bazy, Telegram
python main.py dashboard            # http://localhost:8787
python -m pytest tests -q
```

`cycle`, `dashboard` i `validate` mają flagę `--demo`. Używa wtedy losowych danych i osobnej bazy `goldbot-demo.db`, bez Telegrama. Służy tylko do sprawdzenia, czy program działa.

Najpierw `validate` na prawdziwych danych. Jeśli wynik na okresie kontrolnym (`out_of_sample`) jest na minusie, nie ma sensu odpalać reszty.

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
  main.py         komendy
  cycle.py        jeden cykl doradcy
  regime.py       reżim dzienny
  strategy.py     sygnał M15
  indicators.py   EMA, RSI, MACD, ATR
  advisor.py      werdykt i uzasadnienie
  resolve.py      rozliczanie rad
  backtest.py     backtest
  validate.py     podział na okres do strojenia i kontrolny
  oanda.py        pobieranie świec z OANDA + dane demo  guards.py       zabezpieczenia
  macro.py        dane z FRED
  notify.py       Telegram
  store.py        SQLite
  dashboard.py    serwer dashboardu (web/index.html)
docs/superpowers/ specyfikacja i plan
```
