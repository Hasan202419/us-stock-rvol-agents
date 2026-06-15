"""Backtest dvigateli — jonli skanerdagi AYNI strategiya kodini tarixda qayta o‘ynatadi.

G‘oya: tarixning har bir kuni `i` uchun `candles[:i+1]` oynasidan snapshot yasab, jonli
skanerdagi `StrategyAgent` / `VolumeIgnitionStrategyAgent` `.evaluate()` ni chaqiramiz
(lookahead yo‘q). `strategy_pass` bo‘lsa kirish yozamiz va oldinga qarab natijani
(target/stop/timeout) o‘lchaymiz. So‘ng statistika: win-rate, o‘rtacha R, expectancy.

Bu modul tarmoqqa chiqmaydi — shamlar (candles) chaqiruvchidan keladi (IBKR yoki yfinance),
shu sabab sof birliklar bilan testlanadi.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from statistics import mean
from typing import Any, Dict, Iterator, List, Optional

from agents.rvol_agent import RVOLAgent
from agents.strategy_agent import StrategyAgent
from agents.strategy_gap_and_go import GapAndGoStrategyAgent
from agents.strategy_volume_ignition import VolumeIgnitionStrategyAgent

# Kunlik strategiyalar (intraday/VWAP bu dvigatelga kirmaydi).
_DAILY_MODES = {"rvol", "rvol_momentum", "volume_ignition", "gap_go", "gap_and_go"}

_rvol_agent = RVOLAgent()


def make_strategy(strategy_mode: str) -> Any:
    """Strategiya rejimiga mos agent (env joriy holatidan o‘qiladi)."""

    mode = (strategy_mode or "rvol").strip().lower()
    if mode == "volume_ignition":
        return VolumeIgnitionStrategyAgent()
    if mode in {"gap_go", "gap_and_go"}:
        return GapAndGoStrategyAgent()
    return StrategyAgent()


def build_snapshot(
    candles: List[Dict[str, Any]],
    i: int,
    *,
    avg_window: int = 20,
    ticker: str = "",
) -> Dict[str, Any]:
    """`candles[:i+1]` oynasidan strategiya kutadigan snapshot. Lookahead yo‘q."""

    window = candles[: i + 1]
    cur = candles[i]
    price = float(cur.get("c") or 0)
    volume = float(cur.get("v") or 0)

    prior_vols = [float(b.get("v") or 0) for b in candles[max(0, i - avg_window):i]]
    avg_volume = mean(prior_vols) if prior_vols else volume

    prev_close = float(candles[i - 1].get("c") or 0) if i >= 1 else price
    change_percent = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0

    snapshot = {
        "ticker": (ticker or str(cur.get("ticker") or "")).upper(),
        "price": round(price, 4),
        "previous_close": round(prev_close, 4),
        "change_percent": round(change_percent, 2),
        "volume": int(volume),
        "avg_volume": int(avg_volume),
        "candles": window,
    }
    return _rvol_agent.calculate(snapshot)


def _entry_stop_target(signal: Dict[str, Any], entry: float) -> tuple[float, float]:
    """Signal taklif qilgan SL/TP; yo‘q bo‘lsa ATR yoki foiz bilan zaxira."""

    stop = signal.get("stop_suggestion")
    target = signal.get("take_profit_suggestion")
    atr = signal.get("daily_atr_14") or signal.get("atr_14")

    stop_f = float(stop) if stop else 0.0
    target_f = float(target) if target else 0.0

    if stop_f <= 0 or stop_f >= entry:
        if atr:
            stop_f = entry - 1.5 * float(atr)
        if stop_f <= 0 or stop_f >= entry:
            stop_f = entry * 0.95
    if target_f <= entry:
        if atr:
            target_f = entry + 3.0 * float(atr)
        if target_f <= entry:
            target_f = entry * 1.10
    return round(stop_f, 4), round(target_f, 4)


def evaluate_trade(
    candles: List[Dict[str, Any]],
    entry_index: int,
    entry: float,
    stop: float,
    target: float,
    horizon: int,
) -> Dict[str, Any]:
    """Kirishdan keyingi `horizon` shamda avval stop yoki target tegishini aniqlaydi."""

    last = min(entry_index + horizon, len(candles) - 1)
    exit_price = entry
    outcome = "timeout"
    bars_held = 0
    for j in range(entry_index + 1, last + 1):
        bars_held = j - entry_index
        low = float(candles[j].get("l") or 0)
        high = float(candles[j].get("h") or 0)
        # Konservativ: bir barda ikkalasi tegsa, avval stop hisoblanadi.
        if low <= stop:
            exit_price = stop
            outcome = "stop"
            break
        if high >= target:
            exit_price = target
            outcome = "target"
            break
    else:
        if last > entry_index:
            exit_price = float(candles[last].get("c") or entry)

    risk = entry - stop
    reward = exit_price - entry
    r_multiple = (reward / risk) if risk > 0 else 0.0
    return_pct = ((exit_price - entry) / entry * 100.0) if entry else 0.0
    return {
        "outcome": outcome,
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "exit": round(exit_price, 4),
        "bars_held": bars_held,
        "return_pct": round(return_pct, 3),
        "r_multiple": round(r_multiple, 3),
        "win": exit_price > entry,
    }


def replay_strategy(
    candles: List[Dict[str, Any]],
    strategy_mode: str,
    thresholds: Optional[Dict[str, Any]] = None,
    *,
    ticker: str = "",
    min_history: int = 25,
    horizon: int = 10,
    avg_window: int = 20,
    strategy: Any = None,
) -> List[Dict[str, Any]]:
    """Tarix bo‘ylab walk-forward; har `strategy_pass` uchun bitta savdo natijasi."""

    mode = (strategy_mode or "rvol").strip().lower()
    if mode not in _DAILY_MODES:
        raise ValueError(f"backtest faqat kunlik rejimlarda: {sorted(_DAILY_MODES)}; berildi: {mode}")

    agent = strategy or make_strategy(mode)
    trades: List[Dict[str, Any]] = []
    n = len(candles)
    # Oxirgi barda kirsa, oldinga o‘lchov uchun joy qolmaydi.
    for i in range(max(min_history, avg_window), n - 1):
        snap = build_snapshot(candles, i, avg_window=avg_window, ticker=ticker)
        signal = agent.evaluate(snap, thresholds)
        if not signal.get("strategy_pass"):
            continue
        entry = float(snap.get("price") or 0)
        if entry <= 0:
            continue
        stop, target = _entry_stop_target(signal, entry)
        trade = evaluate_trade(candles, i, entry, stop, target, horizon)
        trade.update(
            {
                "ticker": snap.get("ticker"),
                "entry_index": i,
                "score": signal.get("score"),
                "trend_stage": signal.get("ignition_trend_stage"),
                "continuation_probability": signal.get("ignition_continuation_probability"),
                "rvol": snap.get("rvol"),
            }
        )
        trades.append(trade)
    return trades


def _prob_bucket(prob: Any) -> str:
    try:
        p = float(prob)
    except (TypeError, ValueError):
        return "n/a"
    if p < 50:
        return "<50"
    if p < 70:
        return "50-70"
    return "70+"


def summarize(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Savdolardan statistika: win-rate, o‘rtacha R, expectancy, kesimlar."""

    n = len(trades)
    if n == 0:
        return {"trades": 0, "win_rate_pct": 0.0, "avg_return_pct": 0.0, "avg_r": 0.0, "expectancy_r": 0.0}

    wins = [t for t in trades if t.get("win")]
    losses = [t for t in trades if not t.get("win")]
    returns = [float(t.get("return_pct") or 0) for t in trades]
    rs = [float(t.get("r_multiple") or 0) for t in trades]

    win_rate = len(wins) / n
    avg_win_r = mean([float(t.get("r_multiple") or 0) for t in wins]) if wins else 0.0
    avg_loss_r = mean([float(t.get("r_multiple") or 0) for t in losses]) if losses else 0.0
    expectancy = win_rate * avg_win_r + (1 - win_rate) * avg_loss_r

    by_stage: Dict[str, Dict[str, Any]] = {}
    by_prob: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        stage = str(t.get("trend_stage") or "n/a")
        by_stage.setdefault(stage, {"n": 0, "wins": 0})
        by_stage[stage]["n"] += 1
        by_stage[stage]["wins"] += 1 if t.get("win") else 0
        bucket = _prob_bucket(t.get("continuation_probability"))
        by_prob.setdefault(bucket, {"n": 0, "wins": 0})
        by_prob[bucket]["n"] += 1
        by_prob[bucket]["wins"] += 1 if t.get("win") else 0

    for grp in (by_stage, by_prob):
        for k, v in grp.items():
            v["win_rate_pct"] = round(v["wins"] / v["n"] * 100.0, 1) if v["n"] else 0.0

    return {
        "trades": n,
        "win_rate_pct": round(win_rate * 100.0, 1),
        "avg_return_pct": round(mean(returns), 3),
        "avg_r": round(mean(rs), 3),
        "expectancy_r": round(expectancy, 3),
        "by_stage": by_stage,
        "by_probability": by_prob,
    }


