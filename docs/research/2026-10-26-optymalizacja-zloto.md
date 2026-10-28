# Optymalizacja i testy skuteczności na publicznych danych złota

Data: 2026-10-26. Wyniki surowe: `docs/research/wyniki/` (study.json, trend.json, edges.json, leverage.json, sizing.json, grid_full_period.csv.gz).
Kod: `goldbot/research/` (datasets.py, study.py, trend.py, edges.py, leverage.py, sizing.py, download.sh).

## Wniosek

Strategia doradcy (M15: EMA 200, powrót RSI z korekty, przecięcie MACD, reżim dzienny) **nie ma przewagi na złocie**. Bez kosztów jej średni wynik to około 0R na transakcję, czyli tyle, ile losowe wejścia. Po realnym spreadzie i kosztach traci średnio 0,16R na transakcję, w 15 z 17 lat. Optymalizacja 2880 wariantów nie pomogła: wybór parametrów na latach poprzednich dał poza próbą −0,17R na transakcję. Żaden wariant, także wybrany ze znajomością przyszłości, nie ma istotnie dodatniego wyniku.

Najlepszy wynik przy kontroli ryzyka utraty kapitału daje więc **niezawieranie transakcji z tej strategii**. Inne rodziny strategii, testowane bez ograniczeń ryzyka (punkt 8), też nie mają trwałej przewagi. Jedynym stałym źródłem zysku w danych był długoterminowy wzrost ceny złota, a przy CFD większość tego zysku zjada finansowanie. Program dostał bramkę walidacji: dopóki strategia nie jest oznaczona jako zwalidowana, sygnał daje najwyżej status „obserwacja”.

## Dane

| Źródło | Okres | Opis |
|---|---|---|
| BaseMax/XAUUSD-LSTM (GitHub) | 2004-06 – 2025-03 | M15, jedna cena (bid), czas serwera brokera przeliczony na UTC; 476 666 świec |
| FX-Data/FX-Data-XAUUSD-DS (GitHub) | 2011-05 – 2018-06 | ticki Dukascopy z bid i ask, zagregowane do M15; 161 643 świece; niezależne źródło |

- ejtraderLabs/historical-data (M15 2012–2022) i parshant65 (M1 2020–2025) okazały się tym samym strumieniem notowań co BaseMax (różnica cen 0,000), więc nie są osobnymi testami.
- Opis parshant65 podaje czas UTC, ale skok zmienności po publikacji NFP wypada w danych o 15:30 przez cały rok. To czas serwera (Nowy Jork + 7 h, w latach 2004–2011 + 6 h). Przesunięcie wyznaczono z danych dla każdego roku i sprawdzono na dniach NFP latem i zimą.
- Dane po 21.03.2025 mają luki do 80 dni i zostały pominięte.
- Spread dla danych jednocenowych pochodzi z prawdziwych bid/ask Dukascopy: mediana od 2,2 punktu bazowego ceny w dzień do 3,1 pb wieczorem w UTC (około 0,4–0,6 USD przy cenie 2000 USD). Dodatkowo test z podwójnym spreadem.

## Metoda

- Koszty poza spreadem (założenia badania, nie stawki brokera): prowizja 0, finansowanie LONG −5% rocznie, SHORT −1% rocznie, poślizg na SL 0,1 ATR. SL przy luce cenowej po cenie otwarcia. Wygaśnięcie po 48 h jak na żywo.
- Reżim dzienny tylko z trendu D1. W danych publicznych brak dziennych serii FRED (dolar, realne rentowności), więc składnika makro nie dało się sprawdzić.
- Siatka: RSI 35/40/45, okno 5/10/20 świec, sesja (cała doba albo 7–17 UTC), zgodność EMA 20/50 (tak/nie), zapas do szczytu lub dołka (0 albo 2 ATR), reżim (tak/nie), SL 1/1,5/2/3 ATR, TP 1/1,5/2/3/4 ATR. Razem 2880 wariantów.
- Walk-forward: dla każdego roku 2008–2024 wariant wybierany wyłącznie na 3 poprzednich latach. Kryterium to statystyka t średniego R, minimum 30 transakcji, a gdy żaden wariant nie ma dodatniego wyniku, rok jest bez transakcji. Wynik liczony jest na tym roku, poza próbą.
- Ryzyko: Monte Carlo (10 000 losowań ze zwracaniem transakcji poza próbą) w horyzoncie 4 i 12 miesięcy, przy ryzyku 0,5%, 1% i 2% na transakcję.
- Odniesienie: 100 serii losowych wejść (losowy moment i kierunek) z tymi samymi wyjściami i kosztami.

