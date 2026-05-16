"""Loyiha ildizidagi `.env` ni yaratish va `.env`-da ruxsat etilgan kalit aliaslari."""

from __future__ import annotations

import os
import re
from pathlib import Path

# `# KEY=value` (MASTER_PLAN izoh bloki) — aktiv `KEY` bo'lsa e'tiborsiz; bo'sh bo'lsa shu yerdan to'ldiriladi.
_PROMOTE_FROM_COMMENT_IF_EMPTY: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "POLYGON_API_KEY",
        "FINNHUB_API_KEY",
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "RENDER_API_KEY",
        "DEEPSEEK_API_KEY",
        "FMP_API_KEY",
        "NEWSAPI_KEY",
        "ZOYA_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "RENDER_SERVICE_ID",
        "GITHUB_TOKEN",
        "FINVIZ_ELITE_AUTH",
        "FINVIZ_ELITE_EXPORT_QUERY",
    }
)
_COMMENT_LINE = re.compile(
    r"^\s*#\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$",
)


def ensure_env_file(project_root: Path) -> bool:
    """`.env` yo‘q bo‘lsa, `.env.example` dan nusxa oladi. Yaratildi-yo‘qligini qaytaradi."""

    env_path = project_root / ".env"
    example = project_root / ".env.example"
    if env_path.exists():
        return False
    if not example.exists():
        return False
    env_path.write_bytes(example.read_bytes())
    return True


def promote_master_plan_comment_env(env_path: Path) -> None:
    """`.env` ichidagi `# KEY=value` (izoh) qatorlaridan kalitlarni o'qiydi — faqat aktiv qiymat bo'sh bo'lsa."""

    if not env_path.is_file():
        return
    try:
        raw = env_path.read_text(encoding="utf-8-sig")
    except OSError:
        return

    last_comment_val: dict[str, str] = {}
    for line in raw.splitlines():
        m = _COMMENT_LINE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key not in _PROMOTE_FROM_COMMENT_IF_EMPTY or not val:
            continue
        if val in {"...", '""', "''"}:
            continue
        last_comment_val[key] = val

    for key, val in last_comment_val.items():
        if os.getenv(key, "").strip():
            continue
        os.environ[key] = val


def normalize_alpaca_key_alias() -> None:
    """Alpaca dokumentatsiyasidagi `ALPACA_KEY_ID` → `ALPACA_API_KEY` (bo‘sh bo‘lsa)."""

    if os.getenv("ALPACA_API_KEY", "").strip():
        return
    kid = os.getenv("ALPACA_KEY_ID", "").strip() or os.getenv("ALPACA_API_KEY_ID", "").strip()
    if kid:
        os.environ["ALPACA_API_KEY"] = kid


def normalize_alpaca_secret_alias() -> None:
    """`ALPACA_SECRET_KEY` bo‘sh bo‘lsa, eski aliaslardan ko‘chiradi."""

    if os.getenv("ALPACA_SECRET_KEY", "").strip():
        return
    secret = os.getenv("ALPACA_API_SECRET_KEY", "").strip()
    if secret:
        os.environ["ALPACA_SECRET_KEY"] = secret


def alpaca_credentials_ok() -> bool:
    """Paper API uchun API key + secret (barcha alias nomlar bilan)."""

    normalize_alpaca_key_alias()
    normalize_alpaca_secret_alias()
    key = (
        os.getenv("ALPACA_API_KEY", "").strip()
        or os.getenv("ALPACA_API_KEY_ID", "").strip()
        or os.getenv("ALPACA_KEY_ID", "").strip()
    )
    secret = os.getenv("ALPACA_SECRET_KEY", "").strip() or os.getenv("ALPACA_API_SECRET_KEY", "").strip()
    return bool(key and secret)


def alpaca_credentials_source_hint() -> str:
    """Diagnostika: qaysi env kalit topildi (qiymatsiz)."""

    normalize_alpaca_key_alias()
    normalize_alpaca_secret_alias()
    key_name = ""
    for name in ("ALPACA_API_KEY", "ALPACA_API_KEY_ID", "ALPACA_KEY_ID"):
        if os.getenv(name, "").strip():
            key_name = name
            break
    sec_name = ""
    for name in ("ALPACA_SECRET_KEY", "ALPACA_API_SECRET_KEY"):
        if os.getenv(name, "").strip():
            sec_name = name
            break
    if key_name and sec_name:
        return f"{key_name}+{sec_name}"
    if not key_name and not sec_name:
        return "set ALPACA_API_KEY + ALPACA_SECRET_KEY on Render"
    return f"missing: {'' if key_name else 'API_KEY'} {'' if sec_name else 'SECRET'}"


def normalize_polygon_alias() -> None:
    """Eski loyihadagi `MASSIVE_API_KEY` ni `POLYGON_API_KEY` o‘rnida qabul qiladi."""

    if os.getenv("POLYGON_API_KEY", "").strip():
        return
    massive = os.getenv("MASSIVE_API_KEY", "").strip()
    if massive:
        os.environ["POLYGON_API_KEY"] = massive


