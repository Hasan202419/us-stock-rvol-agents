"""Gap-and-Go strategiyasi — gap up + RVOL davomi (momentum).

G‘oya (klassik day-trade edge): aksiya kechagi yopilishdan sezilarli **gap up** bilan
ochilsa va ochilishdan keyin gapni *ushlab* (fill qilmasdan) abnormal **RVOL** bilan
yuqoriga davom etsa — momentum davomi ehtimoli yuqori. Gap-fade (gapni to‘ldirib tushish)
aksincha — uni filtrlash kerak.

Bu agent jonli skanerdagi `StrategyAgent`/`VolumeIgnitionStrategyAgent` bilan bir xil
`.evaluate(snapshot, thresholds)` shartnomasiga amal qiladi — shu sabab ham jonli skan
(`STRATEGY_MODE=gap_and_go`), ham `backtest_engine` (mode `gap_go`) da ishlaydi.

Kunlik shamlarda model: gap = (bugun_open − kecha_close)/kecha_close. "Go" tasdig‘i —
kun yuqori choragida yopilishi (gap ushlandi). Sozlamalar `.env` orqali (sweep mos).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from agents.indicators import candles_to_sorted_bars


class GapAndGoStrategyAgent:
    """Kunlik gap-up + RVOL davomi qoidalari (.env bilan sozlanadi)."""

    def __init__(self) -> None:
        self.min_gap_pct = float(os.getenv("GAP_GO_MIN_GAP_PCT", "3"))
        self.max_gap_pct = float(os.getenv("GAP_GO_MAX_GAP_PCT", "20"))
        self.min_rvol = float(os.getenv("GAP_GO_MIN_RVOL", "2"))
        self.min_avg_volume = int(os.getenv("GAP_GO_MIN_AVG_VOLUME", "500000"))
        self.min_price = float(os.getenv("GAP_GO_MIN_PRICE", os.getenv("MIN_PRICE", "2")))
        # "Go" tasdig‘i: kun diapazonida yopilish o‘rni (0=low, 1=high) shu chegaradan yuqori.
        self.min_close_position = float(os.getenv("GAP_GO_MIN_CLOSE_POSITION", "0.5"))
        self.stop_cap_frac = float(os.getenv("GAP_GO_STOP_CAP_PCT", "8")) / 100.0
        self.reward_r_multiple = float(os.getenv("GAP_GO_REWARD_R", "2"))
        self.min_history_bars = max(2, int(os.getenv("GAP_GO_MIN_HISTORY_BARS", "20")))

    def evaluate(self, data: Dict[str, Any], thresholds: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        candles_raw = data.get("candles") or []
        bars = candles_to_sorted_bars(candles_raw)

        signal = dict(data)

        min_price = float(self.min_price)
        min_vol_liq = int(self.min_avg_volume)
        if thresholds:
            if thresholds.get("min_price") is not None:
                min_price = float(thresholds["min_price"])
            if thresholds.get("min_volume") is not None:
                min_vol_liq = max(min_vol_liq, int(thresholds["min_volume"]))

        price = float(data.get("price") or 0)
        rvol = float(data.get("rvol") or 0)
        avg_volume = float(data.get("avg_volume") or 0)

        fails: Dict[str, bool] = {}
        meta: Dict[str, Any] = {
            "gap_go_min_gap_pct": self.min_gap_pct,
            "gap_go_min_rvol": self.min_rvol,
        }

        if len(bars) < self.min_history_bars:
            fails["bars_history"] = True
            return self._finish(signal, meta, fails, rvol=rvol, gap_pct=0.0)

        today = bars[-1]
        prev = bars[-2]
        prev_close = float(prev.get("c") or 0)
        t_open = float(today.get("o") or 0)
        t_high = float(today.get("h") or 0)
        t_low = float(today.get("l") or 0)
        t_close = float(today.get("c") or price or 0)

        gap_pct = ((t_open - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
        day_range = max(t_high - t_low, 1e-9)
        close_position = (t_close - t_low) / day_range  # 0=low, 1=high

        meta.update(
            {
                "gap_pct": round(gap_pct, 2),
                "gap_go_close_position": round(close_position, 3),
                "gap_go_prev_close": round(prev_close, 4),
                "gap_go_open": round(t_open, 4),
            }
        )

        # Qoidalar (har biri fail kaliti).
        fails["gap_up"] = gap_pct < self.min_gap_pct
        fails["gap_exhausted"] = gap_pct > self.max_gap_pct
        fails["rvol"] = rvol < self.min_rvol
        fails["liquidity"] = avg_volume < float(min_vol_liq)
        fails["price_min"] = (price or t_close) < min_price
        # "Go": gapni ushlab kun yuqori qismida yopilish + kecha yopilishidan yuqori (gap fill emas).
        fails["held_gap"] = (close_position < self.min_close_position) or (t_close <= prev_close)

        # SL: kun pasti gapni ushladi → uning ostida; juda uzoq bo‘lsa stop_cap bilan cheklash.
        entry = price or t_close
        floor_stop = entry * (1.0 - self.stop_cap_frac)
        stop = max(min(t_low, entry * 0.999), floor_stop)
        if stop <= 0 or stop >= entry:
            stop = round(entry * (1.0 - self.stop_cap_frac), 4)
        risk = max(entry - stop, 1e-9)
        target = entry + self.reward_r_multiple * risk

        gap_bucket = self._gap_bucket(gap_pct)
        cont_prob = self._continuation_probability(fails, rvol=rvol, close_position=close_position)
        meta.update(
            {
                "stop_suggestion": round(stop, 4),
                "take_profit_suggestion": round(target, 4),
                "gap_go_bucket": gap_bucket,
                "gap_go_rr": round((target - entry) / risk, 2),
                # backtest_engine reytinglari uchun (by_stage / by_probability):
                "ignition_trend_stage": gap_bucket,
                "ignition_continuation_probability": cont_prob,
            }
        )
        return self._finish(signal, meta, fails, rvol=rvol, gap_pct=gap_pct, cont_prob=cont_prob)

    def _finish(
        self,
        signal: Dict[str, Any],
        meta: Dict[str, Any],
        fails: Dict[str, bool],
        *,
        rvol: float,
        gap_pct: float,
        cont_prob: Optional[int] = None,
    ) -> Dict[str, Any]:
        failed_keys = [k for k, bad in fails.items() if bad]
        passed = len(failed_keys) == 0
        if cont_prob is None:
            cont_prob = self._continuation_probability(fails, rvol=rvol, close_position=0.0)
        signal.update(meta)
        signal["strategy_pass"] = passed
        signal["failed_rules"] = failed_keys
        signal["strategy_name"] = "gap_and_go_scan"
        signal["score"] = self._score(passed, rvol=rvol, gap_pct=gap_pct, cont_prob=cont_prob)
        signal["thresholds_used"] = {
            "min_gap_pct": self.min_gap_pct,
            "max_gap_pct": self.max_gap_pct,
            "min_rvol": self.min_rvol,
            "min_avg_volume": self.min_avg_volume,
            "min_price": self.min_price,
        }
        signal.setdefault("ignition_continuation_probability", cont_prob)
        return signal

    @staticmethod
    def _gap_bucket(gap_pct: float) -> str:
        if gap_pct < 3:
            return "Gap<3"
        if gap_pct < 6:
            return "Gap3-6"
        if gap_pct < 10:
            return "Gap6-10"
        return "Gap10+"

    def _continuation_probability(self, fails: Dict[str, bool], *, rvol: float, close_position: float) -> int:
        if fails.get("bars_history"):
            return 15
        pieces = (
            ("gap_up", 16),
            ("rvol", 16),
            ("held_gap", 18),
            ("liquidity", 10),
            ("gap_exhausted", 10),
            ("price_min", 6),
        )
        score = sum(w for key, w in pieces if not fails.get(key, False))
        score += min(int(max(rvol - self.min_rvol, 0) * 5), 10)
        score += int(max(close_position - self.min_close_position, 0) * 12)
        return max(20, min(96, score))

    def _score(self, passed: bool, *, rvol: float, gap_pct: float, cont_prob: int) -> int:
        capped = max(20, min(96, cont_prob))
        if not passed:
            return max(8, min(48, capped // 2))
        bonus = min(int(max(gap_pct - self.min_gap_pct, 0) * 1.5), 8)
        bonus += min(int(max(rvol - self.min_rvol, 0) * 4), 6)
        return min(capped + bonus, 100)
