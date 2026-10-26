#!/bin/bash
# Pobiera publiczne notowania złota do badań (research.study, research.trend) do katalogu $1.
# BaseMax: M15 2004-2025 (jedna cena). FX-Data: ticki Dukascopy 2011-2018 z bid/ask (~130 MB na rok).
set -e
D=${1:?podaj katalog docelowy}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$D/dukascopy_m15"
curl -sf --retry 3 -o "$D/XAU_15m_data.csv" https://raw.githubusercontent.com/BaseMax/XAUUSD-LSTM/main/XAU_15m_data.csv
for y in 2011 2012 2013 2014 2015 2016 2017 2018; do
  W=$(mktemp -d)
  git clone -q --depth 1 --branch XAUUSD-$y https://github.com/FX-Data/FX-Data-XAUUSD-DS "$W/raw"
  python3 -I "$HERE/dukascopy_ticks.py" "$W/raw" "$D/dukascopy_m15/XAUUSD_$y.csv"
  rm -rf "$W"
done
