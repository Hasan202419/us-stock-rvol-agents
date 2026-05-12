import json
import os
import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List

import requests
from openai import OpenAI


def _retryable_openai(exc: BaseException) -> bool:
    """429/5xx va ulanish xatolarida qayta urinish (OpenAI SDK turli versiyalar uchun)."""

    name = type(exc).__name__
    if name in {"RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError"}:
        return True
    code = getattr(exc, "status_code", None)
    if isinstance(code, int) and code in {408, 425, 429, 500, 502, 503, 504}:
        return True
    resp = getattr(exc, "response", None)
    rcode = getattr(resp, "status_code", None) if resp is not None else None
    return isinstance(rcode, int) and rcode in {408, 425, 429, 500, 502, 503, 504}


class ChatGPTAnalystAgent:
    """Use ChatGPT only as an analyst/advisor.

    This agent never places trades. It returns structured advice that must still
    pass the hard-coded RiskManagerAgent before any paper order can be sent.
    """

    def __init__(self, openai_api_key: str | None = None, finnhub_api_key: str | None = None) -> None:
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self.finnhub_api_key = finnhub_api_key or os.getenv("FINNHUB_API_KEY", "")
        self._llm_label = "LLM"
        provider = os.getenv("AI_PROVIDER", "auto").strip().lower()
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        deepseek_base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")

        use_openai = bool(self.openai_api_key.strip())
        use_deepseek = bool(deepseek_key)

        if provider == "openai":
            use_deepseek = False
        elif provider == "deepseek":
            # DeepSeek ustun; kaliti yo‘q bo‘lsa OpenAI fallback (faqat OPENAI kalit mavjud bo‘lsa).
            if use_deepseek:
                use_openai = False
        elif provider == "auto":
            # Ikkala kalit ham bo'lsa: avvalo DeepSeek (OPENAI ko'pincha noto'g'ri/namuna; DeepSeek ishlaydi).
            # Faqat OpenAI kerak bo'lsa: AI_PROVIDER=openai
            if use_openai and use_deepseek:
                use_openai = False

        if use_openai:
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            self.client = OpenAI(api_key=self.openai_api_key.strip())
            self._llm_label = "OpenAI"
        elif use_deepseek:
            self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            self.client = OpenAI(api_key=deepseek_key, base_url=deepseek_base)
            self._llm_label = "DeepSeek"
        else:
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            self.client = None

    def analyze(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        if not self.client:
            return self._fallback("LLM kalitlari yo'q (DeepSeek yoki OpenAI); tahlil o'tkazildi.")

        news = self._fetch_news(signal["ticker"])
        prompt = {
            "signal": {
                "ticker": signal.get("ticker"),
                "price": signal.get("price"),
                "change_percent": signal.get("change_percent"),
                "volume": signal.get("volume"),
                "avg_volume": signal.get("avg_volume"),
                "rvol": signal.get("rvol"),
                "score": signal.get("score"),
                "data_delay": signal.get("data_delay"),
                "strategy_name": signal.get("strategy_name"),
                "session_vwap": signal.get("session_vwap"),
                "rsi_14": signal.get("rsi_14"),
                "atr_14": signal.get("atr_14"),
                "take_profit_suggestion": signal.get("take_profit_suggestion"),
                "stop_suggestion": signal.get("stop_suggestion"),
                "daily_rsi_14": signal.get("daily_rsi_14"),
                "daily_ema_9": signal.get("daily_ema_9"),
                "daily_ema_20": signal.get("daily_ema_20"),
                "daily_atr_14": signal.get("daily_atr_14"),
                "volume_pattern_summary": signal.get("volume_pattern_summary"),
                "ignition_trend_stage": signal.get("ignition_trend_stage"),
                "ignition_distance_to_resistance_pct": signal.get("ignition_distance_to_resistance_pct"),
                "ignition_continuation_probability": signal.get("ignition_continuation_probability"),
                "ignition_risk_level": signal.get("ignition_risk_level"),
            },
            "recent_news": news,
            "schema_v2": {
                "decision": ["WATCH", "STRONG_WATCH", "AVOID"],
                "confidence": "int 1-10",
                "reason": "text",
                "risk_level": ["LOW", "MEDIUM", "HIGH"],
                "allow_order": "bool advisory",
                "risk_flags": "list[str] soft warnings",
                "risk_flags_hard": "list[str] deterministic veto helpers",
                "entry_condition": "text",
                "paper_ready_blocked": "null|string",
            },
        }

        max_retries = max(1, int(os.getenv("OPENAI_ANALYSIS_MAX_RETRIES", "4")))
        base_sec = float(os.getenv("OPENAI_ANALYSIS_RETRY_BASE_SEC", "1.25"))

        last_api_error: BaseException | None = None
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a cautious stock-scanning analyst (schema v2). "
                                "Never claim executions. JSON keys: "
                                "decision,confidence,reason,risk_level,allow_order,"
                                "risk_flags,risk_flags_hard,entry_condition,paper_ready_blocked. "
                                "decision is WATCH, STRONG_WATCH, or AVOID. "
                                "If reckless, populate risk_flags_hard with short uppercase codes. "
                                "Always include allow_order explicitly. "
                                "Set allow_order=true only when the setup is WATCH/STRONG_WATCH, has no hard blockers, "
                                "and is acceptable for paper-trade consideration."
                            ),
                        },
                        {"role": "user", "content": json.dumps(prompt, default=str)},
                    ],
                    temperature=0.2,
                )
                raw_content = response.choices[0].message.content or "{}"
            except Exception as exc:
                last_api_error = exc
                if not _retryable_openai(exc) or attempt >= max_retries - 1:
                    break
                delay = base_sec * (2**attempt) + random.uniform(0, 0.35)
                time.sleep(delay)
                continue

            try:
                data = json.loads(raw_content)
            except json.JSONDecodeError as exc:
                return self._fallback(f"{self._llm_label} returned invalid JSON: {exc}")

            return self._normalize_response(data)

        if last_api_error is not None:
            return self._fallback(f"{self._llm_label} analysis failed: {last_api_error}")
        return self._fallback(f"{self._llm_label} analysis failed (no response).")

    def _fetch_news(self, ticker: str) -> List[Dict[str, str]]:
        if not self.finnhub_api_key:
            return []

        today = datetime.now(UTC).date()
        week_ago = today - timedelta(days=7)

        try:
            response = requests.get(
                "https://finnhub.io/api/v1/company-news",
                params={
                    "symbol": ticker,
                    "from": week_ago.isoformat(),
                    "to": today.isoformat(),
                    "token": self.finnhub_api_key,
                },
                timeout=10,
            )
            response.raise_for_status()
            items = response.json()[:5]
        except requests.RequestException:
            return []

        return [
            {
                "headline": item.get("headline", ""),
                "summary": item.get("summary", ""),
                "source": item.get("source", ""),
            }
            for item in items
        ]

    def _normalize_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        decision = str(data.get("decision", "WATCH")).upper().replace("-", "_")
        mapping = {"NO_SIGNAL": "AVOID", "BUY_SIGNAL": "STRONG_WATCH", "HOLD": "WATCH", "WAIT": "WATCH"}
        decision = mapping.get(decision, decision)
        if decision not in {"WATCH", "STRONG_WATCH", "AVOID"}:
            decision = "WATCH"

        risk_level = str(data.get("risk_level", "HIGH")).upper()
        if risk_level not in {"LOW", "MEDIUM", "HIGH"}:
            risk_level = "HIGH"

        try:
            confidence = max(1, min(int(data.get("confidence", 1)), 10))
        except (TypeError, ValueError):
            confidence = 1

        risk_flags = data.get("risk_flags") if isinstance(data.get("risk_flags"), list) else []
        risk_flags = [str(x) for x in risk_flags][:12]

        risk_flags_hard = data.get("risk_flags_hard") if isinstance(data.get("risk_flags_hard"), list) else []
        risk_flags_hard = [str(x) for x in risk_flags_hard][:8]

        blocked = data.get("paper_ready_blocked")
        entry_condition = str(data.get("entry_condition", "")).strip()
        explicit_ready = blocked in (None, "", []) and decision in {"WATCH", "STRONG_WATCH"} and not risk_flags_hard
        raw_allow = data.get("allow_order")
        if isinstance(raw_allow, bool):
            allow_order = raw_allow
        elif isinstance(raw_allow, str) and raw_allow.strip():
            allow_order = raw_allow.strip().lower() in {"1", "true", "yes", "on"}
        else:
            allow_order = explicit_ready

        return {
            "decision": decision,
            "confidence": confidence,
            "reason": str(data.get("reason", "No reason supplied.")),
            "risk_level": risk_level,
            "allow_order": allow_order,
            "risk_flags": risk_flags,
            "risk_flags_hard": risk_flags_hard,
            "entry_condition": entry_condition,
            "paper_ready_blocked": None if blocked in (None, "", []) else str(blocked),
            "paper_ready_explicit": explicit_ready,
        }

    def _fallback(self, reason: str) -> Dict[str, Any]:
        return {
            "decision": "AVOID",
            "confidence": 1,
            "reason": reason,
            "risk_level": "HIGH",
            "allow_order": False,
            "risk_flags": [],
            "risk_flags_hard": [],
            "entry_condition": "",
            "paper_ready_blocked": None,
            "paper_ready_explicit": False,
        }
