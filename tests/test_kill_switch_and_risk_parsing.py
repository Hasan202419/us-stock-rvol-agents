import json
from pathlib import Path

import pytest

from agents.kill_switch import is_kill_switch_active, kill_switch_default_path, set_kill_switch


def test_kill_switch_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    p = kill_switch_default_path(tmp_path)
    assert p.parent.name == "state"
    set_kill_switch(True, "test halt", path=p)
    assert is_kill_switch_active(p) is True
    set_kill_switch(False, "clear", path=p)
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["halt"] is False


def test_dashboard_parse_flags_helper() -> None:
    blob = "[\"FOO\", \"BAR\"]"
    out = json.loads(blob)
    assert out == ["FOO", "BAR"]