# HTTP sarlavha / query orqali yuboriladi; nusxa-yozishda ASCII bo‘lmagan belgilar (BOM, “smart quote”)
# Windows da UnicodeEncodeError yoki 401 berishi mumkin. Haqiqiy kalitlar ASCII.
_HTTP_ASCII_SANITIZE_KEYS: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "POLYGON_API_KEY",
        "FINNHUB_API_KEY",
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "RENDER_API_KEY",
        "FMP_API_KEY",
        "NEWSAPI_KEY",
        "ZOYA_API_KEY",
        "GITHUB_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "ALPHA_VANTAGE_API_KEY",
    }
)


def strip_non_ascii_from_http_api_keys() -> None:
    """`.env` dagi kalitlardan faqat ASCII qoldiradi (yashirin Unicode olib tashlanadi)."""

    for key in _HTTP_ASCII_SANITIZE_KEYS:
        raw = os.getenv(key, "")
        if not raw:
            continue
        cleaned = "".join(ch for ch in raw if ch.isascii()).strip()
        if cleaned != raw:
            os.environ[key] = cleaned


def _parse_services_list(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("service", "services", "items"):
            raw = payload.get(key)
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
    return []


def drop_invalid_render_service_id() -> None:
    """`RENDER_SERVICE_ID` Web Service ID `srv-...` bo'lishi kerak.

    Ba'zan `tea-...` (team) yoki boshqa noto'g'ri qiymat `.env` ga tushadi — API orqali topish
    uchun shunday qiymatni e'tiborsiz qoldiramiz.
    """

    sid = os.getenv("RENDER_SERVICE_ID", "").strip()
    if not sid:
        return
    if sid.startswith("srv-"):
        return
    os.environ.pop("RENDER_SERVICE_ID", None)


def resolve_render_service_id_from_api() -> None:
    """`RENDER_SERVICE_ID` bo'sh bo'lsa, `RENDER_API_KEY` orqali Render'dan qidiradi.

    `RENDER_SERVICE_NAME` (default: us-stock-rvol-dashboard, render.yaml dagi name) bo'yicha mos servisni tanlaydi.
    Mos kelmasa va workspace'da yagona `web` servis bo'lsa, shu ID ishlatiladi.

    `SKIP_RENDER_SERVICE_RESOLVE=true` bo'lsa yoki tarmoq yo'q bo'lsa — hech narsa o'zgarmaydi.
    """

    if os.getenv("RENDER_SERVICE_ID", "").strip():
        return
    if os.getenv("SKIP_RENDER_SERVICE_RESOLVE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    key = os.getenv("RENDER_API_KEY", "").strip()
    if not key:
        return

    default_name = "us-stock-rvol-dashboard"
    name_want = os.getenv("RENDER_SERVICE_NAME", default_name).strip() or default_name

    try:
        import requests

        r = requests.get(
            "https://api.render.com/v1/services",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            params={"limit": "100"},
            timeout=30,
        )
        if r.status_code != 200:
            return
        services = _parse_services_list(r.json())
    except Exception:
        return

    webs: list[dict[str, object]] = []
    for svc in services:
        sid = svc.get("id")
        if not isinstance(sid, str) or not sid.startswith("srv-"):
            continue
        sname = svc.get("name")
        name_ok = isinstance(sname, str) and sname == name_want
        stype = str(svc.get("type", "")).lower()
        if stype == "web":
            webs.append(svc)
        if name_ok:
            os.environ["RENDER_SERVICE_ID"] = sid
            return

    if len(webs) == 1:
        only = webs[0].get("id")
        if isinstance(only, str) and only.startswith("srv-"):
            os.environ["RENDER_SERVICE_ID"] = only


def load_project_env(project_root: Path) -> Path:
    """`.env` ni yuklaydi, izohli fallback, Render service ID (API), Alpaca alias. `.env` yo'li."""

    from dotenv import load_dotenv

    env_path = project_root / ".env"
    # Standart load_dotenv(override=False): agar OPENAI_* kabi kalit Windows "User environment"
    # da mavjud ammo bo‘sh bo‘lsa, .env qiymati yuklanmaydi — barcha kalitlar "bo‘sh" bo‘lib qoladi.
    # Loyiha papkasidagi .env uchun shu qiymatlarni ustuvor qilamiz. Render-da .env odatda yo‘qligi
    # sabab Dashboard env o‘zgarmaydi.
    load_dotenv(env_path, override=True, encoding="utf-8-sig")
    promote_master_plan_comment_env(env_path)
    drop_invalid_render_service_id()
    resolve_render_service_id_from_api()
    normalize_polygon_alias()
    normalize_alpaca_key_alias()
    normalize_alpaca_secret_alias()
    strip_non_ascii_from_http_api_keys()
    return env_path
