"""MTrade Academy / Pine uyumluligi: VWAP crossover + SL/TP + TIME chiqish.

Pine (`MTrade Academy High Volatility`) bilan mos keladigan asoslar:
- `ta.crossover(close, vwap)` ← prev close <= VWAP, joriy close > VWAP.
- `inTime`: bar `time` (ochilish) NY bo‘yicha `[09:30+delay, 16:00-before)`.
- Kirish: flat holatda (`not inTrade`).
- `risk = max(close - nz(low[1]), 2 * mintick)`, SL/TP.
- Chiqish (`useCloseForExits`) yoki High/Low; TIME: `barTime >= endSession`.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Set

from agents.indicators import atr, cumulative_session_vwap, rsi
from agents.session_calendar import (
    NY_TZ,
    bar_end_in_regular_session,
    bar_end_in_trade_window,
    bar_start_in_regular_session,
    bar_start_in_trade_window,
    group_unix_ms_bar_starts_by_ny_trade_date,
    is_weekday_et,
    ny_from_unix_ms,
    ny_session_trade_bounds_for_date,
    utc_from_unix_ms,
)


class VwapBreakoutStrategyAgent:
    """Pine-ga yaqin VWAP strategiyasi (holat mashinasi ixtiyoriy)."""

    ALLOWED_TFS_MIN = frozenset({1, 2, 3, 5})

    def __init__(self) -> None:
        self.min_price = float(os.getenv("MIN_PRICE", "1"))
        self.timeframe_minutes = max(1, int(os.getenv("INTRADAY_TIMEFRAME_MINUTES", "5")))
        self.open_plus_minutes = int(os.getenv("SESSION_OPEN_PLUS_MINUTES", "3"))
        self.close_minus_minutes = int(os.getenv("SESSION_CLOSE_MINUS_MINUTES", "27"))
        self.r_multiplier = float(os.getenv("VWAP_R_MULTIPLIER", os.getenv("MTRADE_R_MULTIPLIER", "3")))

        self.session_window_anchor = os.getenv("VWAP_SESSION_WINDOW", "bar_open").strip().lower()
        self.regular_anchor = os.getenv("VWAP_REGULAR_ANCHOR", "bar_open").strip().lower()
        self.restrict_timeframes = os.getenv("RESTRICT_VWAP_TIMEFRAMES", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.pine_state_machine = os.getenv("VWAP_PINE_STATE_MACHINE", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.use_close_for_exits = os.getenv("VWAP_USE_CLOSE_FOR_EXITS", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.mintick = float(os.getenv("SYMBOL_MINTICK", os.getenv("MTRADE_SYM_MINTICK", "0.01")))
        override = os.getenv("VWAP_STRATEGY_NAME", "").strip()
        if override:
            self.strategy_label = override
        else:
            smode = os.getenv("STRATEGY_MODE", "").strip().lower()
            self.strategy_label = (
                "mtrade_high_volatility" if smode == "mtrade_high_volatility" else "vwap_breakout"
            )

    def _bar_in_trade_window(self, bar_start_ms: int) -> bool:
        use_open = self.session_window_anchor in {"bar_open", "open", "pine"}
        if use_open:
            return bar_start_in_trade_window(
                bar_start_ms, self.open_plus_minutes, self.close_minus_minutes
            )
        return bar_end_in_trade_window(
            bar_start_ms,
            self.timeframe_minutes,
            self.open_plus_minutes,
            self.close_minus_minutes,
        )

    def _bar_in_regular_session(self, bar_start_ms: int) -> bool:
        use_open = self.regular_anchor in {"bar_open", "open", "pine"}
        if use_open:
            return bar_start_in_regular_session(bar_start_ms)
        return bar_end_in_regular_session(bar_start_ms, self.timeframe_minutes)

    def evaluate(self, base_snapshot: Dict[str, Any], intraday_bars: List[Dict[str, Any]]) -> Dict[str, Any]:
        signal = dict(base_snapshot)
        signal["strategy_name"] = self.strategy_label

        if self.restrict_timeframes and self.timeframe_minutes not in self.ALLOWED_TFS_MIN:
            signal["strategy_pass"] = False
            signal["score"] = 0
            signal["failed_rules"] = ["timeframe_not_allowed"]
            self._decorate_empty(signal)
            return signal

        if not intraday_bars:
            signal["strategy_pass"] = False
            signal["score"] = 0
            signal["failed_rules"] = ["intraday_bars"]
            self._decorate_empty(signal)
            return signal

        bars_sorted = sorted(intraday_bars, key=lambda bar: int(bar["t"]))
        buckets = group_unix_ms_bar_starts_by_ny_trade_date(int(bar["t"]) for bar in bars_sorted)

        if not buckets:
            signal["strategy_pass"] = False
            signal["score"] = 0
            signal["failed_rules"] = ["intraday_buckets"]
            self._decorate_empty(signal)
            return signal

        latest_trade_date = max(buckets.keys())
        day_bars = [bar for bar in bars_sorted if int(bar["t"]) in buckets[latest_trade_date]]

        anchor_ny = ny_from_unix_ms(int(day_bars[0]["t"]))
        weekday_ok = is_weekday_et(anchor_ny)

        regular_session_bars: List[Dict[str, Any]] = []
        for bar in sorted(day_bars, key=lambda item: int(item["t"])):
            if self._bar_in_regular_session(int(bar["t"])):
                regular_session_bars.append(bar)

        if not weekday_ok or len(regular_session_bars) < 2:
            signal["strategy_pass"] = False
            signal["score"] = self._fallback_score(signal, weekday_ok, len(regular_session_bars))
            signal["failed_rules"] = self._explain_failure(
                weekday_ok,
                regular_session_bars,
                crossover_detected=False,
                price_ok=False,
            )
            self._decorate_indicators(signal, regular_session_bars, None)
            return signal

        vwaps = cumulative_session_vwap(regular_session_bars)
        closes = [float(bar.get("c") or 0) for bar in regular_session_bars]
        highs = [float(bar.get("h") or 0) for bar in regular_session_bars]
        lows = [float(bar.get("l") or 0) for bar in regular_session_bars]

        last_index = len(regular_session_bars) - 1
        breakout_index: int | None = None
        crossover_detected = False

        last_buy_idx, replay_events = self._pine_build_events(
            regular_session_bars, vwaps, closes, highs, lows
        )

        if self.pine_state_machine:
            crossover_detected = last_buy_idx is not None and last_buy_idx == last_index
            breakout_index = last_buy_idx
        else:
            trade_indices: List[int] = []
            for index, bar in enumerate(regular_session_bars):
                if self._bar_in_trade_window(int(bar["t"])):
                    trade_indices.append(index)
            trade_index_set: Set[int] = set(trade_indices)

            for current_idx in reversed(trade_indices):
                prev_idx = current_idx - 1
                if prev_idx not in trade_index_set:
                    continue

                vw_prev, vw_curr = vwaps[prev_idx], vwaps[current_idx]

                if vw_prev is None or vw_curr is None:
                    continue

                if closes[prev_idx] <= vw_prev and closes[current_idx] > vw_curr:
                    crossover_detected = True
                    breakout_index = current_idx
                    break

        self._decorate_indicators(
            signal,
            regular_session_bars,
            breakout_index if breakout_index is not None else last_index,
        )

        price_candidate = closes[breakout_index] if breakout_index is not None else closes[last_index]
        breakout_meets_price = price_candidate >= self.min_price

        signal["strategy_pass"] = crossover_detected and breakout_meets_price
        signal["failed_rules"] = self._explain_failure(
            weekday_ok,
            regular_session_bars,
            crossover_detected,
            breakout_meets_price,
        )
        signal["score"] = self._score(signal, crossover_detected, breakout_meets_price)

        risk_share, take_profit, stop_loss = self._risk_targets_pine(lows, closes, breakout_index)
        signal["risk_per_share"] = risk_share
        signal["take_profit_suggestion"] = take_profit
        signal["stop_suggestion"] = stop_loss

        self._attach_chart_payload(signal, regular_session_bars, vwaps, replay_events)

        return signal

    def _attach_chart_payload(
        self,
        signal: Dict[str, Any],
        bars: List[Dict[str, Any]],
        vwaps: List[float | None],
        events: List[Dict[str, Any]],
    ) -> None:
        """Streamlit uchun shamlar, VWAP va Pine-style markerlari (BUY / SELL / STOP / TIME)."""

        signal["chart_session_bars"] = [{**bar} for bar in bars]
        signal["chart_vwap_series"] = [None if v is None else float(v) for v in vwaps]
        signal["mtrade_chart_markers"] = events
        signal["chart_timeframe_minutes"] = self.timeframe_minutes

    def _hit_tp(self, cl: float, hi: float, tp: float) -> bool:
        if self.use_close_for_exits:
            return cl >= tp
        return hi >= tp

    def _hit_sl(self, cl: float, lo: float, sl: float) -> bool:
        if self.use_close_for_exits:
            return cl <= sl
        return lo <= sl

    def _pine_build_events(
        self,
        bars: List[Dict[str, Any]],
        vwaps: List[float | None],
        closes: List[float],
        highs: List[float],
        lows: List[float],
    ) -> tuple[int | None, List[Dict[str, Any]]]:
        """Pine tartibi replay: oxirgi BUY bar indeksi va BUY/SELL/STOP/TIME hodisalari."""

        events: List[Dict[str, Any]] = []
        in_trade = False
        tp_val = sl_val = entry = 0.0

        last_buy_idx: int | None = None

        mintick_floor = max(self.mintick * 2.0, 1e-8)

        for i in range(len(bars)):
            ms = int(bars[i]["t"])
            cl = closes[i]
            hi = highs[i]
            lo = lows[i]

            ny_start = utc_from_unix_ms(ms).astimezone(NY_TZ)
            day = ny_start.date()
            _, exclusive_end = ny_session_trade_bounds_for_date(
                day, self.open_plus_minutes, self.close_minus_minutes
            )

            crosses = (
                i > 0
                and vwaps[i - 1] is not None
                and vwaps[i] is not None
                and closes[i - 1] <= float(vwaps[i - 1])
                and cl > float(vwaps[i])
            )
            in_window = self._bar_in_trade_window(ms)

            enter_long = (not in_trade) and crosses and in_window
            if enter_long:
                prev_low_ref = lows[i - 1] if i > 0 else lo
                risk_raw = cl - prev_low_ref
                risk = max(risk_raw, mintick_floor)
                entry = cl
                sl_val = cl - risk
                tp_val = cl + risk * self.r_multiplier
                in_trade = True
                last_buy_idx = i
                events.append({"event": "BUY", "t": ms, "price": float(entry), "idx": i})

            time_up = in_trade and (ny_start >= exclusive_end)

            if in_trade:
                hit_tp = self._hit_tp(cl, hi, tp_val)
                hit_sl = self._hit_sl(cl, lo, sl_val)

                if hit_tp:
                    events.append(
                        {"event": "SELL", "t": ms, "price": float(cl), "idx": i, "ref": float(tp_val)}
                    )
                    in_trade = False
                elif hit_sl:
                    events.append(
                        {"event": "STOP", "t": ms, "price": float(cl), "idx": i, "ref": float(sl_val)}
                    )
                    in_trade = False
                elif time_up:
                    events.append({"event": "TIME", "t": ms, "price": float(cl), "idx": i})
                    in_trade = False

        return last_buy_idx, events

    def _risk_targets_pine(
        self,
        lows: List[float],
        closes: List[float],
        breakout_index: int | None,
    ) -> tuple[float | None, float | None, float | None]:
        if breakout_index is None or breakout_index < 1:
            return None, None, None

        entry_price = closes[breakout_index]
        previous_low_ref = lows[breakout_index - 1]
        mintick_floor = max(self.mintick * 2.0, 1e-8)
        risk_share = max(entry_price - previous_low_ref, mintick_floor)
        tp = round(entry_price + risk_share * self.r_multiplier, 4)
        sl_candidate = round(entry_price - risk_share, 4)
        return round(risk_share, 4), tp, sl_candidate

    def _explain_failure(
        self,
        weekday_ok: bool,
        regular_session_bars: List[Dict[str, Any]],
        crossover_detected: bool,
        price_ok: bool,
    ) -> List[str]:
        failed: List[str] = []

        if not weekday_ok:
            failed.append("weekday")

        if len(regular_session_bars) < 2:
            failed.append("session_bars")

        if not crossover_detected:
            failed.append("vwap_crossover")
        elif not price_ok:
            failed.append("min_price")

        return failed

    def _score(self, signal: Dict[str, Any], crossover_detected: bool, price_ok: bool) -> int:
        rule_points = 0
        if crossover_detected:
            rule_points += 40
        if price_ok:
            rule_points += 20
        if signal.get("rsi_14") is not None and float(signal["rsi_14"]) > 50:
            rule_points += 10
        if signal.get("atr_14") is not None and float(signal["atr_14"]) > 0:
            rule_points += 10
        return min(rule_points, 100)

    def _fallback_score(self, signal: Dict[str, Any], weekday_ok: bool, bar_count: int) -> int:
        score = 0
        if weekday_ok:
            score += 10
        if bar_count >= 2:
            score += 10
        if float(signal.get("price") or 0) >= self.min_price:
            score += 10
        return min(score, 100)

    def _decorate_empty(self, signal: Dict[str, Any]) -> None:
        signal.setdefault("session_vwap", None)
        signal.setdefault("rsi_14", None)
        signal.setdefault("atr_14", None)
        signal.setdefault("vwap_cross", False)

    def _decorate_indicators(
        self,
        signal: Dict[str, Any],
        regular_session_bars: List[Dict[str, Any]],
        highlight_idx: int | None,
    ) -> None:
        if not regular_session_bars:
            self._decorate_empty(signal)
            return

        vwaps = cumulative_session_vwap(regular_session_bars)
        closes = [float(bar.get("c") or 0) for bar in regular_session_bars]
        rsi_series = rsi(closes, period=14)
        atr_series = atr(regular_session_bars, period=14)

        marker = highlight_idx if highlight_idx is not None else len(regular_session_bars) - 1

        vw_marker = vwaps[marker]
        rsi_marker = rsi_series[marker]
        atr_marker = atr_series[marker]

        prev_close_for_cross = closes[marker - 1] if marker > 0 else None
        prev_vwap = vwaps[marker - 1] if marker > 0 else None
        vw_curr = vw_marker

        cross_flag = False
        if prev_close_for_cross is not None and prev_vwap is not None and vw_curr is not None:
            curr_close = closes[marker]
            cross_flag = prev_close_for_cross <= prev_vwap and curr_close > vw_curr

        signal["session_vwap"] = None if vw_marker is None else round(float(vw_marker), 4)
        signal["rsi_14"] = None if rsi_marker is None else round(float(rsi_marker), 2)
        signal["atr_14"] = None if atr_marker is None else round(float(atr_marker), 4)
        signal["vwap_cross"] = bool(cross_flag)