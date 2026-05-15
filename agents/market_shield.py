"""Market Shield — SPY/QQQ/VIX holati bo‘yicha long-only BUY gate (BULL / NEUTRAL / RISK_OFF / NEWS_LOCK)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

from agents.indicators import cumulative_session_vwap, ema


def _truthy(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip(), 10)
    except ValueError:
        return default


def market_shield_enabled() -> bool:
    return _truthy("MARKET_SHIELD_ENABLED", default=True)


def _high_beta_tickers() -> set[str]:
    raw = os.getenv(
        "MARKET_SHIELD_HIGH_BETA_TICKERS",
        "NVDA,TSLA,PLTR,SOFI,AMD,COIN,MARA,RIOT,SMCI,ARM,IONQ,RKLB",
    )
    return {t.strip().upper() for t in raw.split(",") if t.strip()}


def _symbol_keys() -> tuple[str, str, str]:
    spy = os.getenv("MARKET_SHIELD_SPY", "SPY").strip().upper() or "SPY"
    qqq = os.getenv("MARKET_SHIELD_QQQ", "QQQ").strip().upper() or "QQQ"
    vix = os.getenv("MARKET_SHIELD_VIX", "^VIX").strip() or "^VIX"
    return spy, qqq, vix


def _intraday_tf_minutes() -> int:
    try:
        return max(1, min(60, int(os.getenv("MARKET_SHIELD_TIMEFRAME_MINUTES", os.getenv("INTRADAY_TIMEFRAME_MINUTES", "5")))))
    except ValueError:
        return 5


def _analyze_index_bars(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Oxirgi sham: close, VWAP, EMA20, kunlik % (birinchi bar open ≈ day open proxy)."""

    if len(bars) < 25:
        return {"ok": False, "reason": "insufficient_bars"}

    closes = [float(b.get("c") or 0) for b in bars]
    vwaps = cumulative_session_vwap(bars)
    ema20 = ema(closes, 20)

    i = len(bars) - 1
    close = closes[i]
    vwap = vwaps[i]
    e20 = ema20[i]
    day_open = float(bars[0].get("o") or bars[0].get("c") or 0)
    day_pct = ((close - day_open) / day_open * 100.0) if day_open > 0 else 0.0

    above_vwap = vwap is not None and close > float(vwap)
    above_ema20 = e20 is not None and close > float(e20)

    return {
        "ok": True,
        "close": round(close, 4),
        "vwap": round(float(vwap), 4) if vwap is not None else None,
        "ema20": round(float(e20), 4) if e20 is not None else None,
        "day_pct": round(day_pct, 3),
        "above_vwap": above_vwap,
        "above_ema20": above_ema20,
        "bull": bool(above_vwap and above_ema20),
    }