## Wyniki

### 1. Strategia domyślna, lata 2008–2024

| Dane | Transakcje | Trafność | Średnio R | t | Wynik przy 0,5% | Największy spadek |
|---|---|---|---|---|---|---|
| BaseMax (model spreadu) | 1450 | 30,5% | −0,157 | −4,28 | −69% | −71% |
| Dukascopy 2011–2018 (prawdziwy spread) | 424 | 31,4% | −0,131 | −1,90 | −25% | −30% |

Strata jest w 15 z 17 lat. Jedyne lata na plusie to 2012 (+2,7R) i 2015 (+0,1R).

### 2. Optymalizacja walk-forward (2880 wariantów)

| Wariant | Transakcje | Trafność | Średnio R | t | Wynik przy 0,5% | Największy spadek |
|---|---|---|---|---|---|---|
| Pełna siatka, wybór co roku | 693 | 34,9% | −0,172 | −3,70 | −46% | −48% |
| Tylko SL/TP, sygnał domyślny | 176 | 44,3% | −0,160 | −2,11 | −13% | −14% |
| Najlepszy wariant ze znajomością przyszłości | 40 | 50,0% | +0,197 | 0,98 | +3,9% | −3,3% |

Wybierane parametry zmieniały się co roku, bez stałego wzorca: raz z reżimem, raz bez, sesja raz włączona, raz nie, SL od 1,5 do 3 ATR. To typowy obraz dopasowania do szumu. Wariant, który program wybrałby dziś (okno 2022–2024: +0,21R, t = 1,87), na Dukascopy 2011–2018 daje −0,155R, a na BaseMax w tym samym okresie −0,104R.

### 3. Wszystkie warianty na całym okresie 2004–2025

Ze 2880 wariantów tylko 16 (0,6%) ma dodatni średni wynik i żaden nie ma t > 2 (najwyższe t = 0,66). 2432 warianty (84%) są istotnie stratne (t < −2). Najwyższa trafność to 78,8%, przy SL 3 ATR i TP 1 ATR, a średnio daje +0,04R, czyli trafność nie przekłada się na zysk.

### 4. Sygnał bez kosztów (zerowy spread, bez poślizgu i finansowania)

| Wariant | Transakcje | Średnio R | t |
|---|---|---|---|
| Domyślna | 2321 | +0,005 | 0,18 |
| Domyślna bez reżimu | 6096 | +0,006 | 0,31 |
| SL 3 / TP 3 ATR | 1958 | +0,020 | 0,89 |

Sygnał nie przewiduje kierunku ceny. Cały wynik to koszty.

### 5. Losowe wejścia

Przy 1757 losowych sygnałach na serię średni wynik w 100 seriach to −0,178R, a 90% serii mieści się między −0,237R i −0,123R. Strategia domyślna (−0,170R) i wynik walk-forward (−0,172R) leżą w środku tego przedziału.

### 6. Ryzyko utraty kapitału (Monte Carlo, wynik walk-forward, około 41 transakcji rocznie)

