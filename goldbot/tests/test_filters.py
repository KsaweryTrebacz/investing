from config import Config, Instrument
from cycle import Context, run_cycle
from oanda import demo_candles, demo_daily, demo_macro
from pipeline import prepare
from store import Store
from strategy import Params, add_signals

M15 = demo_candles(20000)
BASE = add_signals(M15, Params())


def fired(df):
    return df["signal"] != 0


def test_filters_only_remove_signals():
    for p in (Params(session=(7, 17)), Params(ema_align=True), Params(room_atr=2.0)):
        out = add_signals(M15, p)
        assert (fired(out) <= fired(BASE)).all() and fired(out).sum() < fired(BASE).sum(), p


def test_session_filter_hours():
    out = add_signals(M15, Params(session=(7, 17)))
    hours = out.loc[fired(out), "time"].dt.hour
    assert len(hours) and hours.between(7, 16).all()
    night = add_signals(M15, Params(session=(22, 2)))
    assert night.loc[fired(night), "time"].dt.hour.isin([22, 23, 0, 1]).all()


def test_ema_align_direction():
    out = add_signals(M15, Params(ema_align=True))
    c = out["mid_c"]
    e20, e50 = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    assert (e20[out["signal"] == 1] > e50[out["signal"] == 1]).all()
    assert (e20[out["signal"] == -1] < e50[out["signal"] == -1]).all()


def test_regime_can_be_disabled():
    d1 = demo_daily(M15)
    df = prepare(M15, d1, *demo_macro(d1), Params(use_regime=False))
    assert (df["signal"] == df["signal_raw"]).all()


def test_cycle_takes_strategy_from_instrument_config():
    cfg = Config()
    cfg.instruments = {"XAU_USD": Instrument(strategy={"session": [3, 3], "use_regime": False})}  # pusta sesja
    m15 = demo_candles(30000)
    d1 = demo_daily(m15)
    v = run_cycle(m15, d1, *demo_macro(d1), Store(), ctx=Context(cfg=cfg))["verdict"]
    assert v["signal_raw"] == 0 and v["verdict"] == "CZEKAJ"
