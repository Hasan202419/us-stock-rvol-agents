"""Skan fon thread — lock band bo‘lsa ikkinchi skan rad etiladi."""

from __future__ import annotations

import importlib
import threading
from unittest.mock import patch

import pytest


@pytest.fixture()
def bot_mod():
    return importlib.import_module("scripts.telegram_command_bot")


def test_start_scan_background_busy_lock(bot_mod, monkeypatch) -> None:
    lock = threading.Lock()
    lock.acquire()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:fake")
    with patch.object(bot_mod, "_send_html"):
        with patch.object(bot_mod, "_execute_scan_send_persist"):
            ok = bot_mod._start_scan_background("tok", "123", lock, run_all=False)
    assert ok is False
    lock.release()