def _analyze_vix_bars(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(bars) < 12:
        return {"ok": False, "reason": "insufficient_bars"}

    closes = [float(b.get("c") or 0) for b in bars]
    ema9 = ema(closes, 9)
    i = len(bars) - 1
    close = closes[i]
    e9 = ema9[i]
    day_open = float(bars[0].get("o") or bars[0].get("c") or 0)
    day_pct = ((close - day_open) / day_open * 100.0) if day_open > 0 else 0.0
    prev = closes[i - 1] if i > 0 else close
    rising = close > prev and (e9 is None or close > float(e9))

    calm = e9 is not None and close <= float(e9) and not rising

    return {
        "ok": True,
        "close": round(close, 4),
        "ema9": round(float(e9), 4) if e9 is not None else None,
        "day_pct": round(day_pct, 3),
        "calm": calm,
        "rising": rising,
        "below_ema9": e9 is not None and close <= float(e9),
    }


def classify_regime(
    spy: Dict[str, Any],
    qqq: Dict[str, Any],
    vix: Dict[str, Any],
) -> Tuple[str, Dict[str, bool]]:
    """Regime + flaglar."""

    spy_bull = bool(spy.get("bull"))
    qqq_bull = bool(qqq.get("bull"))
    vix_calm = bool(vix.get("calm"))
    vix_rising = bool(vix.get("rising"))

    spy_day = float(spy.get("day_pct") or 0)
    qqq_day = float(qqq.get("day_pct") or 0)
    vix_day = float(vix.get("day_pct") or 0)
    vix_close = float(vix.get("close") or 0)

    spy_lock_pct = _env_float("MARKET_SHIELD_SPY_NEWS_LOCK_PCT", -1.0)
    qqq_lock_pct = _env_float("MARKET_SHIELD_QQQ_NEWS_LOCK_PCT", -1.2)
    vix_lock_pct = _env_float("MARKET_SHIELD_VIX_NEWS_LOCK_PCT", 10.0)
    vix_level_lock = _env_float("MARKET_SHIELD_VIX_LEVEL_LOCK", 25.0)

    news_lock = (
        spy_day <= spy_lock_pct
        or qqq_day <= qqq_lock_pct
        or vix_day >= vix_lock_pct
        or (vix_close >= vix_level_lock and vix_close > 0)
    )
    if news_lock:
        return "NEWS_LOCK", {
            "market_ok_for_long": False,
            "market_watch_only": False,
            "market_blocked": True,
        }

    bull = spy_bull and qqq_bull and vix_calm
    if bull:
        return "BULL", {
            "market_ok_for_long": True,
            "market_watch_only": False,
            "market_blocked": False,
        }

    risk_off = (not spy_bull or not qqq_bull) and vix_rising
    if risk_off:
        return "RISK_OFF", {
            "market_ok_for_long": False,
            "market_watch_only": False,
            "market_blocked": True,
        }

    neutral_watch = (spy_bull or qqq_bull) and vix_day < vix_lock_pct
    if neutral_watch:
        return "NEUTRAL", {
            "market_ok_for_long": False,
            "market_watch_only": True,
            "market_blocked": False,
        }

    return "NEUTRAL", {
        "market_ok_for_long": False,
        "market_watch_only": True,
        "market_blocked": False,
    }


def build_market_shield_snapshot(market_data: Any) -> Dict[str, Any]:
    """Skan boshida bir marta: SPY/QQQ/VIX intraday + regime."""

    if not market_shield_enabled():
        return {
            "market_shield_enabled": False,
            "market_regime": "OFF",
            "market_ok_for_long": True,
            "market_watch_only": False,
            "market_blocked": False,
        }

    spy_sym, qqq_sym, vix_sym = _symbol_keys()
    tf = _intraday_tf_minutes()
    try:
        lb = max(2, min(30, int(os.getenv("MARKET_SHIELD_LOOKBACK_DAYS", os.getenv("INTRADAY_LOOKBACK_DAYS", "5")))))
    except ValueError:
        lb = 5

    def _bars(sym: str) -> List[Dict[str, Any]]:
        try:
            return market_data.fetch_intraday_bars(sym, timeframe_minutes=tf, lookback_calendar_days=lb) or []
        except Exception:
            return []

    spy_bars = _bars(spy_sym)
    qqq_bars = _bars(qqq_sym)
    vix_bars = _bars(vix_sym)
    if not vix_bars and vix_sym.startswith("^"):
        vix_bars = _bars("VIX")

    spy = _analyze_index_bars(spy_bars)
    qqq = _analyze_index_bars(qqq_bars)
    vix = _analyze_vix_bars(vix_bars)

    if not spy.get("ok") or not qqq.get("ok"):
        return {
            "market_shield_enabled": True,
            "market_shield_data_ok": False,
            "market_regime": "UNKNOWN",
            "market_ok_for_long": True,
            "market_watch_only": False,
            "market_blocked": False,
            "market_shield_note": "SPY/QQQ barlar yetarli emas — shield o‘tkazildi.",
            "market_shield_spy": spy,
            "market_shield_qqq": qqq,
            "market_shield_vix": vix,
        }

    regime, flags = classify_regime(spy, qqq, vix)

    min_score_bull = _env_int("MARKET_SHIELD_MIN_SCORE_BULL", 70)
    min_score_neutral = _env_int("MARKET_SHIELD_MIN_SCORE_NEUTRAL", 80)

    summary_line = (
        f"Market {regime}: SPY {spy.get('day_pct')}% "
        f"({'↑VWAP+EMA20' if spy.get('bull') else '↓'}) · "
        f"QQQ {qqq.get('day_pct')}% · "
        f"VIX {vix.get('close') or '—'} ({'calm' if vix.get('calm') else 'rising' if vix.get('rising') else '—'})"
    )

    return {
        "market_shield_enabled": True,
        "market_shield_data_ok": True,
        "market_regime": regime,
        "market_ok_for_long": flags["market_ok_for_long"],
        "market_watch_only": flags["market_watch_only"],
        "market_blocked": flags["market_blocked"],
        "market_shield_min_score": min_score_bull if regime == "BULL" else min_score_neutral,
        "market_shield_min_score_bull": min_score_bull,
        "market_shield_min_score_neutral": min_score_neutral,
        "market_shield_summary_line": summary_line,
        "market_shield_spy": spy,
        "market_shield_qqq": qqq,
        "market_shield_vix": vix,
        "market_shield_json": json.dumps(
            {"regime": regime, "spy": spy, "qqq": qqq, "vix": vix, **flags},
            default=str,
        ),
    }


def _relative_strength_ok(signal: Dict[str, Any], shield: Dict[str, Any]) -> bool:
    """SPY qizil, lekin stock yashil + kuchli RVOL."""

    spy = shield.get("market_shield_spy") or {}
    if float(spy.get("day_pct") or 0) >= 0:
        return False
    try:
        stock_chg = float(signal.get("change_percent") or 0)
    except (TypeError, ValueError):
        stock_chg = 0.0
    if stock_chg <= 0:
        return False
    try:
        rvol = float(signal.get("rvol") or 0)
    except (TypeError, ValueError):
        rvol = 0.0
    min_rvol = _env_float("MARKET_SHIELD_RS_MIN_RVOL", 2.0)
    return rvol >= min_rvol and bool(signal.get("amt_buy_signal") or signal.get("strategy_pass"))


def apply_market_shield_to_signal(signal: Dict[str, Any], shield: Dict[str, Any]) -> Dict[str, Any]:
    """Signalga regime, blok va skor talablarini yozadi."""

    if not shield.get("market_shield_enabled"):
        return signal

    out = dict(signal)
    regime = str(shield.get("market_regime") or "UNKNOWN")
    out["market_regime"] = regime
    out["market_shield_summary_line"] = shield.get("market_shield_summary_line")
    out["market_ok_for_long"] = shield.get("market_ok_for_long")
    out["market_watch_only"] = shield.get("market_watch_only")
    out["market_blocked"] = shield.get("market_blocked")

    ticker = str(out.get("ticker") or "").upper()
    beta_high = ticker in _high_beta_tickers()
    try:
        beta_val = float(out.get("beta") or 0)
        if beta_val >= 1.5:
            beta_high = True
        if beta_val >= 2.0 and bool((shield.get("market_shield_vix") or {}).get("rising")):
            out["market_shield_buy_blocked"] = True
            out["market_shield_block_reason"] = f"High beta ({beta_val}) + VIX rising — BUY blocked."
            return out
    except (TypeError, ValueError):
        pass

    spy = shield.get("market_shield_spy") or {}
    spy_red = float(spy.get("day_pct") or 0) < 0

    risk_mult = 1.0
    if beta_high and spy_red and regime != "BULL":
        risk_mult = 0.5
    out["market_shield_risk_multiplier"] = risk_mult

    score = 0.0
    try:
        score = float(out.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0

    min_score = int(shield.get("market_shield_min_score") or 70)
    buy_blocked = False
    block_reason = ""

    if regime == "NEWS_LOCK":
        buy_blocked = True
        block_reason = "Market Shield NEWS_LOCK — yangi long yo‘q."
    elif regime == "RISK_OFF":
        buy_blocked = True
        block_reason = "Market Shield RISK_OFF — SPY/QQQ past, VIX ko‘tarilmoqda."
        if _relative_strength_ok(out, shield):
            out["market_shield_relative_strength"] = True
            block_reason = "RISK_OFF — faqat relative-strength WATCH (BUY blok)."
    elif regime == "NEUTRAL":
        if score < min_score:
            buy_blocked = True
            block_reason = f"NEUTRAL — skor {score:.0f} < {min_score} (faqat kuchli setup)."
        else:
            out["market_shield_neutral_allow"] = True
    elif regime == "BULL":
        if score < min_score:
            buy_blocked = True
            block_reason = f"BULL — skor {score:.0f} < {min_score}."
    elif regime == "UNKNOWN":
        pass

    if bool(shield.get("market_shield_data_ok")) and regime == "BULL":
        if not bool(spy.get("bull")) and bool((shield.get("market_shield_vix") or {}).get("rising")):
            buy_blocked = True
            block_reason = "SPY VWAP/EMA20 ostida va VIX ko‘tarilmoqda."

    if buy_blocked:
        out["market_shield_buy_blocked"] = True
        out["market_shield_block_reason"] = block_reason
        failed = list(out.get("failed_rules") or [])
        if "market_shield" not in failed:
            failed.append("market_shield")
        out["failed_rules"] = failed
        if out.get("strategy_pass"):
            out["market_shield_strategy_note"] = block_reason

    return out


def market_shield_blocks_paper(signal: Dict[str, Any], shield: Dict[str, Any] | None = None) -> Tuple[bool, str]:
    """RiskManager / paper uchun qisqa tekshiruv."""

    sh = shield or signal
    if not sh.get("market_shield_enabled", market_shield_enabled()):
        return False, ""

    regime = str(signal.get("market_regime") or sh.get("market_regime") or "")
    if regime == "NEWS_LOCK":
        return True, "Market Shield NEWS_LOCK — paper long blok."

    if bool(signal.get("market_shield_buy_blocked")):
        return True, str(signal.get("market_shield_block_reason") or "Market Shield BUY blocked.")

    if regime == "RISK_OFF" and not signal.get("market_shield_relative_strength"):
        return True, "Market Shield RISK_OFF — long blok."

    return False, ""
