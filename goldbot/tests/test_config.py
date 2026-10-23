import json
import os

import pytest

from config import Config, load_config


def write(tmp_path, data):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_missing_file_gives_defaults(tmp_path):
    cfg = load_config(str(tmp_path / "brak.json"))
    assert cfg.path is None and cfg.account.capital is None and cfg.account.risk_per_trade == 0.005
    assert list(cfg.instruments) == ["XAU_USD"] and cfg.instruments["XAU_USD"].quote == "USD"
    assert cfg.instruments["XAU_USD"].costs.commission_per_unit is None


def test_full_file_is_parsed_and_comments_skipped(tmp_path):
    path = write(tmp_path, {
        "_opis": "komentarz",
        "account": {"currency": "PLN", "capital": 20000, "_uwaga": "x"},
        "fx_rates": {"USDPLN": {"rate": 4.0, "as_of": "2026-10-23", "source": "NBP"}},
        "instruments": {
            "XAU_USD": {"group": "metale", "costs": {"margin_rate": 0.05, "slippage_atr": 0.1}},
            "DE30_EUR": {"macro": False},
            "_szablon": {"group": "pomijany"},
        },
    })
    cfg = load_config(path)
    assert cfg.account.currency == "PLN" and cfg.account.capital == 20000
    assert set(cfg.instruments) == {"XAU_USD", "DE30_EUR"}
    assert cfg.instruments["XAU_USD"].costs.margin_rate == 0.05
    assert cfg.instruments["DE30_EUR"].quote == "EUR" and not cfg.instruments["DE30_EUR"].macro
    assert cfg.fx_rates["USDPLN"]["rate"] == 4.0


def test_unknown_field_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="nieznane pola"):
        load_config(write(tmp_path, {"account": {"kapital": 1}}))


def test_relative_paths_follow_config_file(tmp_path):
    cfg = load_config(write(tmp_path, {"positions_file": "pozycje.json"}))
    assert cfg.resolve_path(cfg.positions_file) == os.path.join(str(tmp_path), "pozycje.json")
    assert Config().resolve_path(None) is None


def test_unknown_instrument_has_no_macro_regime():
    i = Config().instrument("SPX500_USD")
    assert i.quote == "USD" and not i.macro


def test_example_files_are_valid():
    from config import HERE
    from events import load_csv_events
    from risk import load_positions
    cfg = load_config(os.path.join(HERE, "config.example.json"))
    assert list(cfg.instruments) == ["XAU_USD"] and cfg.account.risk_per_trade == 0.005
    assert cfg.instruments["XAU_USD"].costs.margin_rate is None and cfg.events["fred_releases"] == [10]
    assert load_positions(os.path.join(HERE, "positions.example.json"))["positions"] == []
    assert load_csv_events(os.path.join(HERE, "events.example.csv"), "2026-10-23") == []
