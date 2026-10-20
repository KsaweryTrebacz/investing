# 🪙 AURUM Invest — Nowoczesna Platforma Inwestycyjna w Złoto

Kompletny, nowoczesny interfejs internetowy platformy fintech dedykowanej inwestowaniu w **złoto fizyczne** (sztabki mennicze, monety bulionowe) oraz **złoto cyfrowe / ułamkowe**.

Aplikacja została zaprojektowana w estetyce dark-mode klasy premium z akcentami szczotkowanego złota, dynamicznymi wykresami rynkowymi i pełną interaktywnością.

---

## 🚀 Jak uruchomić aplikację?

Aplikacja nie wymaga instalacji żadnych dodatkowych pakietów (`npm`, `python`, etc.) — działa natychmiast w każdej nowoczesnej przeglądarce (Chrome, Edge, Firefox).

### Opcja 1 (Najszybsza — 1 kliknięcie)
Kliknij dwukrotnie plik **`start.bat`** lub bezpośrednio otwórz plik **`index.html`** w przeglądarce.

### Opcja 2 (PowerShell)
W terminalu PowerShell w tym folderze wpisz:
```powershell
.\start.ps1
```

---

## ✨ Główne Moduły i Funkcjonalności

### 1. 📊 Notowania & Panel Rynku (Dashboard)
- **4 Karty Wskaźników KPI**:
  - Aktualna cena kruszcu spot z londyńskiej giełdy (LBMA) oraz NBP.
  - Wycena bieżąca Twojego portfela w czasie rzeczywistym.
  - Całkowity zysk/strata (PLN oraz stopa zwrotu %).
  - Dostępne saldo gotówkowe na natychmiastowe zakupy.
- **Interaktywny Wykres Notowań Złota (Chart.js)**:
  - Złoty gradient z poświatą (*glow effect*) i płynną linią kursową.
  - Interwały czasowe: **24h, 7D, 1M, 1R, 5L, MAX**.
  - Przełącznik jednostek: **1 uncja trojańska (oz t = 31.1g), 1 gram (g), 1 kilogram (kg)**.
  - Wskaźniki dziennego minimum i maksimum.
- **Szybkie Zlecenie (Terminal)**:
  - Zakup złota ułamkowego już od **50 PLN** z automatycznym przeliczaniem masy kruszcu w gramach i uncjach.
  - Natychmiastowy wybór składowania: **Skarbiec Klasy IX** (depozyt bezpłatny) lub **Ubezpieczona przesyłka kurierska**.
  - Szybkie przyciski kwot: `+200 zł`, `+500 zł`, `+1000 zł`, `+5000 zł`.

### 2. 💼 Mój Portfel & Skarbiec
- **Wykres Alokacji (Doughnut Chart)**: Podział posiadanego kruszcu na sztabki mennicze, monety bulionowe oraz złoto skarbcowe.
- **Tabela Aktywów**:
  - Szczegóły każdej pozycji: numer seryjny, mennica (Valcambi, C.Hafner, Perth Mint), próba (999.9 lub 916.6), gramatura, średnia cena zakupu, obecna wartość rynkowa oraz stopa zwrotu.
  - **Przycisk "Sprzedaj"**: Odkup natychmiastowy 24/7 z minimalnym spreadem i natychmiastowym zasileniem salda gotówkowego.

### 3. 🪙 Sklep Menniczy (Katalog Fizyczny)
- Pełen asortyment certyfikowanych produktów menniczych z akredytacją LBMA:
  - **Sztabka C.Hafner 1 g** (w blistrze CertiPack)
  - **Sztabka Valcambi Suisse 1 oz (31.1 g)** (światowy bestseller)
  - **Sztabka PAMP Suisse Fortuna 100 g**
  - **Sztabka Odlewana Valcambi 1 kg** (niska marża mennicza)
  - **Moneta Krugerrand 1 oz** (Republika Południowej Afryki)
  - **Moneta Wiedeńscy Filharmonicy 1 oz** (Austria, próba 999.9)
  - **Moneta Kanadyjski Liść Klonowy 1 oz** (Kanada, super próba 999.99)
