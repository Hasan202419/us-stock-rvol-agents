"""Alohida Volume Ignition skaneri: kuchli bullish momentdan oldin abnormal hajm kengayishi."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from agents.indicators import atr, candles_to_sorted_bars, ema, snapshot_from_daily_candles


class VolumeIgnitionStrategyAgent:
    """Kunlik shamlarga asoslangan ‘volume ignition’ qoidalari (.env bilan sozlanadi)."""

    def __init__(self) -> None:
        self.min_avg_volume_liquidity = int(os.getenv("IGNITION_MIN_AVG_VOLUME", "1000000"))
        self.min_rvol = float(os.getenv("IGNITION_MIN_RVOL", "2"))
        self.vol_vs_ma20_multiple = float(os.getenv("IGNITION_VOL_VS_20D_AVG", "2"))
        self.max_3d_gain_frac = float(os.getenv("IGNITION_MAX_3DAY_GAIN_PCT", "10")) / 100.0
        self.max_resistance_distance_frac = float(os.getenv("IGNITION_MAX_RES_DISTANCE_PCT", "5")) / 100.0
        self.lookback_resistance_days = max(5, int(os.getenv("IGNITION_RESISTANCE_LOOKBACK", "20")))
        self.extended_move_ban_frac = float(os.getenv("IGNITION_EXTENDED_MOVE_BAN_PCT", "20")) / 100.0
        self.lookback_extended_days = max(10, int(os.getenv("IGNITION_EXTENDED_LOOKBACK", "20")))
        self.parabolic_1d_range_frac = float(os.getenv("IGNITION_PARABOLIC_RANGE_PCT", "15")) / 100.0
        self.parabolic_2d_jump_frac = float(os.getenv("IGNITION_PARABOLIC_2DAY_JUMP_PCT", "8")) / 100.0
        self.ema_extension_max_frac = float(os.getenv("IGNITION_EMA_EXTENSION_MAX_PCT", "8")) / 100.0
        self.min_price = float(os.getenv("MIN_PRICE", "1"))
        self.min_change_percent = float(os.getenv("MIN_CHANGE_PERCENT", "-2"))

    def evaluate(self, data: Dict[str, Any], thresholds: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """`rvol_snapshot` ustida ignition qoidalari + kunlik TA maydonlari."""

        candles_raw = data.get("candles") or []
        bars = candles_to_sorted_bars(candles_raw)

        snap = snapshot_from_daily_candles(candles_raw) if candles_raw else {}

        signal = dict(data)
        if candles_raw:
            signal.update(self._decorate_daily_snap(snap))

        min_price = float(self.min_price)
        min_vol_liq = int(self.min_avg_volume_liquidity)
        min_rvol = float(self.min_rvol)
        min_change_floor = float(self.min_change_percent)

        if thresholds:
            if thresholds.get("min_price") is not None:
                min_price = float(thresholds["min_price"])
            if thresholds.get("min_volume") is not None:
                min_vol_liq = max(min_vol_liq, int(thresholds["min_volume"]))
            min_change_floor = float(thresholds.get("min_change_percent", min_change_floor))

        ticker = str(data.get("ticker") or "").upper()

        avg_snapshot = float(data.get("avg_volume") or 0)
        curr_volume = float(data.get("volume") or 0)
        price_live = float(data.get("price") or 0)
        rvol = float(data.get("rvol") or 0)

        ignition_meta: Dict[str, Any] = {
            "liquidity_floor": min_vol_liq,
            "ignition_min_rvol": min_rvol,
        }

        min_bars = max(
            self.lookback_resistance_days + 5,
            self.lookback_extended_days + 5,
            25,
        )

        fails: Dict[str, bool] = {}

        if len(bars) < min_bars:
            fails["bars_history"] = True

        highs = [float(b.get("h") or 0) for b in bars]
        lows = [float(b.get("l") or 0) for b in bars]
        closes = [float(b.get("c") or 0) for b in bars]
        vols = [float(b.get("v") or 0) for b in bars]

        last_i = len(bars) - 1

        if not fails.get("bars_history"):
            closes_tail = closes[-max(self.lookback_resistance_days, 4) :]
            resistance_raw = max(closes_tail) if closes_tail else max(highs[last_i - self.lookback_resistance_days + 1 : last_i + 1])
            recent_high_band = highs[last_i - self.lookback_resistance_days + 1 : last_i + 1]
            resistance = float(max(max(recent_high_band), resistance_raw, 1e-9))

            base_close_3 = closes[last_i - 3] if last_i >= 3 else closes[0]
            gain_3d = (closes[last_i] / max(base_close_3, 1e-9)) - 1.0

            baseline_idx = max(0, last_i - self.lookback_extended_days)
            base_ext = closes[baseline_idx]
            extended_gain = (closes[last_i] / max(base_ext, 1e-9)) - 1.0

            rng_1 = (highs[last_i] - lows[last_i]) / max(lows[last_i], 1e-9)
            jmp2 = (
                abs((closes[last_i] / max(closes[last_i - 1], 1e-9)) - 1.0) if last_i >= 1 else 0.0
            )
            jmp1 = (
                abs((closes[last_i - 1] / max(closes[last_i - 2], 1e-9)) - 1.0)
                if last_i >= 2
                else 0.0
            )
            vol_ma20_prior = (
                sum(vols[last_i - 20 : last_i]) / 20.0 if last_i >= 20 else float("nan")
            )
            ratio_vs_ma20 = curr_volume / max(vol_ma20_prior, 1e-9) if vol_ma20_prior == vol_ma20_prior else 0.0

            bars_for_atr = bars[: last_i + 1]
            atr_series = atr(bars_for_atr, period=14)
            ema_9_series = ema(closes, 9)
            ema_20_series = ema(closes, 20)

            atr_curr = atr_series[last_i] if last_i < len(atr_series) else None
            atr_prev = atr_series[last_i - 1] if last_i >= 1 else None
            atr_prev3 = atr_series[last_i - 3] if last_i >= 3 else None

            ema_9_val = float(ema_9_series[last_i]) if ema_9_series[last_i] is not None else None
            ema_20_val = float(ema_20_series[last_i]) if ema_20_series[last_i] is not None else None

            c_now = closes[last_i]
            dist_res = (resistance - c_now) / max(c_now, 1e-9)

            lows_early = lows[last_i - 2] if last_i >= 2 else lows[0]
            lows_mid = lows[last_i - 1] if last_i >= 1 else lows[0]
            lows_last = lows[last_i]

            vol_m3, vol_m2, vol_m1 = (
                vols[last_i - 2],
                vols[last_i - 1],
                vols[last_i],
            )

            ignition_meta.update(
                {
                    "ignition_volume_prior_mean_20": round(vol_ma20_prior, 0)
                    if vol_ma20_prior == vol_ma20_prior
                    else None,
                    "ignition_volume_vs_20dma": round(ratio_vs_ma20, 2),
                    "ignition_resistance": round(resistance, 4),
                    "ignition_distance_to_resistance_pct": round(dist_res * 100.0, 2),
                    "ignition_gain_3d_pct": round(gain_3d * 100.0, 2),
                    "ignition_extended_move_pct": round(extended_gain * 100.0, 2),
                    "ignition_atr_pct_of_price": None
                    if atr_curr is None
                    else round(float(atr_curr) / max(c_now, 1e-9) * 100.0, 2),
                }
            )

            fails["liquidity"] = avg_snapshot < float(min_vol_liq)
            fails["price_min"] = price_live < min_price
            fails["rvol"] = rvol < min_rvol
            fails["volume_20d_ma2x"] = (not vol_ma20_prior == vol_ma20_prior) or (
                curr_volume + 1 < self.vol_vs_ma20_multiple * vol_ma20_prior
            )
            fails["volume_three_up"] = not (vol_m3 < vol_m2 < vol_m1)
            fails["cap_3d_gain"] = gain_3d >= self.max_3d_gain_frac
            fails["near_resistance"] = not (
                (-0.005 <= dist_res <= self.max_resistance_distance_frac + 0.005) and (c_now <= resistance * 1.002)
            )
            fails["higher_low"] = not (lows_early < lows_mid < lows_last)
            fails["extended_ban"] = extended_gain >= self.extended_move_ban_frac

            fails["ema_context"] = True
            if ema_9_val is not None and ema_20_val is not None:
                ext20 = (c_now - ema_20_val) / max(ema_20_val, 1e-9)
                fails["ema_context"] = not (
                    c_now > ema_9_val
                    and ext20 >= -0.025
                    and ext20 <= self.ema_extension_max_frac
                )

            fails["atr_rising"] = True
            if atr_curr is not None and atr_prev is not None and atr_prev3 is not None:
                fails["atr_rising"] = not (
                    float(atr_curr) > float(atr_prev) or float(atr_curr) > float(atr_prev3)
                )

            fails["parabolic"] = (rng_1 >= self.parabolic_1d_range_frac) or (
                jmp2 >= self.parabolic_2d_jump_frac and jmp1 >= self.parabolic_2d_jump_frac
            )

            fails["change_soft"] = float(data.get("change_percent") or 0) < min_change_floor

            trend_stage = self._infer_trend_stage(dist_res, ratio_vs_ma20, rvol)
            entry_lo, entry_hi = self._entry_zone(c_now, lows_mid, atr_curr)
            cont_prob = self._continuation_probability(fails)
            risk_level = self._risk_level(atr_curr, c_now, dist_res)

            vol_summary = (
                f"3 kunlik hajm o‘sish: {int(vol_m3):,} → {int(vol_m2):,} → {int(vol_m1):,}; "
                f"bugun {int(curr_volume):,} ({ratio_vs_ma20:.2f}× 20 kunlik o‘rtacha)"
            )

            ignition_meta.update(
                {
                    "volume_pattern_summary": vol_summary,
                    "ignition_trend_stage": trend_stage,
                    "ignition_entry_zone_low": round(entry_lo, 4),
                    "ignition_entry_zone_high": round(entry_hi, 4),
                    "ignition_continuation_probability": cont_prob,
                    "ignition_risk_level": risk_level,
                    "take_profit_suggestion": round(resistance, 4),
                    "stop_suggestion": round(c_now - (float(atr_curr) * 1.25), 4)
                    if atr_curr is not None
                    else None,
                    "ignition_professional_outline": self._analyst_outline(
                        ticker=ticker,
                        price=price_live,
                        vol_summary=vol_summary,
                        rvol=rvol,
                        dist_res_pct=dist_res * 100.0,
                        trend_stage=trend_stage,
                        entry_lo=entry_lo,
                        entry_hi=entry_hi,
                        cont_prob=cont_prob,
                        risk_level=risk_level,
                        atr_val=float(atr_curr) if atr_curr is not None else None,
                        stop_guess=round(c_now - (float(atr_curr) * 1.25), 4) if atr_curr else None,
                        target_guess=round(resistance, 4),
                    ),
                }
            )

        if fails.get("bars_history"):
            ignition_meta.update(
                {
                    "volume_pattern_summary": "Kunlik tarix qisqa — scanner uchun ~25+ tugallangan kun kerak.",
                    "ignition_trend_stage": "N/A",
                    "ignition_distance_to_resistance_pct": None,
                    "ignition_entry_zone_low": None,
                    "ignition_entry_zone_high": None,
                    "ignition_continuation_probability": self._continuation_probability(fails),
                    "ignition_risk_level": "Unknown (data gap)",
                    "take_profit_suggestion": None,
                    "stop_suggestion": None,
                    "ignition_professional_outline": (
                        f"**{ticker}** — kunlik kandellar yetarli emas; skan filtrini o‘tkazib yuborildi."
                    ),
                }
            )

        failed_keys = [key for key, bad in fails.items() if bad]
        passed = len(failed_keys) == 0

        signal.update(ignition_meta)
        signal["strategy_pass"] = passed
        signal["failed_rules"] = failed_keys
        raw_cp = ignition_meta.get("ignition_continuation_probability")
        try:
            cp = int(round(float(raw_cp))) if raw_cp is not None else self._continuation_probability(fails)
        except (TypeError, ValueError):
            cp = self._continuation_probability(fails)
        signal["score"] = self._score(passed, float(data.get("rvol") or 0), cp)
        signal["strategy_name"] = "volume_ignition_scan"
        signal["thresholds_used"] = {
            "min_price": min_price,
            "min_avg_volume": min_vol_liq,
            "min_rvol": min_rvol,
            "min_change_percent": min_change_floor,
        }

        return signal

    def _decorate_daily_snap(self, snap: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "daily_bar_timestamp_ms": snap.get("bar_timestamp_ms"),
            "daily_ema_9": snap.get("ema_9"),
            "daily_ema_20": snap.get("ema_20"),
            "daily_rsi_14": snap.get("rsi_14"),
            "daily_atr_14": snap.get("atr_14"),
            "indicators_daily_json": json.dumps(
                {k: v for k, v in snap.items() if k != "closes_series_len"},
                default=str,
            ),
        }

    def _infer_trend_stage(self, dist_res: float, vol_ratio: float, rvol: float) -> str:
        d_pct = dist_res * 100.0
        if d_pct <= 1.25 and rvol >= 2.5 and vol_ratio >= 2.2:
            return "Ignition"
        if d_pct <= 4.0:
            return "Accumulation"
        if d_pct <= 6.5:
            return "Pre-breakout"
        return "Monitor"

    def _entry_zone(
        self,
        close: float,
        last_swing_low: float,
        atr_val: Optional[float],
    ) -> tuple[float, float]:
        atr_use = float(atr_val or max(close * 0.015, 0.01))
        lo = max(last_swing_low * 0.998, close - atr_use)
        hi = min(close + 0.35 * atr_use, close + max(atr_use * 0.5, 0.05))
        if lo >= hi:
            hi = close + max(atr_use * 0.25, 0.02)
        return lo, hi

    def _continuation_probability(self, fails: Dict[str, bool]) -> int:
        if fails.get("bars_history"):
            return 18

        pieces = (
            ("rvol", 12),
            ("volume_20d_ma2x", 12),
            ("volume_three_up", 10),
            ("near_resistance", 14),
            ("higher_low", 11),
            ("atr_rising", 10),
            ("ema_context", 12),
            ("extended_ban", 13),
            ("parabolic", 16),
            ("liquidity", 10),
            ("price_min", 5),
            ("cap_3d_gain", 12),
            ("change_soft", 5),
        )
        score = sum(w for key, w in pieces if key in fails and not fails[key])

        softer = fails.get("change_soft", False) and sum(1 for k, bad in fails.items() if bad) <= 2
        if softer:
            score = min(score + 3, 100)

        return max(35, min(96, score))

    def _risk_level(self, atr_curr: Optional[float], close_px: float, dist_res_frac: float) -> str:
        atr_pct = 0.0
        if atr_curr is not None and close_px > 0:
            atr_pct = float(atr_curr) / close_px * 100.0
        squeeze = dist_res_frac * 100.0
        if atr_pct >= 6.5:
            base = "High"
        elif atr_pct >= 4.2:
            base = "Elevated"
        else:
            base = "Controlled"
        if squeeze <= 1.8:
            return f"{base} (tight squeeze {squeeze:.1f}% to pivot)"
        if squeeze <= 4.8:
            return f"{base} (near supply {squeeze:.1f}%)"
        return f"{base} (stretch {squeeze:.1f}% off pivot)"

    def _score(self, passed: bool, rvol: float, cont_prob: int) -> int:
        capped = max(28, min(96, cont_prob))
        if not passed:
            return max(8, min(48, capped // 2))
        return min(capped + min(int(max(rvol - self.min_rvol, 0) * 7), 8), 100)

    def _analyst_outline(
        self,
        *,
        ticker: str,
        price: float,
        vol_summary: str,
        rvol: float,
        dist_res_pct: float,
        trend_stage: str,
        entry_lo: float,
        entry_hi: float,
        cont_prob: int,
        risk_level: str,
        atr_val: float | None,
        stop_guess: float | None,
        target_guess: float,
    ) -> str:
        atr_line = (
            f"ATR(14): {atr_val:.4f} (~{atr_val / max(price, 1e-9) * 100:.2f}% of price)." if atr_val else "ATR(14): n/a."
        )
        stop_line = (
            f"Stop (mechanical): ~{stop_guess} (~1.25×ATR g‘oya)."
            if stop_guess
            else "Stop: tuzating — ATR uchun ma'lumot yetarli emas."
        )
        rr = ""
        if stop_guess and target_guess and price > stop_guess:
            rr = f"Rough R:R to measured resistance ≈ {(target_guess - price) / max(price - stop_guess, 1e-6):.2f}:1."

        sections = (
            "1) EDGE / SABAB\n• Abnormal hajm kengayiishi + qarshilik yaqinligi + strukturali yuqori dip\n• "
            "(Yangi katalizatorni alohida yangiliklar bilan tasdiqlang)\n\n"
            f"2) TEXNIK ANALIZ\n• Trend: narxi > EMA9, EMA20 dan uzoqqa taralmagan\n• "
            f"Qarshilik zonasi ({dist_res_pct:.2f}% yuqori); {atr_line}\n• {vol_summary}\n\n"
            "3) BASHORA\n• Yo‘nalish: bullish davom nazariasi (skan nazariysi).\n• "
            f"Davom ehtimoli (model): **{cont_prob}%** ({trend_stage} bosqich).\n\n"
            "4) RISK\n• Asosiy xavf: qarshilikda rad etilish + atr tebranishi.\n• "
            f"Risk tasviri: {risk_level}\n\n"
            f"5) SETUP\n• Kirish zonasi: {entry_lo:.4f}–{entry_hi:.4f}\n• "
            f"Maqsad zonasi (pivot/resistance ga yaqin): {target_guess:.4f}\n• {stop_line}\n• {rr}\n\n"
            "6) IJRO\n• Pullback / tayyorlangan hajm bilan tasdiq kuting.\n• "
            "Stopeni darhol rejalashtiring; qarshilikda qaror chiqarish uchun rejani yangilang."
        )

        return (
            f"Ticker: **{ticker}**\n"
            f"Price: **{price:.4f}**\n"
            f"RVOL xolati: **{rvol:.2f}**\n\n"
            f"TREND_STAGE: **{trend_stage}**\n\n"
            f"{sections.strip()}"
        )