| Ryzyko na transakcję | Horyzont | P(strata) | Mediana | 5% najgorszych | P(spadek ≥ 10%) | P(spadek ≥ 20%) |
|---|---|---|---|---|---|---|
| 0,5% | 4 mies. | 71% | −1,3% | −4,7% | 0% | 0% |
| 1% | 4 mies. | 72% | −2,7% | −9,2% | 3% | 0% |
| 2% | 4 mies. | 72% | −5,4% | −17,8% | 51% | 2% |
| 0,5% | 12 mies. | 82% | −3,6% | −9,4% | 6% | 0% |
| 1% | 12 mies. | 83% | −7,2% | −18,0% | 59% | 4% |
| 2% | 12 mies. | 84% | −14,3% | −33,1% | 96% | 56% |

Przy ujemnej wartości oczekiwanej większe ryzyko na transakcję nie zwiększa szansy zysku, tylko przyspiesza utratę kapitału. Limit 0,5% ze specyfikacji to tu najważniejsze zabezpieczenie.

### 7. Inna rodzina strategii: trend na świecach dziennych (research/trend.py)

| Wariant | Transakcje | Średnio R | t | Wynik przy 0,5% |
|---|---|---|---|---|
| Walk-forward, LONG i SHORT (54 warianty Donchiana) | 69 | +0,077 | 0,47 | +2,5% |
| Walk-forward, tylko LONG | 47 | +0,208 | 0,90 | +4,9% |
| Klasyczny 55/20 dni, stop 3 ATR, tylko LONG | 40 | +0,145 | 0,74 | +2,9% |
| Klasyczny 55/20 dni, LONG i SHORT | 76 | −0,093 | −0,64 | −3,6% |
| Kup i trzymaj złoto (bez dźwigni) | – | – | – | +206%, największy spadek −45% |

Trend w wersji tylko LONG jest na plusie, ale bez istotności statystycznej (t < 1) i przy 0,5% ryzyka daje kilka procent w 17 lat. Odzwierciedla raczej wzrost ceny złota w tym okresie niż przewagę reguły. Nie wdrażam jej jako strategii doradcy.

### 8. Inne rodziny strategii bez ograniczeń ryzyka (research/edges.py)

Pozycja 1x wartości nominalnej, bez stopów i bez limitu ryzyka. Spread z cen bid/ask, finansowanie za każdy rollover (LONG −5%, SHORT −1% rocznie). Na danych jednocenowych pominięto godziny 20–22 UTC: w przerwie dziennej spread rośnie do 15 pb, a cena bid najpierw spada, potem odbija, co na wykresie wygląda jak zysk, którego nie da się zrealizować. Sprawdzono to na cenie środkowej Dukascopy.

| Rodzina | Warianty | Walk-forward BaseMax 2008–2024 (łącznie, t) | Walk-forward Dukascopy 2015–2018 |
|---|---|---|---|
| Sesja (pozycja od h1 do h2 UTC, LONG albo SHORT) | 438 | −51%, t −1,58 | +9%, t 0,59 |
| Momentum (zmiana ceny z 5–250 dni) | 12 | −29%, t −0,28 | −21% |
| Cena względem średniej 20–200 dni | 8 | −45%, t −0,94 | −6% |
| Powrót do średniej RSI(2) | 6 | od −9% do −38% | −12% |
| Wybicie z zakresu 01–07 UTC | 2 | +1%, t 0,27 | +31%, t 1,46 |
| Wszystkie rodziny razem | 466 | −9%, t 0,11 | +18%, t 0,97 |
| Kup i trzymaj (CFD z finansowaniem) | – | +35%, największy spadek −56% | −9% |

Stabilność w czasie, strategie stałe (bez doboru parametrów):

| Strategia | 2004–2010 | 2011–2017 | 2018–2025 |
|---|---|---|---|
| SHORT 07–15 UTC (godziny Londynu) | −4% (t 0,1) | **+78% (t 2,1)**, Dukascopy +72% (t 2,0) | **−44% (t −2,0)** |
| LONG 23–07 UTC (sesja azjatycka) | +9% (t 0,7) | +0% (t 0,1) | −20% (t −1,4) |

