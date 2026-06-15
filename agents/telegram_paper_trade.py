"""Telegram /paper — oxirgi skan yoki qisqa skandan Alpaca paper buyurtma."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agents.scan_pipeline import (
    SidebarControls,
    build_scan_agents,
    fetch_universe_for_scan,
    run_scan_market,
    telegram_default_controls,
)


def _truthy(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def paper_trading_enabled() -> bool:
    return _truthy("TELEGRAM_PAPER_TRADING_ENABLED", default=True)


def parse_json_list(blob: Any) -> List[str]:
    if blob is None:
        return []
    if isinstance(blob, list):
        return [str(x) for x in blob]
    try:
        out = json.loads(str(blob))
        return [str(x) for x in out] if isinstance(out, list) else []
    except json.JSONDecodeError:
        return []


def analyst_view_from_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "decision": signal.get("chatgpt_decision"),
        "risk_level": signal.get("risk_level"),
        "allow_order": signal.get("chatgpt_allow_order", False),
        "risk_flags_hard": parse_json_list(signal.get("chatgpt_risk_flags_hard_json")),
        "paper_ready_blocked": signal.get("paper_ready_blocked_field"),
        "reason": signal.get("chatgpt_reason"),
    }


def default_stop_take_profit(signal: Dict[str, Any]) -> Tuple[float, float]:
    price = float(signal.get("price") or 0)
    stop = signal.get("stop_suggestion")
    tp = signal.get("take_profit_suggestion")
    if stop is not None:
        stop_f = float(stop)
    elif price > 0:
        stop_f = round(price * 0.97, 4)
    else:
        stop_f = 0.01
    if tp is not None:
        tp_f = float(tp)
    elif price > 0:
        tp_f = round(price * 1.04, 4)
    else:
        tp_f = 0.01
    return stop_f, tp_f


def build_order_from_signal(
    signal: Dict[str, Any],
    risk: Any,
) -> Tuple[Dict[str, Any], int, str]:
    qty, sizing_note = risk.suggest_quantity(signal)
    stop_f, tp_f = default_stop_take_profit(signal)
    quantity = max(1, int(qty)) if qty and qty > 0 else 1
    order = {
        "quantity": quantity,
        "stop_loss": stop_f,
        "take_profit": tp_f,
    }
    return order, quantity, sizing_note


def pick_paper_signal(
    rows: List[Dict[str, Any]],
    *,
    ticker: str | None = None,
) -> Dict[str, Any] | None:
    ready = [r for r in rows if isinstance(r, dict) and r.get("paper_trade_ready")]
    if ticker:
        want = ticker.strip().upper()
        ready = [r for r in ready if str(r.get("ticker", "")).upper() == want]
    if not ready:
        return None
    ready.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    return ready[0]


def load_last_scan_signals(state_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not state_path.is_file():
        return [], {}
    try:
        blob = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], {}
    rows = blob.get("top_signals") or []
    summary = blob.get("summary") if isinstance(blob.get("summary"), dict) else {}
    if not isinstance(rows, list):
        rows = []
    return [r for r in rows if isinstance(r, dict)], summary


def run_quick_paper_scan(repo_root: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    max_sym = int(os.getenv("TELEGRAM_PAPER_SCAN_MAX_SYMBOLS", "80") or "80")
    max_sym = max(10, min(max_sym, 400))
    ctrls = telegram_default_controls()
    ctrls = SidebarControls(
        desk_label=f"{ctrls.desk_label} paper",
        max_symbols=max_sym,
        preset_name=ctrls.preset_name,
        rvol_thresholds=dict(ctrls.rvol_thresholds),
        max_workers=min(ctrls.max_workers, 12),
        finviz_csv_universe=False,
    )
    tickers = fetch_universe_for_scan(ctrls)
    ranked, _views, summary = run_scan_market(tickers, ctrls, repo_root=repo_root, progress=None)
    return ranked, summary


def execute_paper_trade(
    signal: Dict[str, Any],
    *,
    repo_root: Path,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Paper buyurtma. `dry_run=True` — sizing + risk + buyurtma quriladi, lekin Alpaca'ga
    YUBORILMAYDI (jonli oqimni xavfsiz sinash uchun)."""

    agents = build_scan_agents(repo_root)
    ticker = str(signal.get("ticker") or "?").upper()
    analyst_view = analyst_view_from_signal(signal)
    order, quantity, sizing_note = build_order_from_signal(signal, agents["risk"])
    approved, risk_reason = agents["risk"].approve_order(signal, analyst_view, order)

    price = float(signal.get("price") or 0)
    risk_per_share = max(0.0, price - float(order["stop_loss"])) if price else 0.0
    reward_per_share = max(0.0, float(order["take_profit"]) - price) if price else 0.0
    result: Dict[str, Any] = {
        "ticker": ticker,
        "quantity": quantity,
        "stop_loss": order["stop_loss"],
        "take_profit": order["take_profit"],
        "price": price,
        "risk_approved": approved,
        "risk_reason": risk_reason,
        "sizing_note": sizing_note,
        "dry_run": bool(dry_run),
        "notional": round(price * quantity, 2) if price else 0.0,
        "est_risk_usd": round(risk_per_share * quantity, 2),
        "est_reward_usd": round(reward_per_share * quantity, 2),
        "rr_ratio": round(reward_per_share / risk_per_share, 2) if risk_per_share > 0 else 0.0,
        "paper_trade_ready": bool(signal.get("paper_trade_ready")),
        "paper_trade_block_reason": str(signal.get("paper_trade_block_reason") or ""),
    }

    if not approved:
        result["submitted"] = False
        result["status"] = "BLOCKED"
        result["message"] = risk_reason
        return result

    if dry_run:
        result["submitted"] = False
        result["status"] = "DRY_RUN"
        result["message"] = (
            "Sinov (dry-run): buyurtma Alpaca'ga yuborilmadi. "
            "Haqiqiy yuborish uchun: /paper go yoki /paper " + ticker
        )
        return result

    trade_result = agents["trader"].submit_order(
        ticker,
        int(quantity),
        float(order["stop_loss"]),
        True,
        take_profit=float(order["take_profit"]),
    )
    result.update(trade_result)
    poll = agents["trader"].fetch_order(str(trade_result.get("order_id") or ""))
    if poll:
        result["alpaca_poll_status"] = poll.get("status")
        result["filled_qty"] = poll.get("filled_qty")
        result["filled_avg_price"] = poll.get("filled_avg_price")

    if trade_result.get("submitted"):
        agents["logger"].save_trade(
            {
                "ticker": ticker,
                "quantity": int(quantity),
                "price": result["price"],
                "stop_loss": float(order["stop_loss"]),
                "take_profit": float(order["take_profit"]),
                "risk_approved": True,
                "risk_reason": risk_reason,
                "alpaca_status": trade_result.get("status"),
                "alpaca_order_id": trade_result.get("order_id", ""),
                "message": trade_result.get("message"),
                "submitted_at": trade_result.get("submitted_at"),
                "realized_pnl": 0,
            }
        )
    return result


