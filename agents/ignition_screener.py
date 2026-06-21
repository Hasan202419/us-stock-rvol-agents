"""Volume Ignition Screener — ko'p US stockni skanlab, erta bullish momentum topadi.

Foydalanuvchi frameworki: "abnormal volume expansion before breakout". Har ticker uchun
`_yf_snapshot` (yfinance) candles oladi → `evaluate_bullish_buy` (VolumeIgnitionStrategyAgent
mezonlari + qat'iy BUY/WATCH/AVOID) ishlaydi → ignition formatida natija:

  Ticker · Price · Volume pattern · RVOL · Distance to resistance ·
  Trend stage (Accumulation/Ignition/Breakout) · Entry zone ·
  Continuation probability · Risk level + BUY verdikti.

Tarmoqqa bog'liq (yfinance) — Render'da ishlaydi. Testlarda `_yf_snapshot` mock qilinadi.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from agents.bullish_buy_signal import (
    evaluate_bullish_buy,
    format_bullish_buy_report,
    verdict_badge,
)
from agents.yfinance_screener import SCALP_UNIVERSE_DEFAULT, _tv_url, _yf_snapshot


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _esc(s: Any) -> str:
    text = "" if s is None else str(s)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def evaluate_ignition_for_snapshot(snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Bitta snapshot (candles bilan) uchun ignition + BUY natijasini chiqaradi."""
    candles = snap.get("candles")
    if not isinstance(candles, list) or len(candles) < 10:
        return None
    sig = {
        "ticker": snap.get("ticker"),
        "price": snap.get("price"),
        "rvol": snap.get("rvol"),
        "avg_volume": snap.get("avg_volume"),
        "volume": snap.get("volume"),
        "candles": candles,
    }
    res = evaluate_bullish_buy(sig)
    s = res.get("_signal") or {}
    return {
        "ticker": res.get("ticker"),
        "price": snap.get("price"),
        "rvol": s.get("rvol") if s.get("rvol") is not None else snap.get("rvol"),
        "volume_pattern": s.get("volume_pattern_summary"),
        "distance_to_resistance_pct": s.get("ignition_distance_to_resistance_pct"),
        "trend_stage": s.get("ignition_trend_stage"),
        "entry_zone_low": s.get("ignition_entry_zone_low"),
        "entry_zone_high": s.get("ignition_entry_zone_high"),
        "continuation_probability": s.get("ignition_continuation_probability"),
        "risk_level": s.get("ignition_risk_level"),
        "strategy_pass": bool(s.get("strategy_pass")),
        "verdict": res.get("verdict"),
        "confidence": res.get("confidence"),
        "criteria_passed": res.get("criteria_passed"),
        "criteria_total": res.get("criteria_total"),
        "entry": res.get("entry"),
        "stop": res.get("stop"),
        "target": res.get("target"),
        "rr": res.get("rr"),
        "tv_url": snap.get("tv_url") or _tv_url(str(res.get("ticker") or "")),
        "_buy_result": res,  # to'liq analyst hisobot uchun (format_bullish_buy_report)
        "_company": snap.get("company") or snap.get("company_name") or "",
    }


def _rank_key(row: Dict[str, Any]) -> tuple:
    """Saralash: BUY birinchi, keyin pass, keyin continuation probability, keyin RVOL."""
    verdict_rank = {"BUY": 3, "WATCH": 2, "AVOID": 1}.get(str(row.get("verdict")), 0)
    pass_rank = 1 if row.get("strategy_pass") else 0
    conf = float(row.get("continuation_probability") or 0)
    rvol = float(row.get("rvol") or 0)
    return (verdict_rank, pass_rank, conf, rvol)


def screen_ignition_candidates(
    universe: Optional[List[str]] = None,
    *,
    top_n: int = 10,
    include_watch: bool = True,
    delay_sec: float = 0.15,
) -> List[Dict[str, Any]]:
    """Universe'ni ignition mezonlari bo'yicha skanlaydi.

    include_watch=False bo'lsa faqat BUY qaytadi. Saralash: BUY > WATCH, keyin
    continuation probability va RVOL bo'yicha.
    """
    if universe is None:
        raw = os.getenv("IGNITION_UNIVERSE", os.getenv("SCALP_UNIVERSE", "")).strip()
        if raw:
            universe = [t.strip().upper() for t in raw.split(",") if t.strip()]
        else:
            universe = list(SCALP_UNIVERSE_DEFAULT)

    rows: List[Dict[str, Any]] = []
    for ticker in universe:
        snap = _yf_snapshot(ticker)
        if snap is None:
            continue
        res = evaluate_ignition_for_snapshot(snap)
        if res is None:
            continue
        verdict = str(res.get("verdict"))
        if verdict == "AVOID":
            continue
        if not include_watch and verdict != "BUY":
            continue
        rows.append(res)
        if delay_sec > 0:
            time.sleep(delay_sec)

    rows.sort(key=_rank_key, reverse=True)
    return rows[:top_n]


