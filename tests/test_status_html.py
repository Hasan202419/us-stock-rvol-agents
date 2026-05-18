"""Telegram /status HTML — NameError regressiya."""

from __future__ import annotations

import importlib


def test_status_html_does_not_raise(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    mod = importlib.import_module("scripts.telegram_command_bot")
    html = mod._status_html()
    assert "Bot status" in html
    assert "Alpaca keys" in html
    assert "key_hint" not in html