def format_paper_result_html(result: Dict[str, Any]) -> str:
    t = result.get("ticker", "?")
    status = result.get("status", "—")
    submitted = result.get("submitted")
    title = "Paper sinov (dry-run)" if result.get("dry_run") else "Paper savdo"
    lines = [
        f"<b>{title}</b> · <code>{t}</code>",
        f"Holat: <b>{status}</b> · yuborildi: <code>{'ha' if submitted else 'yo‘q'}</code>",
    ]
    if result.get("quantity"):
        lines.append(
            f"Miqdor: <code>{result.get('quantity')}</code> · SL <code>{result.get('stop_loss')}</code> "
            f"· TP <code>{result.get('take_profit')}</code>"
        )
        notional = result.get("notional")
        rr = result.get("rr_ratio")
        if notional:
            risk_usd = result.get("est_risk_usd")
            reward_usd = result.get("est_reward_usd")
            lines.append(
                f"Hajm: <code>${notional}</code> · risk <code>${risk_usd}</code> "
                f"· reward <code>${reward_usd}</code> · R:R <code>{rr}</code>"
            )
    if result.get("order_id"):
        lines.append(f"Alpaca order: <code>{result.get('order_id')}</code>")
    if result.get("alpaca_poll_status"):
        lines.append(
            f"Poll: <code>{result.get('alpaca_poll_status')}</code>"
            f" · filled {result.get('filled_qty') or '—'}"
        )
    msg = str(result.get("message") or result.get("risk_reason") or "").strip()
    if msg:
        lines.append(f"<i>{msg}</i>")
    if not result.get("paper_trade_ready"):
        block = str(result.get("paper_trade_block_reason") or "").strip()
        if block:
            lines.append(f"Paper-ready: yo‘q — {block}")
    return "\n".join(lines)


def paper_help_html() -> str:
    return (
        "<b>/paper</b> — Alpaca <i>paper</i> buyurtma\n"
        "• <code>/paper</code> yoki <code>/paper go</code> — oxirgi skandagi eng yaxshi paper-ready signal\n"
        "• <code>/paper AAPL</code> — shu ticker (oxirgi skan)\n"
        "• <code>/paper scan</code> — qisqa skan (~80 ticker), keyin paper-ready bo‘lsa buyurtma\n"
        "• <code>/paper preview</code> yoki <code>/paper preview AAPL</code> — <b>sinov</b>: sizing+risk+R:R "
        "ko‘rsatiladi, lekin Alpaca'ga yuborilmaydi\n"
        "RiskManager + AI ruxsati shart; blok bo‘lsa sabab chiqadi.\n"
        "<code>TELEGRAM_PAPER_TRADING_ENABLED=false</code> — o‘chirish."
    )
