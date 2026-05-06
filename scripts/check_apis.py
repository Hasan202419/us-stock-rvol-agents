"""Offline-friendly API sanity checks: prints statuses only (never prints secrets).

Tekshiriladi (agar .env da bor bo'lsa): OpenAI, DeepSeek, Polygon, Finnhub, Alpaca, Render (account + service),
GitHub, Supabase, Telegram (getMe + getChat), SMTP email (sozlangan/bo‘sh), FMP, NewsAPI, Zoya. Oxirda xulosa: muvaffaqiyat / o'tkazilgan / xato.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import requests

from agents.bootstrap_env import ensure_env_file, load_project_env


def _scrub_secret(value: str) -> str:
    """BOM, nazoratsiz tirnoqlar, yashirin Unicode bo‘laklarini oladi — HTTP headerlar uchun xavfsiz."""

    if not value:
        return ""
    s = value.strip().strip('"').strip("'")
    for ch in ("\ufeff", "\u200b", "\u200c", "\u200d", "\u2060"):
        s = s.replace(ch, "")
    return s.strip()


def _dotenv_final_assignments(env_path: Path) -> dict[str, str]:
    """Fayldagi aktiv (izoh emas) qatorlar bo‘yicha oxirgi `KEY=value` — load_dotenv last-wins bilan bir xil."""

    try:
        raw = env_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {}

    final: dict[str, str] = {}
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.split("#", 1)[0].strip() if val else ""
        if key and key.replace("_", "").isalnum():
            final[key] = val
    return final


_ENV_KEY_NAMES = (
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "POLYGON_API_KEY",
    "FINNHUB_API_KEY",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "RENDER_API_KEY",
    "RENDER_SERVICE_ID",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "FMP_API_KEY",
    "NEWSAPI_KEY",
    "ZOYA_API_KEY",
    "GITHUB_TOKEN",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SMTP_HOST",
    "SMTP_PASSWORD",
    "EMAIL_FROM",
    "EMAIL_TO",
)


# Barcha tekshiriladigan kalitlar — yuqoridagi tuple bilan sinxron.
def log(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            try:
                buf.write((message + "\n").encode("utf-8", errors="replace"))
                buf.flush()
                return
            except Exception:
                pass
        print(message.encode("ascii", errors="replace").decode("ascii"), flush=True)


def looks_placeholder(name: str, value: str) -> bool:
    if not value or not value.strip():
        return True
    if "..." in value:
        return True
    lowered = value.strip().lower()
    if lowered.startswith("your_"):
        return True
    if name == "OPENAI_API_KEY" and len(value.strip()) < 20:
        return True
    if name == "DEEPSEEK_API_KEY" and len(value.strip()) < 8:
        return True
    if name == "TELEGRAM_BOT_TOKEN":
        tok = value.strip()
        if len(tok) < 30 or ":" not in tok:
            return True
    if name == "RENDER_SERVICE_ID":
        sid = value.strip()
        if not sid.startswith("srv-") or len(sid) < 12:
            return True
    if name in {"FMP_API_KEY", "NEWSAPI_KEY", "ZOYA_API_KEY"} and len(value.strip()) < 8:
        return True
    if name == "GITHUB_TOKEN":
        t = value.strip()
        if len(t) < 20:
            return True
        if not (
            t.startswith("ghp_")
            or t.startswith("github_pat_")
            or t.startswith("gho_")
            or t.startswith("ghs_")
        ):
            return True
    if name == "SUPABASE_URL":
        u = value.strip().rstrip("/")
        if not u.startswith("https://") or len(u) < 24:
            return True
    if name == "SUPABASE_ANON_KEY" and len(value.strip()) < 32:
        return True
    return False


def _classify_outcome(detail: str) -> str:
    """xulosa uchun: skip | pass | fail"""

    s = detail.strip().lower()
    if s == "skipped" or s.startswith("skipped"):
        return "skip"
    if "configured" in s:
        return "skip"
    if s == "ok":
        return "pass"
    if detail.startswith("http "):
        parts = detail.split()
        if len(parts) >= 2 and parts[1].isdigit():
            code = int(parts[1])
            return "pass" if 200 <= code < 300 else "fail"
    if "fail" in s:
        return "fail"
    return "fail"


def _log_duplicate_env_keys(env_path: Path) -> None:
    """Bir xil kalit takrorlansa oxirgi qiymat ustun; bo'sh qator barchasini buzadi."""

    try:
        raw_lines = env_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return

    from collections import defaultdict

    hits: dict[str, list[int]] = defaultdict(list)
    for i, raw in enumerate(raw_lines, start=1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        key, _, _rest = s.partition("=")
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        hits[key].append(i)

    dups = [(k, nums) for k, nums in hits.items() if len(nums) > 1]
    if not dups:
        return

    dups.sort(key=lambda x: x[0])
    parts = [f"{k}: qatorlar {', '.join(map(str, nums))}" for k, nums in dups[:10]]
    suffix = "..." if len(dups) > 10 else ""
    log(
        "! .env takrori: bir xil kalit bir necha marta — oxirgi yozuv ustun. Bo‘sh yozuv ustun "
        "qolsa boshqa kalitlar `placeholder_or_empty`. Takrorlangan qatorlarni bittasiga qoldiring:\n  "
        + "\n  ".join(parts)
        + suffix
    )


def main() -> int:
    # UTF-8 konsol; bo‘lmasa log() stdout.buffer orqali UTF-8 yozadi.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    root = _PROJECT_ROOT
    if ensure_env_file(root):
        log("created .env from .env.example — fill API keys, then rerun this script.")

    env_path = root / ".env"
    log(f"env_file: {'found' if env_path.exists() else 'missing'}")
    if not env_path.exists():
        return 0

    _log_duplicate_env_keys(env_path)
    load_project_env(root)

    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line_st = raw_line.strip()
            if not line_st or line_st.startswith("#"):
                continue
            if line_st.startswith("RENDER_SERVICE_") and not line_st.startswith("RENDER_SERVICE_ID="):
                log(
                    "! .env nitpick: noto‘g‘ri kalit — `RENDER_SERVICE_ID` yozilishi kerak (ID yozuvi bilan). "
                    "Sizda `RENDER_SERVICE_` bilan tugagan bo‘lishi mumkin."
                )
                break

    file_final = _dotenv_final_assignments(env_path) if env_path.is_file() else {}

    checks = {name: _scrub_secret(os.getenv(name, "")) for name in _ENV_KEY_NAMES}

    for key_name in _ENV_KEY_NAMES:
        fv = _scrub_secret(file_final.get(key_name, ""))
        ev = checks[key_name]
        if looks_placeholder(key_name, ev) and fv and not looks_placeholder(key_name, fv):
            log(
                f"! diag: {key_name} — `.env` fayl oxiridagi qiymat uzunligi {len(fv)}, lekin yuklangan `os.environ` bo‘sh "
                "(takroriy bo‘sh qator BOM yoki boshqa `.env`; yuqoridagi `takror` xabarini tekshiring)."
            )

    for key_name, raw_value in checks.items():
        label = "placeholder_or_empty" if looks_placeholder(key_name, raw_value) else "set"
        log(f"{key_name}: {label}")

    def ck(name: str) -> str:
        return checks.get(name, "")

    openai_ok = not looks_placeholder("OPENAI_API_KEY", ck("OPENAI_API_KEY"))
    deepseek_ok = not looks_placeholder("DEEPSEEK_API_KEY", ck("DEEPSEEK_API_KEY"))
    polygon_ok = not looks_placeholder("POLYGON_API_KEY", ck("POLYGON_API_KEY"))
    finnhub_ok = not looks_placeholder("FINNHUB_API_KEY", ck("FINNHUB_API_KEY"))
    alpaca_ok = not looks_placeholder("ALPACA_API_KEY", ck("ALPACA_API_KEY")) and not looks_placeholder(
        "ALPACA_SECRET_KEY", ck("ALPACA_SECRET_KEY")
    )
    render_ok = not looks_placeholder("RENDER_API_KEY", ck("RENDER_API_KEY"))
    telegram_token_ok = not looks_placeholder("TELEGRAM_BOT_TOKEN", ck("TELEGRAM_BOT_TOKEN"))
    telegram_chat_ok = not looks_placeholder("TELEGRAM_CHAT_ID", ck("TELEGRAM_CHAT_ID"))
    fmp_ok = not looks_placeholder("FMP_API_KEY", ck("FMP_API_KEY"))
    newsapi_ok = not looks_placeholder("NEWSAPI_KEY", ck("NEWSAPI_KEY"))
    zoya_ok = not looks_placeholder("ZOYA_API_KEY", ck("ZOYA_API_KEY"))
    github_ok = not looks_placeholder("GITHUB_TOKEN", ck("GITHUB_TOKEN"))
    supabase_ok = not looks_placeholder("SUPABASE_URL", ck("SUPABASE_URL")) and not looks_placeholder(
        "SUPABASE_ANON_KEY", ck("SUPABASE_ANON_KEY")
    )

    render_sid_ok = not looks_placeholder("RENDER_SERVICE_ID", ck("RENDER_SERVICE_ID"))

    log("--- live checks ---")

    outcomes: list[tuple[str, str]] = []

    def track(name: str, detail: str) -> None:
        log(f"{name}: {detail}")
        outcomes.append((name, detail))

    finnhub_http: int | None = None
    fmp_http: int | None = None

    # OpenAI
    if openai_ok:
        try:
            from openai import OpenAI

            OpenAI(api_key=ck("OPENAI_API_KEY")).models.list()
            track("openai", "ok")
        except Exception as exc:  # pragma: no cover - network path
            track("openai", f"fail ({type(exc).__name__})")
    else:
        track("openai", "skipped")

    if deepseek_ok:
        try:
            from openai import OpenAI

            base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
            OpenAI(api_key=ck("DEEPSEEK_API_KEY"), base_url=base).models.list()
            track("deepseek", "ok")
        except Exception as exc:  # pragma: no cover - network path
            track("deepseek", f"fail ({type(exc).__name__})")
    else:
        track("deepseek", "skipped")

    if polygon_ok:
        try:
            response = requests.get(
                "https://api.polygon.io/v3/reference/tickers",
                params={"active": "true", "limit": 1, "apiKey": ck("POLYGON_API_KEY")},
                timeout=20,
            )
            track("polygon", f"http {response.status_code}")
        except Exception as exc:
            track("polygon", f"fail ({type(exc).__name__})")
    else:
        track("polygon", "skipped")

    if finnhub_ok:
        try:
            response = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": "AAPL", "token": ck("FINNHUB_API_KEY")},
                timeout=20,
            )
            finnhub_http = response.status_code
            track("finnhub", f"http {finnhub_http}")
        except Exception as exc:
            track("finnhub", f"fail ({type(exc).__name__})")
    else:
        track("finnhub", "skipped")

    if alpaca_ok:
        try:
            base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
            response = requests.get(
                f"{base}/v2/account",
                headers={
                    "APCA-API-KEY-ID": ck("ALPACA_API_KEY"),
                    "APCA-API-SECRET-KEY": ck("ALPACA_SECRET_KEY"),
                },
                timeout=20,
            )
            track("alpaca", f"http {response.status_code}")
        except Exception as exc:
            track("alpaca", f"fail ({type(exc).__name__})")
    else:
        track("alpaca", "skipped")

    if render_ok:
        try:
            response = requests.get(
                "https://api.render.com/v1/users",
                headers={
                    "Authorization": f"Bearer {ck('RENDER_API_KEY')}",
                    "Accept": "application/json",
                },
                timeout=20,
            )
            track("render (account)", f"http {response.status_code}")
        except Exception as exc:
            track("render (account)", f"fail ({type(exc).__name__})")
    else:
        track("render (account)", "skipped")

    if render_ok and render_sid_ok:
        try:
            sid = ck("RENDER_SERVICE_ID")
            response = requests.get(
                f"https://api.render.com/v1/services/{sid}",
                headers={
                    "Authorization": f"Bearer {ck('RENDER_API_KEY')}",
                    "Accept": "application/json",
                },
                timeout=20,
            )
            track("render (service)", f"http {response.status_code}")
        except Exception as exc:
            track("render (service)", f"fail ({type(exc).__name__})")
    else:
        track("render (service)", "skipped")

    if telegram_token_ok:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{ck('TELEGRAM_BOT_TOKEN')}/getMe",
                timeout=15,
            )
            track("telegram (getMe)", f"http {response.status_code}")
        except Exception as exc:
            track("telegram (getMe)", f"fail ({type(exc).__name__})")
    else:
        track("telegram (getMe)", "skipped")

    if telegram_token_ok and telegram_chat_ok:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{ck('TELEGRAM_BOT_TOKEN')}/getChat",
                params={"chat_id": ck("TELEGRAM_CHAT_ID")},
                timeout=15,
            )
            track("telegram (getChat)", f"http {response.status_code}")
        except Exception as exc:
            track("telegram (getChat)", f"fail ({type(exc).__name__})")
    else:
        track("telegram (getChat)", "skipped")

    smtp_host_ok = not looks_placeholder("SMTP_HOST", ck("SMTP_HOST"))
    smtp_pass_ok = not looks_placeholder("SMTP_PASSWORD", ck("SMTP_PASSWORD"))
    email_from_ok = not looks_placeholder("EMAIL_FROM", ck("EMAIL_FROM"))
    email_to_ok = not looks_placeholder("EMAIL_TO", ck("EMAIL_TO"))
    if smtp_host_ok and email_from_ok and email_to_ok:
        auth_note = "login" if smtp_pass_ok else "no_password (relay?)"
        track("smtp_email", f"configured ({auth_note})")
    else:
        track("smtp_email", "skipped")

    if telegram_token_ok and telegram_chat_ok:
        log(
            "telegram (config): chat_id + token tayyor — TELEGRAM_ALERTS_ENABLED=true "
            "yoki TELEGRAM_ALERT_ON_SCAN=true"
        )
    elif telegram_token_ok and not telegram_chat_ok:
        log("telegram (config): TELEGRAM_CHAT_ID yo'q — xabar ketmaydi")

    if fmp_ok:
        try:
            response = requests.get(
                "https://financialmodelingprep.com/api/v3/profile/AAPL",
                params={"apikey": ck("FMP_API_KEY")},
                timeout=20,
            )
            fmp_http = response.status_code
            track("fmp", f"http {fmp_http}")
        except Exception as exc:
            track("fmp", f"fail ({type(exc).__name__})")
    else:
        track("fmp", "skipped")

    if newsapi_ok:
        try:
            response = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={"country": "us", "pageSize": 1, "apiKey": ck("NEWSAPI_KEY")},
                timeout=20,
            )
            track("newsapi", f"http {response.status_code}")
        except Exception as exc:
            track("newsapi", f"fail ({type(exc).__name__})")
    else:
        track("newsapi", "skipped")

    if zoya_ok:
        try:
            response = requests.post(
                "https://api.zoya.finance/graphql",
                json={
                    "query": """
                        query StockPing($ticker: String!) {
                          stock(ticker: $ticker) { ticker }
                        }
                    """,
                    "variables": {"ticker": "AAPL"},
                },
                headers={
                    "Authorization": f"Bearer {ck('ZOYA_API_KEY')}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            track("zoya", f"http {response.status_code}")
        except Exception as exc:
            track("zoya", f"fail ({type(exc).__name__})")
    else:
        track("zoya", "skipped")

    if github_ok:
        try:
            response = requests.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {ck('GITHUB_TOKEN')}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=20,
            )
            track("github", f"http {response.status_code}")
        except Exception as exc:
            track("github", f"fail ({type(exc).__name__})")
    else:
        track("github", "skipped")

    if supabase_ok:
        try:
            base_u = ck("SUPABASE_URL").strip().rstrip("/")
            anon_k = ck("SUPABASE_ANON_KEY")
            response = requests.get(
                f"{base_u}/auth/v1/health",
                headers={
                    "apikey": anon_k,
                    "Authorization": f"Bearer {anon_k}",
                },
                timeout=20,
            )
            track("supabase", f"http {response.status_code}")
        except Exception as exc:
            track("supabase", f"fail ({type(exc).__name__})")
    else:
        track("supabase", "skipped")

    passed = sum(1 for _, d in outcomes if _classify_outcome(d) == "pass")
    skipped = sum(1 for _, d in outcomes if _classify_outcome(d) == "skip")
    failed = sum(1 for _, d in outcomes if _classify_outcome(d) == "fail")
    log("--- xulosa (barcha live tekshiruvlar) ---")
    log(f"  muvaffaqiyat: {passed} · o'tkazildi (kalit yo'q): {skipped} · xato: {failed} · jami: {len(outcomes)}")
    for label, detail in outcomes:
        bucket = _classify_outcome(detail)
        log(f"  [{bucket}] {label}: {detail}")

    log("--- hints (agar kerak bo'lsa) ---")
    if not deepseek_ok:
        log(
            "deepseek: .env da aktiv DEEPSEEK_API_KEY yozing yoki MASTER_PLAN izohidagi "
            "# DEEPSEEK_API_KEY=... (bootstrap_env izohdan avtomatik oladi, agar aktiv bo'sh bo'lsa)."
        )
    if finnhub_ok and finnhub_http == 401:
        log("finnhub: 401 = API kalit rad etilgan; https://finnhub.io/dashboard dan yangi token oling.")
    if render_ok and not render_sid_ok:
        log(
            "render (service): RENDER_SERVICE_ID `srv-...` ko'rinishida emas yoki bo'sh → skipped. "
            "Render Dashboard → Service → Settings → Service ID nusxa. "
            "Yoki RENDER_SERVICE_NAME ni render.yaml dagi name bilan tekshiring (avto-topish)."
        )
    if fmp_ok and fmp_http == 403:
        log(
            "fmp: 403 — rejangiz/profile endpoint bloklangan yoki kalit mos emas; "
            "financialmodelingprep.com/dashboard va ularning yangi Stable API bo'limini ko'ring."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
