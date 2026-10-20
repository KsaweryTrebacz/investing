# Doradca XAU/USD

Program co 15 minut mówi, czy według reguł warto kupić, sprzedać, czy czekać ze złotem (CFD XAU/USD na OANDA).
Pokazuje werdykt na lokalnej stronie i wysyła powiadomienie na Telegram, gdy pojawia się sygnał albo zmienia się reżim.
Nie składa zleceń.

> Sygnały analityczne, nie porada inwestycyjna. Wyniki historyczne nie gwarantują przyszłych.

## Jak to działa

1. **Reżim dzienny.** Trzy składniki: trend złota (EMA 50 vs EMA 200), siła dolara (FRED `DTWEXBGS`) i realne rentowności USA (FRED `DFII10`).
   Co najmniej dwa punkty w jedną stronę dają reżim *sprzyja kupnie* albo *sprzyja sprzedaży*. Zmiana wymaga dwóch kolejnych dni.
   Brak danych makro daje reżim neutralny.
2. **Sygnał M15.** EMA 200, korekta RSI (40 / 60), przecięcie histogramu MACD. SL 1,5 ATR, TP 3 ATR. Sygnał przechodzi tylko zgodnie z reżimem.
3. **Werdykt** KUP / SPRZEDAJ / CZEKAJ z poziomami i uzasadnieniem. Każda rada jest zapisywana w SQLite i rozstrzygana po fakcie (TP, SL lub wygaśnięcie po 48 h).

## Konfiguracja

Python 3.12, potem w katalogu `goldbot`:

```
python -m pip install -r requirements-dev.txt
```

Zmienne środowiskowe użytkownika (np. `[Environment]::SetEnvironmentVariable("OANDA_TOKEN", "...", "User")`):

| Zmienna | Skąd |
|---|---|
| `OANDA_TOKEN` | OANDA, konto Practice: *Manage API Access* |
| `FRED_API_KEY` | darmowy klucz na fred.stlouisfed.org (*My Account, API Keys*) |
| `TELEGRAM_BOT_TOKEN` | bot założony przez @BotFather |
| `TELEGRAM_CHAT_ID` | id Twojego czatu z botem |

## Komendy

```
python main.py validate            # najpierw: czy reguły mają przewagę na okresie kontrolnym
python main.py cycle               # jeden cykl: werdykt, zapis, powiadomienie
python main.py dashboard           # http://localhost:8787
python -m pytest tests -q          # testy
```

Każda komenda przyjmuje `--demo` (dane syntetyczne, osobna baza `goldbot-demo.db`, bez Telegrama).

## Praca w tle

`install_task.ps1` rejestruje zadanie Harmonogramu Windows, które uruchamia `main.py cycle` co 15 minut.
Uruchom go ręcznie dopiero, gdy `validate` na prawdziwych danych pokaże sens strategii.
