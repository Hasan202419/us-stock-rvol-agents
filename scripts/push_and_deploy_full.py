#!/usr/bin/env python3
"""Bitta buyruq: pytest (ixtiyoriy) → git add/commit → GITHUB_TOKEN push → Render deploy."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _run(cmd: list[str], *, cwd: Path, label: str) -> int:
    print(f"\n=== {label} ===", flush=True)
    proc = subprocess.run(cmd, cwd=str(cwd))
    return int(proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--message", default="chore: sync from workstation")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--no-deploy", action="store_true")
    args = parser.parse_args()

    root = _PROJECT_ROOT
    py = sys.executable

    if not args.skip_tests:
        rc = _run(
            [py, "-m", "pytest", "tests/test_telegram_amt_buy.py", "tests/test_amt_vwap_scalp.py", "-q"],
            cwd=root,
            label="pytest",
        )
        if rc != 0:
            return rc

    _run(["git", "add", "-A"], cwd=root, label="git add")
    commit = subprocess.run(
        ["git", "commit", "-m", args.message],
        cwd=str(root),
    )
    if commit.returncode not in (0, 1):
        return int(commit.returncode)

    push_script = root / "scripts" / "git_push_from_env.py"
    rc = _run([py, str(push_script)], cwd=root, label="git push (GITHUB_TOKEN)")
    if rc != 0:
        return rc

    if not args.no_deploy:
        for script, label in (
            ("scripts/trigger_render_deploy.py", "Render deploy"),
            ("scripts/ensure_render_telegram_worker.py", "Render worker env"),
        ):
            path = root / script
            if path.is_file():
                rc = _run([py, str(path)], cwd=root, label=label)
                if rc != 0:
                    return rc

    print("\nTAYYOR: GitHub push + Render deploy tugadi.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
