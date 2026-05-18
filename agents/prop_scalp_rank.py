"""Qisqa muddat (prop) skan — MTF 1m/5m/1H + AMT + RVOL bo‘yicha tartiblash."""

from __future__ import annotations

from typing import Any, Dict, List


def _f(row: Dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key) or default)
    except (TypeError, ValueError):
        return default


def prop_scalp_priority_score(row: Dict[str, Any]) -> float:
    """Yuqori = Telegramda yuqoriroq (qisqa muddat foyda ehtimoli)."""

    score = _f(row, "score")
    aligned = int(row.get("mtf_alignment_count") or 0)
    total = int(row.get("mtf_alignment_total") or 0)
    if total > 0:
        score += aligned * 12.0
        if aligned == total and total >= 2:
            score += 25.0
    if bool(row.get("amt_buy_signal")):
        score += 40.0
    if bool(row.get("strategy_pass")):
        score += 18.0
    if bool(row.get("paper_trade_ready")):
        score += 10.0
    rvol = _f(row, "rvol")
    if rvol >= 1.5:
        score += min(15.0, (rvol - 1.0) * 8.0)
    chg = _f(row, "change_percent")
    if 0.3 <= chg <= 8.0:
        score += 6.0
    elif chg > 8.0:
        score += 2.0
    regime = str(row.get("market_regime") or "").upper()
    if regime == "RISK_OFF":
        score -= 50.0
    elif regime == "NEWS_LOCK":
        score -= 80.0
    if row.get("watchlist_only"):
        score -= 5.0
    return score


def rank_for_prop_scalp(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prop skan natijasini qayta tartiblash."""

    keyed = [(prop_scalp_priority_score(r), r) for r in rows if isinstance(r, dict)]
    keyed.sort(key=lambda x: (-x[0], str(x[1].get("ticker", ""))))
    return [r for _, r in keyed]


def filter_prop_scalp_candidates(rows: List[Dict[str, Any]], *, min_mtf_aligned: int = 2) -> List[Dict[str, Any]]:
    """Faqat qisqa muddat uchun mantiqiy nomzodlar."""

    out: list[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if bool(r.get("amt_buy_signal")) or bool(r.get("strategy_pass")) or bool(r.get("paper_trade_ready")):
            out.append(r)
            continue
        aligned = int(r.get("mtf_alignment_count") or 0)
        if aligned >= min_mtf_aligned:
            out.append(r)
            continue
        if _f(r, "rvol") >= 2.0 and _f(r, "change_percent") >= 0.5:
            out.append(r)
    return out if out else list(rows)
