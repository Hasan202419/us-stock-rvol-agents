"""Bir necha timeframe (1m/5m/10m/1H) bo‘yicha qisqa, faktik MTF snapshot — prop qisqa muddat uchun."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from agents.indicators import ema


def _truthy(raw: str | None, *, default: bool = True) -> bool:
    s = (raw or "").strip().lower()
    if not s:
        return default
    if s in {"0", "false", "no", "off"}:
        return False
    return s in {"1", "true", "yes", "on"}


def _parse_timeframes() -> List[int]:
    raw = os.getenv("MTF_TIMEFRAMES", "1,5,10,60").strip()
    if not raw or raw.lower() in {"off", "none", "false"}:
        return []
    allowed = {1, 2, 3, 5, 10, 15, 30, 60}
    out: list[int] = []
    for part in raw.split(","):
        s = part.strip().lower()
        if not s:
            continue
        m: int | None = None
        if s in {"1h", "60m", "60"}:
            m = 60
        elif s.endswith("h") and len(s) > 1:
            try:
                m = int(float(s[:-1].strip()) * 60)
            except ValueError:
                m = None
        elif s.endswith("m"):
            try:
                m = int(float(s[:-1].strip()))
            except ValueError:
                m = None
        else:
            try:
                m = int(float(s))
            except ValueError:
                m = None
        if m is not None and m in allowed and m not in out:
            out.append(m)
    return sorted(out)


def _tf_label(minutes: int) -> str:
    if minutes >= 60:
        return "1H"
    return f"{minutes}m"


def _mtf_lookback_days() -> int:
    try:
        return max(1, min(60, int(os.getenv("MTF_LOOKBACK_CALENDAR_DAYS", os.getenv("INTRADAY_LOOKBACK_DAYS", "7")))))
    except ValueError:
        return 7


def build_mtf_fields(market_data: Any, ticker: str, signal: Dict[str, Any]) -> Dict[str, Any]:
    """Har bir TF uchun oxirgi yopilish va EMA9 nisbati (fakt)."""

    if not _truthy(os.getenv("MTF_SNAPSHOT_ENABLED"), default=True):
        return {}
    pass_only = _truthy(os.getenv("MTF_SNAPSHOT_STRATEGY_PASS_ONLY"), default=True)
    if pass_only and not bool(signal.get("strategy_pass")):
        return {}

    tfs = _parse_timeframes()
    if not tfs:
        return {}

    lookback = _mtf_lookback_days()
    by_tf: Dict[str, Any] = {}
    labels: list[str] = []
    aligned = 0
    counted = 0

    for tf in tfs:
        key = _tf_label(tf)
        try:
            bars = market_data.fetch_intraday_bars(
                ticker,
                timeframe_minutes=tf,
                lookback_calendar_days=lookback,
            )
        except Exception:
            bars = []
        if not bars:
            by_tf[key] = {"timeframe_minutes": tf, "bars": 0, "above_ema9": None}
            labels.append(f"{key}?")
            continue

        closes = [float(b.get("c") or 0.0) for b in bars]
        last_c = closes[-1] if closes else 0.0
        ema9_s = ema(closes, 9)
        e9 = ema9_s[-1] if ema9_s and ema9_s[-1] is not None else None
        above: bool | None
        if e9 is None or e9 <= 0 or last_c <= 0:
            above = None
            labels.append(f"{key}—")
        else:
            above = last_c > float(e9)
            counted += 1
            if above:
                aligned += 1
                labels.append(f"{key}↑")
            else:
                labels.append(f"{key}↓")

        by_tf[key] = {
            "timeframe_minutes": tf,
            "bars": len(bars),
            "close": round(last_c, 4) if last_c else None,
            "ema9": round(float(e9), 4) if e9 is not None else None,
            "above_ema9": above,
            "last_bar_ms": int(bars[-1].get("t") or 0),
        }

    summary = "MTF " + " ".join(labels)
    if counted:
        summary += f" | EMA9↑ {aligned}/{counted}"
    return {
        "mtf_snapshot_by_tf": by_tf,
        "mtf_alignment_count": aligned,
        "mtf_alignment_total": counted,
        "mtf_summary_line": summary,
        "mtf_timeframes_scanned": tfs,
    }


def maybe_attach_mtf_snapshot(market_data: Any, ticker: str, signal: Dict[str, Any]) -> Dict[str, Any]:
    extra = build_mtf_fields(market_data, ticker, signal)
    if not extra:
        return signal
    out = dict(signal)
    out.update(extra)
    return out
