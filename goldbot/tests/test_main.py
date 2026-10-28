import main


def test_cycle_and_validate_demo_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(main, "HERE", str(tmp_path))
    monkeypatch.setenv("GOLDBOT_CONFIG", str(tmp_path / "brak.json"))
    assert main.main(["cycle", "--demo"]) == 0
    out = capsys.readouterr().out
    assert "STATUS:" in out and "8. Status:" in out and "Brak config.json" in out
    assert (tmp_path / "goldbot-demo.db").exists()
    assert main.main(["validate", "--demo"]) == 0
    out = capsys.readouterr().out
    assert "out_of_sample" in out and "BRAK DANYCH o kosztach" in out


def test_db_path_per_instrument():
    assert main.db_path(False).endswith("goldbot.db")
    assert main.db_path(True, "SPX500_USD").endswith("goldbot-demo-SPX500_USD.db")


def test_trend_mode_validate_and_cycle_demo(tmp_path, monkeypatch, capsys):
    import json
    (tmp_path / "config.json").write_text(json.dumps({
        "account": {"currency": "USD", "capital": 10000},
        "instruments": {"XAU_USD": {"mode": "trend_d1", "costs": {"margin_rate": 0.02}}}}), encoding="utf-8")
    monkeypatch.setattr(main, "HERE", str(tmp_path))
    monkeypatch.setenv("GOLDBOT_CONFIG", str(tmp_path / "config.json"))
    assert main.main(["validate", "--demo"]) == 0
    out = capsys.readouterr().out
    assert "strategia trendowa D1" in out and "kup_i_trzymaj_1x" in out and "BRAK DANYCH o finansowaniu" in out
    assert main.main(["cycle", "--demo"]) == 0
    assert "świeca D1 od" in capsys.readouterr().out
