import json
import os
from typing import Any, Dict, List, Optional

from agents.indicators import snapshot_from_daily_candles


class StrategyAgent:
    """Apply simple RVOL momentum rules before any AI analysis runs."""

    def __init__(self) -> None:
        # Defaults err on the side of finding more names for research; tighten via .env or UI overrides.
        self.min_rvol = float(os.getenv("MIN_RVOL", "1.35"))
        self.min_price = float(os.getenv("MIN_PRICE", "1"))
        self.min_volume = int(os.getenv("MIN_VOLUME", "200000"))
        # Allow modest red days so scans are not empty on choppy tape (strict funds can set 0.01 for “must be green”).
        self.min_change_percent = float(os.getenv("MIN_CHANGE_PERCENT", "-2"))
        # MASTER-style optional filter: kunlik RSI zonasi (ma’lumot bo‘lmaganda o‘tmaydi → qoida “yumshoq” true).
        self.daily_rsi_gate = os.getenv("DAILY_RSI_GATE_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.daily_rsi_min = float(os.getenv("DAILY_RSI_MIN", "55"))
        self.daily_rsi_max = float(os.getenv("DAILY_RSI_MAX", "70"))
        self.daily_rsi_pass_if_missing = os.getenv("DAILY_RSI_PASS_IF_MISSING", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def evaluate(self, data: Dict[str, Any], thresholds: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Evaluate RVOL gates. Optional `thresholds` dict overrides .env for ad-hoc UI presets."""

        snap: Dict[str, Any] = {}
        candles = data.get("candles") or []
        if candles:
            snap = snapshot_from_daily_candles(candles)

        signal = dict(data)
        if snap:
            daily_rsi = snap.get("rsi_14")
            daily_atr = snap.get("atr_14")
            signal.update(
                {
                    "daily_bar_timestamp_ms": snap.get("bar_timestamp_ms"),
                    "daily_ema_9": snap.get("ema_9"),
                    "daily_ema_20": snap.get("ema_20"),
                    "daily_rsi_14": daily_rsi,
                    "daily_atr_14": daily_atr,
                    # RVOL rejimida dashboard jadvali uchun (sessiya indikatorlari yo‘q).
                    "rsi_14": daily_rsi,
                    "atr_14": daily_atr,
                    "indicators_daily_json": json.dumps(
                        {k: v for k, v in snap.items() if k != "closes_series_len"},
                        default=str,
                    ),
                }
            )

        active = {
            "min_rvol": self.min_rvol,
            "min_price": self.min_price,
            "min_volume": self.min_volume,
            "min_change_percent": self.min_change_percent,
        }

        if thresholds:
            for key, raw_value in thresholds.items():
                if raw_value is None:
                    continue
                if key == "min_volume":
                    active[key] = int(raw_value)
                else:
                    active[key] = float(raw_value)

        change_reading = float(data.get("change_percent") or 0)

        rules: Dict[str, bool] = {
            "rvol": float(data.get("rvol") or 0) >= float(active["min_rvol"]),
            "price": float(data.get("price") or 0) >= float(active["min_price"]),
            "volume": int(data.get("volume") or 0) >= int(active["min_volume"]),
            "change": change_reading >= float(active["min_change_percent"]),
        }

        if self.daily_rsi_gate:
            rsi_val = snap.get("rsi_14")
            if rsi_val is None:
                rules["daily_rsi"] = self.daily_rsi_pass_if_missing
            else:
                rules["daily_rsi"] = float(self.daily_rsi_min) <= float(rsi_val) <= float(self.daily_rsi_max)

        passed = all(rules.values())

        signal["strategy_pass"] = passed
        signal["score"] = self._score(signal, rules)
        signal["failed_rules"] = [name for name, ok in rules.items() if not ok]
        signal["strategy_name"] = "rvol_momentum"
        signal["thresholds_used"] = active
        if self.daily_rsi_gate:
            signal["thresholds_used"] = dict(
                active,
                daily_rsi_min=self.daily_rsi_min,
                daily_rsi_max=self.daily_rsi_max,
                daily_rsi_gate=True,
            )

        return signal

    def filter_signals(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return only tickers that pass all hard strategy rules."""
        return [record for record in records if record.get("strategy_pass")]

    def _score(self, signal: Dict[str, Any], rules: Dict[str, bool]) -> int:
        rule_points = sum(20 for ok in rules.values() if ok)
        rvol_bonus = min(int(float(signal.get("rvol") or 0) * 5), 10)
        change_bonus = min(int(max(float(signal.get("change_percent") or 0), 0)), 10)
        return min(rule_points + rvol_bonus + change_bonus, 100)
