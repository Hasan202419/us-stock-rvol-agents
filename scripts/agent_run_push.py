#!/usr/bin/env python3
"""Push + deploy natijani logs/agent_run_push.txt ga yozadi."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "agent_run_push.txt"


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def run(cmd: list[str], label: str) -> int:
        lines.append(f"\n=== {label} ===\n")
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        lines.append(p.stdout or "")
        if p.stderr:
            lines.append(p.stderr)
        lines.append(f"exit={p.returncode}\n")
        return int(p.returncode)

    rc = run(
        [sys.executable, "-m", "pytest", "tests/test_market_shield.py", "-q", "--tb=short"],
        "pytest market_shield",
    )
    if rc != 0:
        LOG.write_text("".join(lines), encoding="utf-8")
        return rc

    run(["git", "status", "-sb"], "git status")
    run(["git", "add", "-A"], "git add")
    p = subprocess.run(
        ["git", "commit", "-m", "feat: Market Shield SPY QQQ VIX regime gates for long BUY"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    lines.append(p.stdout or "")
    lines.append(p.stderr or "")
    lines.append(f"commit exit={p.returncode}\n")

    rc = run([sys.executable, str(ROOT / "scripts" / "git_push_from_env.py")], "git push")
    if rc == 0:
        run([sys.executable, str(ROOT / "scripts" / "trigger_render_deploy.py")], "render deploy")
        run([sys.executable, str(ROOT / "scripts" / "ensure_render_telegram_worker.py")], "render env")

    run(["git", "rev-parse", "HEAD"], "HEAD")
    run(["git", "status", "-sb"], "git status after")
    LOG.write_text("".join(lines), encoding="utf-8")
    print(LOG.read_text(encoding="utf-8"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