@contextmanager
def _env_overrides(overrides: Dict[str, str]) -> Iterator[None]:
    """Vaqtincha env o‘zgartirish (sweep uchun) — chiqishda tiklanadi."""

    saved: Dict[str, Optional[str]] = {}
    try:
        for k, v in overrides.items():
            saved[k] = os.environ.get(k)
            os.environ[k] = str(v)
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def sweep_thresholds(
    candles_by_ticker: Dict[str, List[Dict[str, Any]]],
    grid: List[Dict[str, str]],
    *,
    strategy_mode: str = "volume_ignition",
    horizon: int = 10,
    avg_window: int = 20,
    min_trades: int = 5,
) -> List[Dict[str, Any]]:
    """Har env-kombinatsiyani barcha tickerlar tarixida sinab, expectancy bo‘yicha reyting.

    `grid` — env-override lug‘atlari ro‘yxati, masalan
    `[{"IGNITION_MIN_RVOL": "2.0", "IGNITION_VOL_VS_20D_AVG": "2.0"}, ...]`.
    Eng yuqori `expectancy_r` = "yangi strategiya" sozlamasi.
    """

    ranked: List[Dict[str, Any]] = []
    for combo in grid:
        with _env_overrides(combo):
            all_trades: List[Dict[str, Any]] = []
            for ticker, candles in candles_by_ticker.items():
                if not candles:
                    continue
                all_trades.extend(
                    replay_strategy(
                        candles,
                        strategy_mode,
                        None,
                        ticker=ticker,
                        horizon=horizon,
                        avg_window=avg_window,
                    )
                )
            summary = summarize(all_trades)
        ranked.append({"params": combo, **summary})

    eligible = [r for r in ranked if r.get("trades", 0) >= min_trades] or ranked
    eligible.sort(key=lambda r: (r.get("expectancy_r", 0.0), r.get("win_rate_pct", 0.0)), reverse=True)
    return eligible


def build_default_grid(strategy_mode: str = "volume_ignition") -> List[Dict[str, str]]:
    """Sukut parametr to‘ri (kichik, tez). Foydalanuvchi kengaytirishi mumkin."""

    mode_norm = (strategy_mode or "").strip().lower()
    if mode_norm == "volume_ignition":
        grid: List[Dict[str, str]] = []
        for rvol in ("2.0", "2.5", "3.0"):
            for vol20 in ("1.8", "2.0", "2.5"):
                grid.append({"IGNITION_MIN_RVOL": rvol, "IGNITION_VOL_VS_20D_AVG": vol20})
        return grid
    if mode_norm in {"gap_go", "gap_and_go"}:
        grid = []
        for gap in ("3.0", "4.0", "5.0", "7.0"):
            for rvol in ("2.0", "2.5", "3.0"):
                grid.append({"GAP_GO_MIN_GAP_PCT": gap, "GAP_GO_MIN_RVOL": rvol})
        return grid
    grid = []
    for rvol in ("1.3", "1.5", "2.0", "2.5"):
        for vol in ("200000", "500000", "1000000"):
            grid.append({"MIN_RVOL": rvol, "MIN_VOLUME": vol})
    return grid
