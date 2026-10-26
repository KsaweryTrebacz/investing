import pandas as pd

from research.datasets import (daily_from_m15, hourly_spread_profile, load_dukascopy, load_mt_csv, nfp_offsets,
                               server_to_utc, with_spread)


def test_load_both_metatrader_formats(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("Date;Open;High;Low;Close;Volume\n2021.03.05 15:30;1700;1710;1695;1705;12\n", encoding="utf-8")
    b = tmp_path / "b.csv"
    b.write_text("Date,open,high,low,close,tick_volume\n2021-03-05 15:30:00,170000.0,171000.0,169500.0,170500.0,12\n",
                 encoding="utf-8")
    for p in (a, b):
        df = load_mt_csv(str(p))
        assert df.iloc[0].to_dict() == {"time": pd.Timestamp("2021-03-05 15:30"), "open": 1700.0, "high": 1710.0,
                                        "low": 1695.0, "close": 1705.0, "volume": 12}


def spiky_month_starts(year, server_hour="15:30"):
    """Świece M15 w piątki 1-7 dnia miesiąca, z dużym zakresem o `server_hour` (jak po NFP)."""
    rows = []
    for d in pd.date_range(f"{year}-01-01", f"{year}-12-31"):
        if d.weekday() == 4 and d.day <= 7:
            for t in pd.date_range(d + pd.Timedelta(hours=12), d + pd.Timedelta(hours=19, minutes=45), freq="15min"):
                big = t.strftime("%H:%M") == server_hour
                rows.append({"time": t, "open": 100.0, "high": 110.0 if big else 101.0, "low": 99.0, "close": 100.0,
                             "volume": 1})
    return pd.DataFrame(rows)


def test_nfp_offset_and_conversion_follow_new_york_dst():
    df = pd.concat([spiky_month_starts(2020), spiky_month_starts(2021), spiky_month_starts(2022, "16:30")])
    off = nfp_offsets(df)
    assert off[2020] == 7 and off[2021] == 7  # 2022 (8) jest wygładzony medianą tylko na brzegu
    utc = server_to_utc(pd.DataFrame({"time": pd.to_datetime(["2021-03-05 15:30", "2021-07-02 15:30"]),
                                      "close": [1.0, 2.0]}), pd.Series({2021: 7}))
    assert [t.strftime("%H:%M") for t in utc["time"]] == ["13:30", "12:30"]  # zima EST, lato EDT


def test_spread_model_and_bid_ask():
    duk = pd.DataFrame({"time": pd.to_datetime(["2015-01-05 10:00", "2015-01-05 22:00"], utc=True),
                        "bid_c": [1000.0, 1000.0], "ask_c": [1000.2, 1000.6]})
    prof = hourly_spread_profile(duk)
    assert abs(prof[10] - 0.0002) < 1e-12 and abs(prof[22] - 0.0006) < 1e-12
    one = pd.DataFrame({"time": pd.to_datetime(["2020-01-06 10:00", "2020-01-06 05:00"], utc=True),
                        "open": [2000.0] * 2, "high": [2001.0] * 2, "low": [1999.0] * 2, "close": [2000.0] * 2,
                        "volume": [5, 6]})
    out = with_spread(one, prof, mult=2)
    assert out["bid_c"].tolist() == [2000.0, 2000.0]
    assert abs(out["ask_c"].iloc[0] - 2000.8) < 1e-9          # 2 x 0,02% ceny
    assert abs(out["ask_c"].iloc[1] - 2001.6) < 1e-9          # godzina bez danych: mediana profilu (0,04%)


def test_daily_candles_start_at_17_new_york():
    t = pd.date_range("2021-01-10 21:45", "2021-01-11 22:15", freq="15min", tz="UTC")  # niedziela -> poniedziałek
    m15 = pd.DataFrame({"time": t, "volume": 1.0, **{f"{s}_{k}": 1.0 for s in ("bid", "ask") for k in "ohlc"}})
    d1 = daily_from_m15(m15)
    assert [x.isoformat() for x in d1["time"]] == ["2021-01-09T22:00:00+00:00", "2021-01-10T22:00:00+00:00",
                                                   "2021-01-11T22:00:00+00:00"]
    assert d1["volume"].tolist() == [1.0, 96.0, 2.0]   # 21:45; 22:00..21:45 (96 świec); 22:00, 22:15


def test_load_dukascopy_scales_prices(tmp_path):
    (tmp_path / "XAUUSD_2015.csv").write_text(
        "time,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,volume\n"
        "2015-01-05 10:00:00+00:00,12.0,12.1,11.9,12.05,12.004,12.104,11.904,12.054,30\n", encoding="utf-8")
    d = load_dukascopy(str(tmp_path))
    assert d["bid_c"].iloc[0] == 1205.0 and round(d["ask_c"].iloc[0] - d["bid_c"].iloc[0], 6) == 0.4
