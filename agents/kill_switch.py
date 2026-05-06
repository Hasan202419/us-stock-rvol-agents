"""Diskdagi halt bayrog'i — kunlik zarar va qo‘lda to‘xtatish."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def kill_switch_default_path(repo_root: str | Path | None = None) -> Path:
    root = Path(repo_root or os.getenv("PROJECT_ROOT", "."))
    override = os.getenv("KILL_SWITCH_PATH")
    return Path(override) if override else root / "state" / "kill_switch.json"


def is_kill_switch_active(path: Path | None = None) -> bool:
    p = kill_switch_default_path() if path is None else path
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not data.get("halt"):
        return False
    expiry = data.get("expires_after_utc")
    if expiry:
        try:
            normalized = expiry.replace("Z", "+00:00")
            exp_dt = datetime.fromisoformat(normalized)
            exp_utc = exp_dt if exp_dt.tzinfo else exp_dt.replace(tzinfo=UTC)
            if datetime.now(UTC) > exp_utc:
                return False
        except (TypeError, ValueError):
            pass
    return True


def set_kill_switch(
    halt: bool,
    reason: str = "",
    *,
    path: Path | None = None,
    expires_after_utc: str | None = None,
) -> None:
    p = kill_switch_default_path() if path is None else path
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "halt": bool(halt),
        "reason": reason,
        "updated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_after_utc": expires_after_utc,
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