Słabość złota w godzinach Londynu w latach 2011–2017 widać na obu źródłach. Opiera się jednak głównie na bessie z lat 2013 (+47%) i 2015 (+23%), a od 2018 roku strategia traci. To nie jest trwała przewaga.

Strategie dzienne a koszt finansowania (BaseMax 2008–2024, roczne tempo wzrostu):

| Finansowanie LONG | Kup i trzymaj | Momentum 120 dni, LONG albo bez pozycji | Średnia 200 dni, LONG albo bez pozycji |
|---|---|---|---|
| −5% | +1,8% (spadek −56%) | +2,6% (−37%) | +1,6% (−39%) |
| −2,5% | +4,4% (−50%) | +4,3% (−34%) | +3,2% (−34%) |
| 0% | +7,0% (−45%) | +6,0% (−32%) | +4,9% (−32%) |

Filtry trendu nie dają wyższego zwrotu niż samo trzymanie złota, tylko mniejsze spadki. Przy CFD koszt finansowania zjada większość zysku. Bez ograniczeń ryzyka najwyższy zwrot w badanym okresie dawało więc trzymanie złota bez dźwigni i bez finansowania (np. fizyczne złoto albo fundusz), a nie strategia transakcyjna. Dźwignia mnoży zarówno ten zwrot, jak i spadki (−45% bez dźwigni).

### 9. Dźwignia CFD 1:50 (research/leverage.py)

Symulacja rachunku: pozycja = dźwignia x kapitał, depozyt 2% wartości (1:50), likwidacja przez brokera, gdy kapitał spadnie poniżej 50% depozytu. Likwidację sprawdzano na najgorszej cenie dnia albo transakcji, przy luce po cenie otwarcia. Finansowanie liczone od całej wartości pozycji, kapitał nie spada poniżej zera, po likwidacji strategia wchodzi ponownie pozostałym kapitałem. Przy pełnej dźwigni 50:1 likwidacja następuje już po ruchu ceny o około 1%. Okna 4-miesięczne zaczynają się co miesiąc w latach 2008–2024 (około 200 okien).

| Strategia | Dźwignia | Kapitał końcowy 2008–2024 (start = 1) | Okna 4 mies.: mediana | P(strata) | P(+80%) | P(−50%) | P(wyzerowanie) |
|---|---|---|---|---|---|---|---|
| Kup i trzymaj | 1x | 1,61 | +1% | 45% | 0% | 0% | 0% |
| Kup i trzymaj | 2x | 2,22 (spadek −94%) | +3% | 45% | 0% | 0% | 0% |
| Kup i trzymaj | 5x | 0,01 (wyzerowany 11.2015) | +5% | 45% | 3% | 8% | 0% |
| Kup i trzymaj | 20x | 0,007 (wyzerowany 09.2008) | −52% | 64% | 26% | 52% | 14% |
| Kup i trzymaj | 50x | 0,007 (wyzerowany 08.2008) | −79% | 75% | 17% | 64% | 35% |
| Momentum 120 dni, LONG albo bez pozycji | 5x | 2,00 (spadek −89%) | +2% | 47% | 2% | 3% | 0% |
| Momentum 120 dni, LONG albo bez pozycji | 50x | 0,006 (wyzerowany 01.2009) | −73% | 74% | 18% | 60% | 18% |
| SHORT 07–15 UTC (Londyn) | 50x | 0,008 (wyzerowany 01.2008) | −99% | 90% | 7% | 88% | 57% |
| Strategia doradcy M15 | 1x | 0,68 | −1% | 71% | 0% | 0% | 0% |
| Strategia doradcy M15 | 50x | 0,01 (wyzerowany 10.2008) | −49% | 87% | 4% | 49% | 1% |

Pełne wyniki dla dźwigni 1, 2, 5, 10, 20 i 50: `docs/research/wyniki/leverage.json`.

