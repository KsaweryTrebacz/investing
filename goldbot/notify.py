"""Decyzje o zapisie i powiadomieniu oraz wysyłka przez Telegram."""
import os

import requests

from advisor import TRADE
from regime import REGIME_PL

DISCLAIMER = "Sygnał analityczny, nie porada inwestycyjna."


def should_store(prev, new) -> bool:
    """Zapisz werdykt, gdy to pierwszy, albo nowa świeca z werdyktem handlowym lub zmianą werdyktu,
    reżimu albo statusu decyzji."""
    if prev is None:
        return True
    if new["time"] == prev["time"]:
        return False
    key = lambda v: (v["verdict"], v["regime"], v.get("decision"))  # noqa: E731
    return new["verdict"] in TRADE or key(new) != key(prev)


def should_notify(prev, new) -> bool:
    """Powiadom o pierwszym werdykcie, nowym werdykcie handlowym lub zmianie reżimu."""
    if prev is None:
        return True
    if new["time"] == prev["time"]:
        return False
    return new["verdict"] in TRADE or new["regime"] != prev["regime"]


def format_message(v: dict) -> str:
    if v.get("report"):
        from report import render_telegram
        return render_telegram(v["report"])
    lines = [f"XAU/USD: {v['verdict']}", f"Reżim dzienny: {REGIME_PL[v['regime']]}"]
    if v["verdict"] in TRADE:
        lines.append(f"Wejście ok. {v['entry']:.2f}  SL {v['sl']:.2f}  TP {v['tp']:.2f}")
    lines += [v["reasoning"], f"Świeca M15 z {v['time']}", DISCLAIMER]
    return "\n".join(lines)


def telegram_sender():
    """Funkcja wysyłająca tekst na Telegram albo None, gdy brak konfiguracji."""
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return None

    def send(text: str):
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text}, timeout=15)
        r.raise_for_status()
    return send