def format_ignition_html(rows: List[Dict[str, Any]]) -> str:
    """Ignition scanner natijasini Telegram HTML formatida."""
    if not rows:
        return (
            "🔍 <b>Ignition skaner</b>: mezonlarga mos nomzod topilmadi.\n"
            "<i>Hajm portlashi + qarshilikka yaqinlik shartlari qattiq — bu normal.</i>"
        )

    lines = [f"<b>🔥 VOLUME IGNITION SKANER</b> · <b>{len(rows)}</b> nomzod\n"]
    for i, r in enumerate(rows, 1):
        t = _esc(r.get("ticker"))
        badge = verdict_badge(str(r.get("verdict")))
        price = r.get("price")
        rvol = r.get("rvol")
        rvol_txt = f"{float(rvol):.2f}×" if rvol is not None else "—"
        dist = r.get("distance_to_resistance_pct")
        dist_txt = f"{dist}%" if dist is not None else "—"
        stage = _esc(r.get("trend_stage") or "—")
        lo, hi = r.get("entry_zone_low"), r.get("entry_zone_high")
        zone = f"{lo}–{hi}" if (lo is not None and hi is not None) else "—"
        cont = r.get("continuation_probability")
        cont_txt = f"{cont}%" if cont is not None else "—"
        risk = _esc(r.get("risk_level") or "—")
        vol_pat = _esc(r.get("volume_pattern") or "—")
        rr = r.get("rr")
        tv = _esc(r.get("tv_url") or "")

        lines.append(
            f"<b>{i}. {badge}</b> · <code>{t}</code> · ${price}\n"
            f"   📊 RVOL <b>{rvol_txt}</b> · qarshilikка {dist_txt} · bosqich <b>{stage}</b>\n"
            f"   🎯 Kirish zonasi: {zone} · davom ehtimoli <b>{cont_txt}</b>\n"
            f"   🛡️ Risk: {risk}\n"
            f"   📈 Hajm: {vol_pat}\n"
            f"   💹 Entry {r.get('entry')} · SL {r.get('stop')} · TP {r.get('target')} · R:R {rr}\n"
            f"   🔗 <a href=\"{tv}\">TradingView</a>"
        )

    lines.append(
        "\n<i>ℹ️ Kunlik yfinance ma'lumoti. Catalyst/yangilikni alohida tasdiqlang. "
        "Bu avtomatik BUY emas — manual review.</i>"
    )
    return "\n".join(lines)


def format_pro_reports(rows: List[Dict[str, Any]]) -> List[str]:
    """Har nomzod uchun TO'LIQ professional analyst trade plan (master format).

    Ikki frameworkni birlashtiradi: ignition skaner (nomzod topish) + analyst
    tuzilmasi (Reason/Setup/Entry/SL/Target/R:R/Position/Execution/Final Summary).
    Har bir nomzod alohida HTML matn (Telegramda alohida xabar sifatida yuboriladi).
    """
    out: List[str] = []
    for i, r in enumerate(rows, 1):
        full = r.get("_buy_result")
        if not full:
            continue
        company = str(r.get("_company") or "")
        report = format_bullish_buy_report(full, company=company)
        header = f"<b>#{i} — Master tahlil</b>"
        tv = _esc(r.get("tv_url") or "")
        footer = f"\n🔗 <a href=\"{tv}\">TradingView</a>" if tv else ""
        out.append(f"{header}\n{report}{footer}")
    return out


def screen_pro_candidates(
    universe: Optional[List[str]] = None,
    *,
    top_n: int = 5,
    buy_only: bool = True,
    delay_sec: float = 0.15,
) -> List[Dict[str, Any]]:
    """Master skaner: ignition nomzodlari + har biriga to'liq analyst natija (_buy_result)."""
    return screen_ignition_candidates(
        universe, top_n=top_n, include_watch=not buy_only, delay_sec=delay_sec
    )
