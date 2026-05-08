"""bootstrap_env: izohdan kalit chiqarish."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agents.bootstrap_env import (
    load_project_env,
    promote_master_plan_comment_env,
    resolve_render_service_id_from_api,
)


def test_promote_deepseek_from_comment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """# DEEPSEEK_API_KEY=sk-from-comment-xxxxxxxx
DEEPSEEK_API_KEY=
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    promote_master_plan_comment_env(env_path)

    assert os.environ.get("DEEPSEEK_API_KEY") == "sk-from-comment-xxxxxxxx"


def test_promote_does_not_override_existing_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# DEEPSEEK_API_KEY=sk-from-comment\nDEEPSEEK_API_KEY=\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "already-set")
    promote_master_plan_comment_env(env_path)
    assert os.environ.get("DEEPSEEK_API_KEY") == "already-set"


def test_resolve_render_service_id_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    monkeypatch.setenv("RENDER_API_KEY", "rnd_x")
    monkeypatch.setenv("RENDER_SERVICE_NAME", "my-app")

    class R:
        status_code = 200

        def json(self) -> list[dict[str, object]]:
            return [
                {"id": "srv-other", "name": "x", "type": "web"},
                {"id": "srv-want", "name": "my-app", "type": "web"},
            ]

    monkeypatch.setattr("requests.get", lambda *a, **k: R())

    resolve_render_service_id_from_api()
    assert os.environ.get("RENDER_SERVICE_ID") == "srv-want"


def test_drop_invalid_render_id_then_resolve(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "RENDER_API_KEY=rnd_x\nRENDER_SERVICE_ID=tea-not-a-web-service\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RENDER_SERVICE_NAME", "my-app")

    class R:
        status_code = 200

        def json(self) -> list[dict[str, object]]:
            return [{"id": "srv-want", "name": "my-app", "type": "web"}]

    monkeypatch.setattr("requests.get", lambda *a, **k: R())

    load_project_env(tmp_path)
    assert os.environ.get("RENDER_SERVICE_ID") == "srv-want"


def test_resolve_render_single_web_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    monkeypatch.setenv("RENDER_API_KEY", "rnd_x")
    monkeypatch.delenv("RENDER_SERVICE_NAME", raising=False)

    class R:
        status_code = 200

        def json(self) -> list[dict[str, object]]:
            return [{"id": "srv-only", "name": "other-name", "type": "web"}]

    monkeypatch.setattr("requests.get", lambda *a, **k: R())

    resolve_render_service_id_from_api()
    assert os.environ.get("RENDER_SERVICE_ID") == "srv-only"


def test_promote_openai_from_comment_when_active_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text(
        "# OPENAI_API_KEY=sk-from-comment-12345678901234567890\nOPENAI_API_KEY=\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    load_project_env(tmp_path)
    assert os.environ.get("OPENAI_API_KEY") == "sk-from-comment-12345678901234567890"


def test_dotenv_overrides_empty_system_placeholder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows User env kalitlari bo'sh satr bo‘lsa, .env shu ustidan yozilishi kerak."""

    monkeypatch.delenv("_TEST_FROM_DOTENV_", raising=False)
    (tmp_path / ".env").write_text("_TEST_FROM_DOTENV_=from-file-value\n", encoding="utf-8")
    monkeypatch.setenv("_TEST_FROM_DOTENV_", "")
    load_project_env(tmp_path)
    assert os.environ.get("_TEST_FROM_DOTENV_") == "from-file-value"


def test_massive_api_key_maps_to_polygon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("MASSIVE_API_KEY=poly-from-massive\nPOLYGON_API_KEY=\n", encoding="utf-8")
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    load_project_env(tmp_path)
    assert os.environ.get("POLYGON_API_KEY") == "poly-from-massive"


def test_alpaca_legacy_aliases_map_to_current_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text(
        "ALPACA_API_KEY_ID=key-legacy\nALPACA_API_SECRET_KEY=secret-legacy\nALPACA_API_KEY=\nALPACA_SECRET_KEY=\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    load_project_env(tmp_path)
    assert os.environ.get("ALPACA_API_KEY") == "key-legacy"
    assert os.environ.get("ALPACA_SECRET_KEY") == "secret-legacy"