- Przy dźwigni od około 5x każda strategia, także trzymanie rosnącego złota, w latach 2008–2024 traci prawie cały kapitał. Wystarcza do tego jedno silne tąpnięcie (2008, 2013) i finansowanie liczone od całej wartości pozycji.
- Najwyższy kapitał końcowy dało trzymanie złota przy 2x (2,2 raza w 17 lat), przy spadku po drodze −94%. Powyżej tej wielkości wynik długoterminowy spada, bo zmienność i koszt finansowania rosną razem z dźwignią szybciej niż zysk.
- W horyzoncie 4 miesięcy duża dźwignia działa jak loteria. Przy 20x trzymanie złota dało +80% w 26% okien, ale w 52% okien stratę ponad połowy kapitału i w 14% wyzerowanie rachunku. Przy 50x mediana to −79%.
- W UE limit dźwigni na złocie dla klienta detalicznego to 1:20 (ESMA). Dźwignia 1:50 oznacza rachunek profesjonalny albo brokera spoza tych zasad.

### 10. Optymalna dźwignia (research/sizing.py)

Kryterium: największy kapitał końcowy, czyli maksymalny wzrost geometryczny (Kelly), bez kary za spadki. Rachunek przeliczany codziennie: ekspozycja = dźwignia × kapitał, depozyt 2% (1:50), likwidacja przy 50% depozytu, spread od zmian wielkości, finansowanie od całej wartości. Lata 2008–2024. Każde okno liczone od świeżego rachunku.

Teoria zgadza się z symulacją. Dla trzymania złota (średni zwrot 6,6% rocznie, zmienność 16,8%) optimum Kelly'ego μ/σ² wynosi 1,05× przy finansowaniu −5%, 1,94× przy −2,5% i 2,82× przy 0%. Najlepsza stała dźwignia w symulacji to odpowiednio 1×, 2× i 3×.

Najlepsza strategia do lewarowania to momentum 120 dni (LONG albo bez pozycji). Sposoby doboru dźwigni (kapitał końcowy, start = 1):

| Sposób doboru dźwigni | Finansowanie −5% | −2,5% | 0% |
|---|---|---|---|
| Najlepsza stała dźwignia ze znajomością przyszłości | 2× → 1,77 | 3× → 3,38 | 4× → 8,18 |
| Walk-forward: stała dźwignia wybierana co roku na 3 latach wstecz | 0,64 | 0,75 | 1,23 |
| Walk-forward: docelowa zmienność wybierana co roku | 2,13 (spadek −75%) | 3,97 | 9,67 |
| Kelly kroczący (estymacja z 2 lat), pełny / połowa | 0,02 / 0,48 | 0,03 / 0,83 | 0,05 / 1,68 |
| **Stała docelowa zmienność wybrana na 2008–2015, test na 2016–2024** | **50% → 1,98** | **50% → 3,85** | **75% → 9,11** |
| Kup i trzymaj bez dźwigni, dla porównania | 1,35 | 2,07 | 3,16 |

Stała docelowa zmienność, momentum 120 dni, finansowanie −5% (2008–2024, okna 4-miesięczne z lat 2016–2024):

| Docelowa zmienność | Kapitał końcowy | Największy spadek | Dźwignia średnia / maks. | 4 mies.: mediana | P(+80%) | P(−50%) |
|---|---|---|---|---|---|---|
| 10% | 1,70 | −26% | 0,8 / 2,2 | +0,8% | 0% | 0% |
| 20% | 2,52 | −48% | 1,5 / 4,5 | +1,4% | 0% | 0% |
| 30% | 3,23 | −65% | 2,3 / 6,7 | +1,8% | 0% | 0% |
| **50%** | **3,46** | −86% | 3,8 / 11,2 | +2,2% | 3% | 0% |
| 75% | 1,64 | −97% | 5,7 / 16,9 | +1,6% | 7% | 6% |
| 100% | 0,30 | −100% | 7,6 / 22,5 | 0,0% | 10% | 12% |
| 150% | 0,00 | −100% | 11,4 / 33,7 | −2,9% | 14% | 23% |

