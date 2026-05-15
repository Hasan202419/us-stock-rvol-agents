#!/usr/bin/env python3
"""`.env` dagi GITHUB_TOKEN bilan `git push` (to'liq avtomat push/deploy zanjiri uchun)."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.bootstrap_env import ensure_env_file, load_project_env  # noqa: E402

_GITHUB_REMOTE_RE = re.compile(
    r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:)(?P<owner>[^/]+)/(?P<repo>[^/.]+)",
    re.IGNORECASE,
)


def _parse_remote(url: str) -> tuple[str, str] | None:
    url = (url or "").strip()
    m = _GITHUB_REMOTE_RE.match(url)
    if not m:
        return None
    return m.group("owner"), m.group("repo")


def _verify_token(token: str) -> bool:
    try:
        r = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20,
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


def _run_git(args: list[str], *, cwd: Path) -> int:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        print(proc.stdout.rstrip(), flush=True)
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr, flush=True)
    return int(proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Push to GitHub using GITHUB_TOKEN from .env")
    parser.add_argument("--branch", default="", help="Branch (default: current branch or main)")
    args = parser.parse_args()

    ensure_env_file(_PROJECT_ROOT)
    load_project_env(_PROJECT_ROOT)

    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token or token.lower() in {"your_token", "ghp_xxx", "changeme"}:
        print(
            "GITHUB_TOKEN .env da yo'q yoki namuna.\n"
            "1) https://github.com/settings/tokens → Generate new token (classic)\n"
            "2) Scope: repo\n"
            f"3) {_PROJECT_ROOT / '.env'} ichiga: GITHUB_TOKEN=ghp_...",
            file=sys.stderr,
        )
        return 1

    if not _verify_token(token):
        print(
            "GITHUB_TOKEN GitHub API da qabul qilinmadi (muddati tugagan yoki scope yetarli emas). "
            "Yangi token yarating: repo scope.",
            file=sys.stderr,
        )
        return 1

    proc = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    remote_url = (proc.stdout or "").strip()
    parsed = _parse_remote(remote_url)
    if not parsed:
        print(f"origin URL tushunarsiz: {remote_url}", file=sys.stderr)
        return 1
    owner, repo = parsed

    branch = (args.branch or "").strip()
    if not branch:
        proc_b = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        branch = (proc_b.stdout or "").strip() or "main"

    safe_token = quote(token, safe="")
    push_url = f"https://x-access-token:{safe_token}@github.com/{owner}/{repo}.git"

    print(f"git push → github.com/{owner}/{repo}.git ({branch})", flush=True)
    push = subprocess.run(
        ["git", "push", push_url, f"HEAD:{branch}"],
        cwd=str(_PROJECT_ROOT),
    )
    if push.returncode != 0:
        return int(push.returncode)

    # origin ni token siz qoldiramiz (xavfsizlik)
    _run_git(["remote", "set-url", "origin", f"https://github.com/{owner}/{repo}.git"], cwd=_PROJECT_ROOT)
    print("Push OK.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
