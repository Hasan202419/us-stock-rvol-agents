"""Professional trade-plan matni: LLM `trade_plan` obyektidan yoki signal maydonlaridan (fallback)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

# LLM JSON `trade_plan` kalitlari (inglizcha bo‘limlar bilan mos).
TRADE_PLAN_KEYS: tuple[str, ...] = (
    "company",
    "reason_catalyst",
    "fundamental_analysis",
    "technical_analysis",
    "prediction",
    "risk_analysis",
    "entry_price",
    "stop_loss",
    "target_price",
    "risk_reward_ratio",
    "position_size_example",
    "execution_plan",
    "final_trade_summary",
)

# LLM / boshqa agentlar ba'zan canonical emas kalit yuboradi.
_TRADE_PLAN_ALIASES: dict[str, str] = {
    "entry_px": "entry_price",
    "entry": "entry_price",
    "stop_px": "stop_loss",
    "sl": "stop_loss",
    "target_px": "target_price",
    "tp": "target_price",
    "take_profit": "target_price",
}


def parse_trade_plan_dict(raw: Any) -> Dict[str, str]:
    """`trade_plan` JSON qatori yoki dict; alias kalitlar canonical nomlarga map qilinadi."""
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("{"):
            try:
                parsed = json.loads(s)
            except (json.JSONDecodeError, TypeError):
                return {}
            return parse_trade_plan_dict(parsed)
    if not isinstance(raw, dict):
        return {}

    data: Dict[str, str] = {k: str(raw.get(k, "") or "").strip() for k in TRADE_PLAN_KEYS}
    for alias, canon in _TRADE_PLAN_ALIASES.items():
        if not data.get(canon) and raw.get(alias) is not None:
            data[canon] = str(raw.get(alias) or "").strip()
    return data


def format_trade_plan_markdown(ticker: str, tp: Dict[str, str]) -> str:
    """Foydalanuvchi so‘ragan sarlavhalar tartibida Markdown."""

    def line(label: str, key: str) -> str:
        v = (tp.get(key) or "").strip()
        if not v:
            return f"**{label}** — —"
        return f"**{label}**\n{v}"

    parts: List[str] = [
        f"**Ticker**\n{ticker}",
        line("Company", "company"),
        line("Reason (Catalyst)", "reason_catalyst"),
        "**Fundamental Analysis**",
        (tp.get("fundamental_analysis") or "—").strip() or "—",
        "**Technical Analysis**",
        (tp.get("technical_analysis") or "—").strip() or "—",
        line("Prediction", "prediction"),
        line("Risk Analysis", "risk_analysis"),
        "**Trading Setup**",
        "\n".join(
            [
                f"- Entry: {tp.get('entry_price') or '—'}",
                f"- Stop Loss: {tp.get('stop_loss') or '—'}",
                f"- Target: {tp.get('target_price') or '—'}",
                f"- Risk/Reward: {tp.get('risk_reward_ratio') or '—'}",
                f"- Position size example: {tp.get('position_size_example') or '—'}",
            ]
        ),
        line("Execution Plan", "execution_plan"),
        line("Final Trade Summary", "final_trade_summary"),
    ]
    return "\n\n".join(parts)


def trade_plan_dict_has_content(tp: Dict[str, str]) -> bool:
    return any(bool((tp.get(k) or "").strip()) for k in TRADE_PLAN_KEYS)


def deterministic_trade_plan_from_signal(signal: Dict[str, Any], *, lang: str = "en") -> str:
    """LLM yo‘q yoki `trade_plan` bo‘sh bo‘lsa — mavjud signal maydonlaridan qisqa professional reja."""

    ticker = str(signal.get("ticker") or "?").upper()
    price = signal.get("price")
    if bool(signal.get("trade_levels_ok")):
        entry_px = signal.get("trade_entry_price")
        sl = signal.get("trade_stop_loss")
        tp = signal.get("trade_tp1")
        tp2 = signal.get("trade_tp2")
    else:
        entry_px = None
        tp2 = None
        sl = signal.get("stop_suggestion")
        tp = signal.get("take_profit_suggestion")
    try:
        px = f"{float(entry_px if entry_px is not None else price):.4f}"
    except (TypeError, ValueError):
        px = "—"
    try:
        sl_s = f"{float(sl):.4f}" if sl is not None else "—"
    except (TypeError, ValueError):
        sl_s = "—"
    try:
        tp_s = f"{float(tp):.4f}" if tp is not None else "—"
    except (TypeError, ValueError):
        tp_s = "—"
    rvol = signal.get("rvol")
    try:
        rv = f"{float(rvol):.2f}" if rvol is not None else "—"
    except (TypeError, ValueError):
        rv = "—"

    vol_pat = str(signal.get("volume_pattern_summary") or "").strip()
    stage = str(signal.get("ignition_trend_stage") or "").strip()
    dist = signal.get("ignition_distance_to_resistance_pct")
    cont = signal.get("ignition_continuation_probability")
    strat = str(signal.get("strategy_name") or "").strip()
    reason = str(signal.get("chatgpt_reason") or "").strip()
    entry_c = str(signal.get("chatgpt_entry_condition") or "").strip()
    outline = str(signal.get("ignition_professional_outline") or "").strip()

    rr_txt = "—"
    rr2_txt = ""
    if signal.get("trade_rr_tp1") is not None:
        rr_txt = f"{signal.get('trade_rr_tp1')}:1 (TP1)"
    if signal.get("trade_rr_tp2") is not None:
        rr2_txt = f" · TP2 R:R≈{signal.get('trade_rr_tp2')}:1"
    if rr_txt == "—":
        try:
            p = float(entry_px if entry_px is not None else price)
            s = float(sl)
            t = float(tp)
            if p > s > 0 and t > p:
                rr_txt = f"{(t - p) / (p - s):.2f}:1 (approx. to target vs stop)"
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    trade_note = str(signal.get("trade_entry_note") or "").strip()
    trade_exit = str(signal.get("trade_exit_rule") or "").strip()
    levels_line = str(signal.get("trade_levels_line") or "").strip()
    try:
        tp2_s = f"{float(tp2):.4f}" if tp2 is not None else ""
    except (TypeError, ValueError):
        tp2_s = ""

    if lang.lower().startswith("uz"):
        setup_block = ""
        if levels_line:
            setup_block = f"**Skalp / day trade (avtomatik)**\n{levels_line}\n"
            if trade_note:
                setup_block += f"Kirish: {trade_note}\n"
            if trade_exit:
                setup_block += f"{trade_exit}\n"
            if tp2_s:
                setup_block += f"Chiqish2 (kuchli zona): {tp2_s}\n"
            setup_block += "\n"
        body = (
            f"**Ticker**\n{ticker}\n\n"
            f"**Narx / kirish**\n{px}\n\n"
            f"{setup_block}"
            f"**Strategiya**\n{strat or '—'}\n\n"
            f"**RVOL**\n{rv}\n\n"
            f"**Kirish (shart)**\n{entry_c or trade_note or reason or '—'}\n\n"
            f"**SL / TP**\nSL: {sl_s} · TP1: {tp_s} · R:R ≈ {rr_txt}{rr2_txt}\n\n"
        )
        if vol_pat:
            body += f"**Hajm**\n{vol_pat}\n\n"
        if stage or dist is not None:
            body += f"**Ignition**\nBosqich: {stage or '—'} · R masofa %: {dist}\n\n"
        if cont is not None:
            body += f"**Davom ehtimoli (model)**\n{cont}\n\n"
        if outline:
            body += f"**6 bo‘lim (skaner)**\n{outline}"
        return body.strip()

    setup_en = ""
    if levels_line:
        setup_en = (
            f"**Scalp / day trade (auto)**\n{levels_line}\n"
            f"{(trade_note + chr(10)) if trade_note else ''}"
            f"{(trade_exit + chr(10)) if trade_exit else ''}"
            f"{('TP2: ' + tp2_s + chr(10)) if tp2_s else ''}\n"
        )
    body = (
        f"**Ticker**\n{ticker}\n\n"
        f"{setup_en}"
        f"**Company**\n— (add manually or enable LLM with Finnhub for context)\n\n"
        f"**Reason (Catalyst)**\n{reason or 'Scan-based setup; verify catalysts independently.'}\n\n"
        f"**Technical setup**\n"
        f"- Strategy: {strat or '—'}\n"
        f"- Price: {px} · RVOL: {rv}\n"
    )
    if vol_pat:
        body += f"- Volume: {vol_pat}\n"
    if stage or dist is not None:
        body += f"- Trend stage: {stage or '—'} · Distance to resistance (%): {dist}\n"
    if cont is not None:
        body += f"- Continuation probability (model): {cont}\n"
    body += (
        f"\n**Entry / risk / targets**\n"
        f"- Entry condition: {entry_c or 'See strategy rules; wait for confirmation.'}\n"
        f"- Stop loss: {sl_s}\n"
        f"- Target (TP1): {tp_s}\n"
        f"{(f'- Target (TP2): {tp2_s}' + chr(10)) if tp2_s else ''}"
        f"- Risk/Reward (approx.): {rr_txt}{rr2_txt}\n"
        f"- Position size: size from risk budget (see RiskManager / dashboard).\n\n"
        f"**Execution**\n"
        f"Wait for price/volume confirmation; set stop immediately; manage at resistance.\n"
    )
    if outline:
        body += f"\n**Scanner outline**\n{outline}"
    return body.strip()


def analyst_trade_plan_for_signal(
    signal: Dict[str, Any],
    analyst_view: Dict[str, Any],
    *,
    trade_plan_enabled: bool,
) -> tuple[Dict[str, str], str]:
    """(trade_plan_dict, markdown_text) — LLM yoki deterministik."""

    tp = parse_trade_plan_dict(analyst_view.get("trade_plan"))
    ticker = str(signal.get("ticker") or "?").upper()
    if trade_plan_enabled and trade_plan_dict_has_content(tp):
        return tp, format_trade_plan_markdown(ticker, tp)
    md = deterministic_trade_plan_from_signal(
        signal,
        lang=os.getenv("ANALYST_TRADE_PLAN_LANG", "en"),
    )
    return tp, md