- **Optimum:** dźwignia dopasowywana do zmienności, średnio około 4× (chwilowo do 11×), czyli daleko poniżej dostępnych 50×. To samo optimum (50%) wychodzi w obu połowach danych, więc jest stabilne. Powyżej niego kapitał końcowy szybko spada, a od około 11× średnio rachunek się zeruje.
- **Dobór dźwigni co roku na podstawie ostatnich lat szkodzi.** Wybiera dużą dźwignię po dobrych latach i oddaje zysk w następnych (2012: −41%, 2021: −40%). Kelly z historycznych średnich też zawodzi, bo błąd estymacji średniej jest za duży.
- **Optimum oznacza ogromne spadki** (−86% przy 50%). Cel 30% daje 93% kapitału końcowego optimum przy spadku −65%, a cel 20% daje 73% przy spadku −48%.
- **Zysk pochodzi głównie z hossy złota** (2009–2011, 2019–2024). Sam filtr momentum nie jest istotny statystycznie (t ≈ 1–2), więc wynik zakłada, że złoto dalej będzie wyraźnie trendować. Strategia doradcy M15 i krótka pozycja w godzinach Londynu mają ujemną wartość oczekiwaną, więc ich optymalna dźwignia to 0.

## Zmiany w programie

- `strategy_validated` w konfiguracji instrumentu (domyślnie `false`): sygnał M15 daje najwyżej „obserwację”, a plan jest pokazany jako wstrzymany, z odnośnikiem do tego raportu. Zmienić na `true` można dopiero, gdy `python main.py validate` na danych Twojego brokera da dodatni wynik na okresie kontrolnym po kosztach i przy rozsądnej liczbie transakcji.
- Filtry jakości (sesja, EMA 20/50, zapas do szczytu lub dołka, wyłączenie reżimu) są dostępne w sekcji `strategy` konfiguracji, domyślnie wyłączone. Żaden nie dał poprawy poza próbą.
- Parametry domyślne strategii bez zmian: żaden wariant nie był lepszy w sposób powtarzalny.
- Strategia z punktu 10 (momentum 120 dni, docelowa zmienność 50%) jest wbudowana jako tryb `trend_d1` (`goldbot/momentum.py`, symulacja wspólna z `research/sizing.py`).
- Dźwignia: raport pokazuje użytą dźwignię, wolny depozyt i cenę likwidacji przez brokera. Brak wolnego depozytu albo SL dalej niż poziom likwidacji blokuje radę. Przy ryzyku 0,5% na transakcję pozycja zwykle ma dźwignię kilka do 1, a likwidacja wypada kilkadziesiąt procent od ceny wejścia.

## Ograniczenia

- Składnik makro reżimu (dolar, realne rentowności z FRED) nie był testowany: brak tych danych w źródłach dostępnych z tego środowiska.
- Główne źródło to notowania jednego brokera z modelowanym spreadem. Niezależne źródło (Dukascopy) pokrywa tylko lata 2011–2018.
- Koszty poza spreadem są założeniami. Wynik bez kosztów (punkt 4) pokazuje, że wniosek od nich nie zależy.
- Nie badano innych rynków ani interwałów niż M15 i D1.

## Jak odtworzyć

```
cd goldbot
research/download.sh ../dane                 # około 1 GB transferu, kilkanaście minut
python -m research.study --broker ../dane/XAU_15m_data.csv --dukascopy ../dane/dukascopy_m15 --out ../wyniki
python -m research.trend --broker ../dane/XAU_15m_data.csv --dukascopy ../dane/dukascopy_m15 --out ../wyniki
python -m research.edges --broker ../dane/XAU_15m_data.csv --dukascopy ../dane/dukascopy_m15 --out ../wyniki
python -m research.leverage --broker ../dane/XAU_15m_data.csv --dukascopy ../dane/dukascopy_m15 --out ../wyniki
python -m research.sizing --broker ../dane/XAU_15m_data.csv --dukascopy ../dane/dukascopy_m15 --out ../wyniki
```

Pełna siatka liczy się 10–15 minut na 4 rdzeniach.
