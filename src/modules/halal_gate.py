from __future__ import annotations

from typing import Optional

from src.config.settings import JarvisSettings, get_settings
from src.models.schemas import HalalReport


def halal_report_to_dict(report: HalalReport | None) -> Optional[dict]:
    if report is None:
        return None
    return report.model_dump()


def apply_halal_gate(
    zoya_report: HalalReport | dict | None,
    ratios: dict | None = None,
    *,
    settings: JarvisSettings | None = None,
) -> tuple[bool, list[str]]:
    """
    MASTER_PLAN: Zoya + ixtiyoriy fundamentals (debt / impure revenue).

    `zoya_report` dict bo‘lsa: `status` kaliti kutiladi (backward compat).
    """
    cfg = settings or get_settings()
    reasons: list[str] = []

    max_debt = float(cfg.halal_max_debt_ratio)
    max_impure = float(cfg.halal_max_impure_rev)

    if zoya_report is not None:
        if isinstance(zoya_report, HalalReport):
            status = zoya_report.status
            raw_lower = (zoya_report.detail or "").lower()
        else:
            status = str(zoya_report.get("status", "unknown")).lower()
            raw_lower = status
        if status == "non_compliant" or raw_lower in {"non-compliant", "non_compliant", "haram"}:
            return False, ["Zoya: NON_COMPLIANT"]
        if status == "questionable":
            reasons.append("Zoya: questionable — qo'lda ko'rilsin")

    if ratios:
        debt = float(ratios.get("debt_ratio", 0))
        impure = float(ratios.get("impure_revenue_pct", 0))
        cash = float(ratios.get("cash_ratio", 0))
        max_cash = float(getattr(cfg, "halal_max_cash_ratio", 0.30))
        if debt > max_debt:
            return False, [f"Debt ratio yuqori: {debt:.1%} > {max_debt:.0%} (SS21-style)"]
        if cash > max_cash:
            return False, [f"Cash + foizli qimmatliklar: {cash:.1%} > {max_cash:.0%} (SS21-style)"]
        if impure > max_impure:
            return False, [f"Impure revenue: {impure:.1%} > {max_impure:.0%} (SS21-style)"]

    return True, reasons or ["Halal gate: PASSED"]