- Filtrowanie produktów (*Wszystkie*, *Sztabki*, *Monety*).
- Modal zamówienia z wyborem liczby sztuk i formy odbioru.

### 4. 📈 Plan Oszczędzania (Kalkulator Złotej Emerytury)
- Symulacja długoterminowego budowania majątku w złocie:
  - Wpłata początkowa (suwak `0` – `100 000 zł`).
  - Miesięczna dopłata (suwak `100` – `10 000 zł/mies.`).
  - Horyzont czasowy (od `1` do `25 lat`).
  - Średnioroczna stopa zwrotu (domyślnie `8.5%` w oparciu o historyczne średnie złota).
- **Bezpośrednie porównanie z lokatą bankową (3.5%) oraz trzymaniem samej gotówki** (spadek siły nabywczej).
- Wykres prognozy kapitału i wyliczenie zgromadzonej masy złota (gramy i uncje).

### 5. 📜 Dziennik Transakcji & Certyfikaty
- Rejestr wszystkich operacji (kupno, sprzedaż, wpłaty BLIK/karta).
- Generowanie i pobieranie **indywidualnego certyfikatu transakcji** (format pliku tekstowego z unikalnym identyfikatorem i skrótem kryptograficznym).
- Eksport historii transakcji do pliku **CSV**.

### 6. ⚡ Silnik Symulacji Na Żywo (Live Market Ticks)
- Opcja włączenia/wyłączenia w nagłówku (**Live: ON/OFF**).
- Co kilka sekund generuje realistyczne mikro-wahania kursu spot z zielonym lub czerwonym błyskiem i aktualizacją wykresów oraz wartości portfela.

### 7. 💱 Obsługa Wielowalutowości (PLN / USD / EUR)
- Błyskawiczne przeliczanie wszystkich wartości, cen produktów i wykresów na wybraną walutę jednym kliknięciem.

### 8. 💾 Zapis Danych w Przeglądarce (`localStorage`)
- Wszystkie transakcje, zakupy, sprzedaże i doładowania konta są trwale zapamiętywane.
- W stopce dostępny jest przycisk **"Zresetuj dane demo"**, przywracający stan początkowy.

---

## 📁 Struktura Projektu

```
c:\moje\GitHub\investing\
├── index.html            # Główny szkielet HTML z semantycznym podziałem na zakładki i modale
├── start.bat             # Skrypt uruchamiający aplikację jednym kliknięciem w Windows
├── start.ps1             # Skrypt uruchamiający w PowerShell
├── README.md             # Dokumentacja projektu
├── css\
│   └── styles.css        # Złote gradienty, efekty glassmorphism, niestandardowe animacje
└── js\
    ├── data.js           # Katalog menniczy, dane historyczne wykresów, portfel początkowy
    ├── state.js          # Zarządzanie stanem (AppState), subskrypcje zdarzeń, persistencja
    ├── chart-manager.js  # Konfiguracja wykresów Chart.js (notowania, alokacja, kalkulator)
    └── app.js            # Kontroler główny UI, modale, obsługa formularzy, toasty
```

---

## 🛠️ Zastosowane Technologie

- **HTML5 & CSS3** z nowoczesną architekturą komponentów.
- **Tailwind CSS v3** (CDN) — responsywność (Mobile / Tablet / Desktop), system siatek i klas utility.
- **Chart.js** — interaktywne wykresy liniowe i kołowe.
- **Lucide Icons** — nowoczesny pakiet ikon wektorowych.
- **Google Fonts** (Inter, Plus Jakarta Sans, Cinzel).
- **Vanilla Modern JS (ES6+)** — zero ciężkich frameworków, wysoka wydajność, brak konieczności kompilacji.

---

## 🔮 Możliwe Kierunki Rozwoju

1. Podłączenie produkcyjnego API do notowań kruszców na żywo (np. GoldAPI.io lub NBP API).
2. Integracja bramki płatności online (np. PayU, Stripe lub Przelewy24).
3. Backend z bazą danych (np. Node.js Express / NestJS / FastAPI) oraz autoryzacją użytkowników JWT.
4. Generowanie certyfikatów autentyczności w plikach PDF z kodami QR i pieczęcią elektroniczną.
