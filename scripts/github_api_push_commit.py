#!/usr/bin/env python3
"""GITHUB_TOKEN bilan Git Data API orqali commit + push (git CLI push ishlamasa)."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.bootstrap_env import ensure_env_file, load_project_env  # noqa: E402

API = "https://api.github.com"
OWNER = "Hasan202419"
REPO = "us-stock-rvol-agents"
DEFAULT_BRANCH = "main"

# Market Shield + bog‘liq fayllar (loyiha ildizidan nisbiy yo‘l).
DEFAULT_PATHS: tuple[str, ...] = (
    "agents/bootstrap_env.py",
    "agents/market_shield.py",
    "agents/scan_pipeline.py",
    "agents/risk_manager_agent.py",
    "agents/chatgpt_analyst_agent.py",
    "agents/telegram_framework_html.py",
    "scripts/telegram_command_bot.py",
    "scripts/ensure_render_telegram_worker.py",
    "scripts/push_and_deploy_full.py",
    "scripts/agent_run_push.py",
    "scripts/github_api_push_commit.py",
    "tests/test_market_shield.py",
    "tests/test_bootstrap_env.py",
    "pine/market_shield_filter.pine",
    ".env.example",
    "README.md",
    "PUSH_NOW.bat",
)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_ref(token: str, branch: str) -> dict[str, Any]:
    r = requests.get(f"{API}/repos/{OWNER}/{REPO}/git/ref/heads/{branch}", headers=_headers(token), timeout=30)
    r.raise_for_status()
    return r.json()


def _get_commit(token: str, sha: str) -> dict[str, Any]:
    r = requests.get(f"{API}/repos/{OWNER}/{REPO}/git/commits/{sha}", headers=_headers(token), timeout=30)
    r.raise_for_status()
    return r.json()


def _create_blob(token: str, content: str) -> str:
    r = requests.post(
        f"{API}/repos/{OWNER}/{REPO}/git/blobs",
        headers=_headers(token),
        json={"content": content, "encoding": "utf-8"},
        timeout=60,
    )
    r.raise_for_status()
    return str(r.json()["sha"])


def _create_tree(token: str, base_tree: str, entries: list[dict[str, str]]) -> str:
    r = requests.post(
        f"{API}/repos/{OWNER}/{REPO}/git/trees",
        headers=_headers(token),
        json={"base_tree": base_tree, "tree": entries},
        timeout=60,
    )
    r.raise_for_status()
    return str(r.json()["sha"])


def _create_commit(token: str, tree: str, parent: str, message: str) -> str:
    r = requests.post(
        f"{API}/repos/{OWNER}/{REPO}/git/commits",
        headers=_headers(token),
        json={"message": message, "tree": tree, "parents": [parent]},
        timeout=30,
    )
    r.raise_for_status()
    return str(r.json()["sha"])


def _update_ref(token: str, branch: str, sha: str) -> None:
    r = requests.patch(
        f"{API}/repos/{OWNER}/{REPO}/git/refs/heads/{branch}",
        headers=_headers(token),
        json={"sha": sha, "force": False},
        timeout=30,
    )
    r.raise_for_status()


def push_files(
    token: str,
    paths: list[str],
    *,
    message: str,
    branch: str = DEFAULT_BRANCH,
) -> str:
    ref = _get_ref(token, branch)
    parent_sha = str(ref["object"]["sha"])
    parent_commit = _get_commit(token, parent_sha)
    base_tree = str(parent_commit["tree"]["sha"])

    tree_entries: list[dict[str, str]] = []
    for rel in paths:
        fp = _ROOT / rel.replace("/", os.sep)
        if not fp.is_file():
            print(f"skip (yo'q): {rel}", flush=True)
            continue
        text = fp.read_text(encoding="utf-8")
        blob = _create_blob(token, text)
        tree_entries.append({"path": rel.replace("\\", "/"), "mode": "100644", "type": "blob", "sha": blob})
        print(f"blob ok: {rel}", flush=True)

    if not tree_entries:
        raise SystemExit("Hech qanday fayl yuklanmadi.")

    new_tree = _create_tree(token, base_tree, tree_entries)
    new_commit = _create_commit(token, new_tree, parent_sha, message)
    _update_ref(token, branch, new_commit)
    return new_commit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--message", default="feat: Market Shield SPY QQQ VIX regime gates for long BUY")
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--paths-file", default="", help="JSON list of paths")
    args = parser.parse_args()

    ensure_env_file(_ROOT)
    load_project_env(_ROOT)
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        print("GITHUB_TOKEN .env da kerak.", file=sys.stderr)
        return 1

    if args.paths_file:
        paths = json.loads(Path(args.paths_file).read_text(encoding="utf-8"))
    else:
        paths = list(DEFAULT_PATHS)

    try:
        sha = push_files(token, paths, message=args.message, branch=args.branch)
    except requests.HTTPError as exc:
        body = ""
        if exc.response is not None:
            body = exc.response.text[:500]
        print(f"GitHub API xato: {exc}\n{body}", file=sys.stderr)
        return 1

    print(f"GitHub push OK — commit {sha[:12]} on {args.branch}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
