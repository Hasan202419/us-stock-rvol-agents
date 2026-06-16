"""Bullish BUY signal — volume-ignition mezonlari + professional analyst output.

Foydalanuvchi frameworki: (1) professional bullish analyst tuzilmasi va (2) volume
ignition scanner mezonlari. Mavjud `VolumeIgnitionStrategyAgent` mezonlarni hisoblaydi;
bu modul ularni **bahоlangan kontrol-roʻyxat** (necha mezon oʻtdi) + **must-have** shartlar
asosida QATʼIY verdiktга aylantiradi: BUY / WATCH / AVOID — va toʻliq savdo rejasini beradi.

Deterministik: tarmoq/LLM shart emas — signalda candles + RVOL boʻlsa har doim ishlaydi.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple

from agents.strategy_volume_ignition import VolumeIgnitionStrategyAgent

# Volume-ignition mezonlari (fail kaliti → inson oʻqiydigan nom).
CRITERIA: List[Tuple[str, str]] = [
    ("volume_three_up", "3 kun ketма-ket hajm oʻsishi"),
    ("volume_20d_ma2x", "Hajm ≥ 2× 20-kunlik oʻrtacha"),
    ("rvol", "RVOL ≥ chegara (≥2)"),
    ("cap_3d_gain", "3 kunda < +10% (charchamagan)"),
    ("near_resistance", "Qarshilikка yaqin (≤5%)"),
    ("higher_low", "Strukturali higher-low"),
    ("ema_context", "Narx > EMA9, EMA20 dan uzoq emas"),
    ("atr_rising", "ATR koʻtarilmoqda"),
    ("liquidity", "Likvidlik ≥ 1M"),
]

# BUY uchun shart majburiy oʻtishi kerak (boʻlmasa BUY emas).
_MUST_HAVE = ("rvol", "volume_20d_ma2x", "liquidity", "price_min")
# Bular fail boʻlsa — qatʼiy AVOID (xavfli setup).
_HARD_AVOID = ("extended_ban", "parabolic")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _position_size_example(entry: float, stop: float) -> Dict[str, Any]:
    """Namuna pozitsiya: hisob × risk% / aksiyaga risk; notional MAX_POSITION_SIZE_USD bilan cheklanadi."""

    account = _env_float("BUY_EXAMPLE_ACCOUNT_USD", 10_000.0)
    risk_pct = _env_float("MAX_RISK_PCT_OF_EQUITY", _env_float("MAX_RISK_PCT", 1.0)) / 100.0
    pos_cap = _env_float("MAX_POSITION_SIZE_USD", 10_000.0)
    per_share = max(entry - stop, 1e-9)
    risk_usd = account * risk_pct
    shares = int(risk_usd / per_share) if per_share > 0 else 0
    if entry > 0:
        shares = min(shares, int(pos_cap / entry))
    shares = max(shares, 0)
    return {
        "shares": shares,
        "notional": round(shares * entry, 2),
        "risk_usd": round(shares * per_share, 2),
        "account": account,
        "risk_pct": round(risk_pct * 100.0, 2),
    }


def evaluate_bullish_buy(
    signal: Dict[str, Any],
    *,
    agent: Optional[VolumeIgnitionStrategyAgent] = None,
) -> Dict[str, Any]:
    """Volume-ignition mezonlarini baholab, qatʼiy BUY/WATCH/AVOID verdiktini chiqaradi."""

    agent = agent or VolumeIgnitionStrategyAgent()
    sig = agent.evaluate(dict(signal), None)
    fails = set(sig.get("failed_rules") or [])

    checklist = [{"key": k, "label": lbl, "ok": k not in fails} for k, lbl in CRITERIA]
    n_pass = sum(1 for c in checklist if c["ok"])
    n_total = len(CRITERIA)

    conf = int(round(float(sig.get("ignition_continuation_probability") or 0)))
    hard_avoid = any(k in fails for k in _HARD_AVOID) or bool(sig.get("failed_rules") and "bars_history" in fails)
    must_ok = all(k not in fails for k in _MUST_HAVE)

    min_conf = _env_int("BUY_MIN_CONFIDENCE", 70)
    watch_conf = _env_int("BUY_WATCH_CONFIDENCE", 50)
    min_pass = math.ceil(n_total * _env_float("BUY_MIN_CRITERIA_FRAC", 0.7))

    if hard_avoid:
        verdict = "AVOID"
    elif must_ok and conf >= min_conf and n_pass >= min_pass:
        verdict = "BUY"
    elif conf >= watch_conf or n_pass >= math.ceil(n_total * 0.6):
        verdict = "WATCH"
    else:
        verdict = "AVOID"

    price = float(sig.get("price") or signal.get("price") or 0)
    entry = price
    stop = float(sig.get("stop_suggestion") or 0) or round(price * 0.95, 4)
    target = float(sig.get("take_profit_suggestion") or 0)
    min_rr = max(1.5, _env_float("MIN_RISK_REWARD_RATIO", 2.0))
    risk = max(entry - stop, 1e-9)
    # Ignition take_profit = qarshilik (breakout darajasi). Bullish davom uchun haqiqiy
    # target qarshilik ortida — R:R minimumdan past boʻlsa, targetni koʻtaramiz.
    if target <= entry or (target - entry) / risk < min_rr:
        target = round(entry + min_rr * risk, 4)
    rr = round((target - entry) / risk, 2) if risk > 0 else 0.0

    pos = _position_size_example(entry, stop)
    return {
        "ticker": str(sig.get("ticker") or signal.get("ticker") or "?").upper(),
        "verdict": verdict,
        "confidence": conf,
        "criteria": checklist,
        "criteria_passed": n_pass,
        "criteria_total": n_total,
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "rr": rr,
        "trend_stage": sig.get("ignition_trend_stage"),
        "distance_to_resistance_pct": sig.get("ignition_distance_to_resistance_pct"),
        "volume_summary": sig.get("volume_pattern_summary"),
        "rvol": sig.get("rvol"),
        "risk_level": sig.get("ignition_risk_level"),
        "position": pos,
        "_signal": sig,
    }


def verdict_badge(verdict: str) -> str:
    return {"BUY": "🟢 SOTIB OL", "WATCH": "🟡 KUTING", "AVOID": "🔴 OʻTKAZ"}.get(verdict, "🟡 KUTING")


def _esc(s: Any) -> str:
    text = "" if s is None else str(s)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_bullish_buy_report(result: Dict[str, Any], *, company: str = "") -> str:
    """Professional analyst tuzilmasidagi HTML hisobot (Telegram)."""

    t = _esc(result.get("ticker"))
    badge = verdict_badge(result.get("verdict", "WATCH"))
    conf = result.get("confidence")
    npass = result.get("criteria_passed")
    ntot = result.get("criteria_total")
    rvol = result.get("rvol")
    rvol_txt = ""
    try:
        rvol_txt = f"{float(rvol):.2f}" if rvol is not None else "—"
    except (TypeError, ValueError):
        rvol_txt = "—"
    dist = result.get("distance_to_resistance_pct")
    stage = _esc(result.get("trend_stage") or "—")
    pos = result.get("position") or {}

    checklist_lines = "\n".join(
        f"{'✅' if c['ok'] else '❌'} {_esc(c['label'])}" for c in result.get("criteria", [])
    )

    reason = result.get("volume_summary") or "Abnormal hajm kengayishi (momentum davomi nazariyasi)."
    dist_txt = f"{dist}%" if dist is not None else "—"

    return (
        f"<b>{badge}</b> · <code>{t}</code> · ishonch <b>{conf}%</b> ({npass}/{ntot} mezon)\n"
        f"<b>Ticker:</b> {t}\n"
        f"<b>Company:</b> {_esc(company or '—')}\n"
        f"<b>Reason (Catalyst):</b> {_esc(reason)} "
        f"<i>(yangilik/katalizatorni alohida tasdiqlang)</i>\n"
        f"<b>Technical Setup:</b> Trend bosqichi {stage}; RVOL {rvol_txt}; "
        f"qarshilikка masofa {dist_txt}; narx &gt; EMA9\n"
        f"<b>Entry Price:</b> <code>{result.get('entry')}</code>\n"
        f"<b>Stop Loss:</b> <code>{result.get('stop')}</code>\n"
        f"<b>Target Price:</b> <code>{result.get('target')}</code>\n"
        f"<b>Risk/Reward Ratio:</b> <code>{result.get('rr')}</code>\n"
        f"<b>Position Size Example:</b> <code>{pos.get('shares')}</code> dona "
        f"(~${pos.get('notional')}), risk ~${pos.get('risk_usd')} "
        f"<i>({pos.get('account')} hisob, {pos.get('risk_pct')}%)</i>\n"
        f"<b>Execution Plan:</b> tasdiq kuting → intizom bilan kirish → SL darhol → "
        f"profitni qisman himoyalang\n"
        f"<b>Mezonlar:</b>\n{checklist_lines}\n"
        f"<b>Final Trade Summary:</b> {badge} — {npass}/{ntot} mezon, ishonch {conf}%. "
        f"<i>Oʻtmish/model — kafolat emas.</i>"
    )
