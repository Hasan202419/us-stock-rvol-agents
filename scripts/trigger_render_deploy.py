"""Trigger Render deploy(s).

1) ``RENDER_DEPLOY_HOOK_URL`` — Web Dashboard → Deploy Hook (POST).
   Ixtiyoriy: ``RENDER_WORKER_DEPLOY_HOOK_URL`` — Telegram worker hook (ikkinchi POST).
2) ``RENDER_API_KEY`` + ``RENDER_SERVICE_ID`` — REST deploy.
   Ixtiyoriy: ``RENDER_WORKER_SERVICE_ID`` yoki ``--worker-service-id`` — ikkinchi worker deploy.

Usage:
  python scripts/trigger_render_deploy.py
  python scripts/trigger_render_deploy.py --clear-cache
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.bootstrap_env import ensure_env_file, load_project_env  # noqa: E402


def _render_env_help(extra: str = "") -> None:
    env_path = _PROJECT_ROOT / ".env"
    base = (
        "Render uchun `.env` faylda quyidagidan BIR VARIANT bo'lishi kerak:\n\n"
        "VARIANT A (tavsiya): Dashboard → WEB service (`us-stock-rvol-dashboard`) → "
        "Settings → Build & Deploy → Deploy Hook — to'liq URL ni nusxa oling va `.env`ga qo'shing:\n"
        "  RENDER_DEPLOY_HOOK_URL=https://api.render.com/deploy/srv-xxxx?key=yyyy\n\n"
        "Telegram worker alohida servis → uning Deploy Hook ham (ixtiyoriy):\n"
        "  RENDER_WORKER_DEPLOY_HOOK_URL=https://api.render.com/deploy/...\n\n"
        "VARIANT B: Account → API Keys → Render API kaliti va WEB service ID (srv-...):\n"
        "  RENDER_API_KEY=rnd_xxxxx\n"
        "  RENDER_SERVICE_ID=srv-xxxx\n"
        "Ixtiyoriy worker uchun:\n"
        "  RENDER_WORKER_SERVICE_ID=srv-xxxx\n\n"
        f"`.env` manzili: {env_path}\n"
        f"(So'zlandi: MASTER_PLAN yoki boshqa joydagi aktiv qator `.env`ga ko'chirish kerak.)"
    )
    if extra:
        print(extra, file=sys.stderr)
        print("", file=sys.stderr)
    print(base, file=sys.stderr)


def main() -> int:
    ensure_env_file(_PROJECT_ROOT)
    load_project_env(_PROJECT_ROOT)

    parser = argparse.ArgumentParser(description="Queue a Render deploy (hook URL or REST API).")
    parser.add_argument(
        "--service-id",
        default=os.getenv("RENDER_SERVICE_ID", "").strip(),
        help="Render service ID (default: RENDER_SERVICE_ID from .env)",
    )
    parser.add_argument(
        "--worker-service-id",
        default=os.getenv("RENDER_WORKER_SERVICE_ID", "").strip(),
        help="Optional second service (Telegram worker) for REST API path.",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Pass clearCache=clear for REST API deploy (ignored for Deploy Hook).",
    )
    args = parser.parse_args()

    hook = os.getenv("RENDER_DEPLOY_HOOK_URL", "").strip()
    worker_hook = os.getenv("RENDER_WORKER_DEPLOY_HOOK_URL", "").strip()
    if hook:
        if args.clear_cache:
            print(
                "Note: --clear-cache is ignored for Deploy Hook; use Dashboard or API deploy if needed.",
                file=sys.stderr,
            )
        response = requests.post(hook, timeout=60)
        print(f"deploy hook (web) http {response.status_code}", flush=True)
        if response.text:
            try:
                print(response.text[:2000], flush=True)
            except Exception:
                pass
        if not (200 <= response.status_code < 300):
            return 1
        if worker_hook:
            w = requests.post(worker_hook, timeout=60)
            print(f"deploy hook (telegram worker) http {w.status_code}", flush=True)
            if w.text:
                try:
                    print(w.text[:2000], flush=True)
                except Exception:
                    pass
            if not (200 <= w.status_code < 300):
                return 1
        return 0

    key = os.getenv("RENDER_API_KEY", "").strip()
    if not key:
        _render_env_help("RENDER_DEPLOY_HOOK_URL bo'sh — lekin REST uchun RENDER_API_KEY ham yo'q.")
        return 1
    if not args.service_id:
        _render_env_help("RENDER_DEPLOY_HOOK_URL yo'qligi uchun REST ishlatyapsiz — lekin RENDER_SERVICE_ID bo'sh.")
        return 1

    body: dict[str, str] = {}
    if args.clear_cache:
        body["clearCache"] = "clear"

    response = requests.post(
        f"https://api.render.com/v1/services/{args.service_id}/deploys",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=body if body else None,
        timeout=60,
    )
    print(f"api http {response.status_code}", flush=True)
    try:
        print(response.text[:2000], flush=True)
    except Exception:
        pass
    if response.status_code not in (201, 202):
        return 1

    worker_sid = (args.worker_service_id or "").strip()
    if worker_sid:
        response2 = requests.post(
            f"https://api.render.com/v1/services/{worker_sid}/deploys",
            headers={
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=body if body else None,
            timeout=60,
        )
        print(f"api (worker) http {response2.status_code}", flush=True)
        try:
            print(response2.text[:2000], flush=True)
        except Exception:
            pass
        if response2.status_code not in (201, 202):
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
