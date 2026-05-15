"""scan_pipeline telegram defaults va telegram_command_bot yordamchilar regression."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import requests

from agents.scan_presets import SCAN_PRESETS
from agents.scan_pipeline import (
    SidebarControls,
    _email_or_telegram_top_n_for_alerts,
    _env_int_bounded,
    _safe_float,
    fetch_universe_for_scan,
    telegram_default_controls,
)

_BOT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "telegram_command_bot.py"


def _load_command_bot_script():
    spec = importlib.util.spec_from_file_location("_telegram_command_bot_under_test", _BOT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    ("raw_env", "default", "expected"),
    [
        ("", 10, 10),
        ("not_number", 7, 7),
        ("3", 10, 3),
        ("999", 5, 20),  # clamp hi
        ("-80", 5, 2),  # clamp lo when hi=20 lo=2
    ],
)
def test_env_int_bounded(
    monkeypatch: pytest.MonkeyPatch,
    raw_env: str,
    default: int,
    expected: int,
) -> None:
    key = "__TEST_BOUNDED_INT_TEMP__"
    if raw_env:
        monkeypatch.setenv(key, raw_env)
    else:
        monkeypatch.delenv(key, raising=False)
    assert _env_int_bounded(key, default, lo=2, hi=20) == expected


def test_safe_float_handles_bad_values() -> None:
    assert _safe_float(12.5) == 12.5
    assert _safe_float(None) == 0.0
    assert _safe_float("abc") == 0.0
    assert _safe_float("3", default=1.0) == 3.0


def test_email_or_telegram_top_n(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMAIL_ALERT_TOP_N", raising=False)
    monkeypatch.setenv("TELEGRAM_ALERT_TOP_N", "zzz")
    assert _email_or_telegram_top_n_for_alerts() == 3
    monkeypatch.setenv("TELEGRAM_ALERT_TOP_N", "7")
    assert _email_or_telegram_top_n_for_alerts() == 7
    monkeypatch.setenv("EMAIL_ALERT_TOP_N", "ninety")
    assert _email_or_telegram_top_n_for_alerts() == 3
    monkeypatch.setenv("EMAIL_ALERT_TOP_N", "12")
    assert _email_or_telegram_top_n_for_alerts() == 12


def test_telegram_default_controls_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_MAX_SYMBOLS", "bogus")
    monkeypatch.setenv("SCAN_MAX_WORKERS", "oops")
    monkeypatch.setenv("TELEGRAM_SCAN_PRESET", "DOES_NOT_EXIST")
    c = telegram_default_controls()
    assert c.max_symbols >= 0
    assert 2 <= c.max_workers <= 20
    assert c.preset_name == "Explorer"


def test_fetch_universe_for_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, bool]] = []

    class DummyUniverseAgent:
        def fetch_symbols(self, limit: int = 100, *, use_finviz_elite: bool = False) -> list[str]:
            calls.append((limit, use_finviz_elite))
            return ["AAA", "BBB"]

    monkeypatch.setattr("agents.scan_pipeline.UniverseAgent", DummyUniverseAgent)

    ctrls = SidebarControls(
        desk_label="t",
        max_symbols=50,
        preset_name="Balanced",
        rvol_thresholds=dict(SCAN_PRESETS["Balanced"]),
        max_workers=4,
        finviz_csv_universe=False,
    )
    out = fetch_universe_for_scan(ctrls)
    assert out == ["AAA", "BBB"]
    assert calls == [(50, False)]


def test_fetch_universe_for_scan_uses_builtin_when_agent_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    class EmptyUniverseAgent:
        def fetch_symbols(self, limit: int = 100, *, use_finviz_elite: bool = False) -> list[str]:
            return []

    monkeypatch.setattr("agents.scan_pipeline.UniverseAgent", EmptyUniverseAgent)
    ctrls = SidebarControls(
        desk_label="t",
        max_symbols=5,
        preset_name="Balanced",
        rvol_thresholds=dict(SCAN_PRESETS["Balanced"]),
        max_workers=4,
        finviz_csv_universe=False,
    )
    out = fetch_universe_for_scan(ctrls)
    assert len(out) == 5
    assert out[0] == "AAPL"


def test_parse_auto_push_at() -> None:
    bot = _load_command_bot_script()
    assert bot._parse_auto_push_at("18:30") == (18, 30)
    assert bot._parse_auto_push_at("9:05") == (9, 5)
    assert bot._parse_auto_push_at("") is None
    assert bot._parse_auto_push_at("25:00") is None
    assert bot._parse_auto_push_at("12:99") is None


def test_telegram_command_from_text_basic() -> None:
    bot = _load_command_bot_script()
    assert bot._command_from_text("/help")[0] == "help"
    assert bot._command_from_text("/help")[1] == ""
    assert bot._command_from_text("/scan")[0] == "scan"
    assert bot._command_from_text("/Scan@some_bot leftovers")[1] == "leftovers"
    assert bot._command_from_text("/scan foo bar")[1] == "foo bar"


def test_escape_html_escapes_tags() -> None:
    bot = _load_command_bot_script()
    assert "&lt;br&gt;" in bot._escape_html("<br>")


def test_register_bot_menu_commands_calls_setmycommands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []

    def fake_post(url: str, *, json=None, timeout=None, **kwargs: object) -> object:
        calls.append((url, json))

        class R:
            ok = True
            status_code = 200
            text = '{"ok":true}'

            def json(self) -> dict[str, bool]:
                return {"ok": True}

        return R()

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.delenv("TELEGRAM_SKIP_SET_MY_COMMANDS", raising=False)
    bot = _load_command_bot_script()
    bot._register_bot_menu_commands("TESTTOKEN")
    assert len(calls) == 1
    assert "setMyCommands" in calls[0][0]
    body = calls[0][1]
    assert isinstance(body, dict) and "commands" in body
    cmds = body["commands"]
    assert isinstance(cmds, list) and cmds[0]["command"] == "start"
    assert any(c.get("command") == "scan" for c in cmds)


def test_parse_allowed_chat_ids_supergroup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TELEGRAM_ALLOWED_CHAT_IDS",
        "-1001234567890, 987654321, spam",
    )
    bot = _load_command_bot_script()
    s = bot._parse_allowed_chat_ids()
    assert s == {"-1001234567890", "987654321"}


def test_effective_allowed_bot_id_only_opens_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bot token oldidagi raqamni chat ID deb qo‘yish — filtrni bekor qilamiz."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "7839339510:AA_testfake")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "7839339510")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "7839339510")
    bot = _load_command_bot_script()
    assert bot._effective_allowed_chat_ids("7839339510:AA_testfake") is None


def test_effective_allowed_keeps_real_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "7839339510:AA_testfake")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111222333")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "444555666")
    bot = _load_command_bot_script()
    got = bot._effective_allowed_chat_ids("7839339510:AA_testfake")
    assert got == {"111222333", "444555666"}
