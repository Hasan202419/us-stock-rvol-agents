import json
import os
import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List

import requests
from openai import OpenAI

from agents.telegram_framework_html import ANALYST_LLM_SYSTEM_APPENDIX
from agents.trade_plan_format import analyst_trade_plan_for_signal, parse_trade_plan_dict


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
            return self._with_trade_plan_text(signal, self._fallback("LLM kalitlari yo'q (DeepSeek yoki OpenAI); tahlil o'tkazildi."))

        news = self._fetch_news(signal["ticker"])
        trade_plan_on = os.getenv("ANALYST_TRADE_PLAN_ENABLED", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        framework_append = os.getenv("LLM_ANALYST_FRAMEWORK_APPEND", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
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
                "ignition_professional_outline": signal.get("ignition_professional_outline"),
                "mtf_summary_line": signal.get("mtf_summary_line"),
                "mtf_alignment_count": signal.get("mtf_alignment_count"),
                "mtf_alignment_total": signal.get("mtf_alignment_total"),
                "mtf_snapshot_by_tf": signal.get("mtf_snapshot_by_tf"),
                "amt_buy_signal": signal.get("amt_buy_signal"),
                "amt_summary_line": signal.get("amt_summary_line"),
                "amt_tp_zone": signal.get("amt_tp_zone"),
                "amt_strong_tp_zone": signal.get("amt_strong_tp_zone"),
                "amt_poc_proxy": signal.get("amt_poc_proxy"),
                "amt_vah": signal.get("amt_vah"),
                "amt_val": signal.get("amt_val"),
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
                "entry_condition": "text — must align with trade_plan.entry_price idea when bullish",
                "paper_ready_blocked": "null|string",
            },
        }
        if trade_plan_on:
            prompt["schema_v2"]["trade_plan"] = {
                "company": "string (or unknown)",
                "reason_catalyst": "string — edge / catalyst / unusual volume",
                "fundamental_analysis": "string — brief; say insufficient data if unknown",
                "technical_analysis": "string — trend, S/R, volume, price action",
                "prediction": "string — bullish bias, move size estimate, probability language cautious",
                "risk_analysis": "string — support, downside, volatility, R:R narrative",
                "entry_price": "string e.g. near 123.45 or zone",
                "stop_loss": "string — numeric level",
                "target_price": "string — numeric level",
                "risk_reward_ratio": "string e.g. ~2.5:1",
                "position_size_example": "string — illustrative only, not a mandate",
                "execution_plan": "string — confirmation, stops, management",
                "final_trade_summary": "string — one paragraph",
            }

        max_retries = max(1, int(os.getenv("OPENAI_ANALYSIS_MAX_RETRIES", "4")))
        base_sec = float(os.getenv("OPENAI_ANALYSIS_RETRY_BASE_SEC", "1.25"))

        last_api_error: BaseException | None = None
        trade_plan_block = ""
        if trade_plan_on:
            trade_plan_block = (
                " Also include key trade_plan (object) with fields: company, reason_catalyst, "
                "fundamental_analysis, technical_analysis, prediction, risk_analysis, entry_price, stop_loss, "
                "target_price, risk_reward_ratio, position_size_example, execution_plan, final_trade_summary. "
                "Use professional English. Numbers should be consistent with signal.stop_suggestion / "
                "take_profit_suggestion when present. Never claim executed trades."
            )
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
                                "risk_flags,risk_flags_hard,entry_condition,paper_ready_blocked"
                                + (",trade_plan" if trade_plan_on else "")
                                + ". "
                                "decision is WATCH, STRONG_WATCH, or AVOID. "
                                "If reckless, populate risk_flags_hard with short uppercase codes. "
                                "Always include allow_order explicitly. "
                                "Set allow_order=true only when the setup is WATCH/STRONG_WATCH, has no hard blockers, "
                                "and is acceptable for paper-trade consideration."
                                + trade_plan_block
                                + (" " + ANALYST_LLM_SYSTEM_APPENDIX if framework_append else "")
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
                return self._with_trade_plan_text(signal, self._fallback(f"{self._llm_label} returned invalid JSON: {exc}"))

            normalized = self._normalize_response(data)
            return self._with_trade_plan_text(signal, normalized, trade_plan_enabled=trade_plan_on)

        if last_api_error is not None:
            return self._with_trade_plan_text(signal, self._fallback(f"{self._llm_label} analysis failed: {last_api_error}"))
        return self._with_trade_plan_text(signal, self._fallback(f"{self._llm_label} analysis failed (no response)."))

    def _with_trade_plan_text(
        self,
        signal: Dict[str, Any],
        view: Dict[str, Any],
        *,
        trade_plan_enabled: bool | None = None,
    ) -> Dict[str, Any]:
        if trade_plan_enabled is None:
            trade_plan_enabled = os.getenv("ANALYST_TRADE_PLAN_ENABLED", "true").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        _, md = analyst_trade_plan_for_signal(signal, view, trade_plan_enabled=trade_plan_enabled)
        out = dict(view)
        out["analyst_trade_plan_text"] = md
        return out

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
            "trade_plan": parse_trade_plan_dict(data.get("trade_plan")),
            "analyst_trade_plan_text": "",
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
            "trade_plan": {},
            "analyst_trade_plan_text": "",
        }
