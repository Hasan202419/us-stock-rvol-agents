from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


class LoggerAgent:
    """Save scanner signals and paper trading activity to CSV files."""

    def __init__(self, logs_dir: str = "logs") -> None:
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.signals_path = self.logs_dir / "signals.csv"
        self.full_scan_path = self.logs_dir / "full_scan.csv"
        self.trades_path = self.logs_dir / "trades.csv"

    def save_signals(self, signals: List[Dict[str, Any]]) -> None:
        if not signals:
            return

        rows = [
            {
                "ticker": signal.get("ticker"),
                "price": signal.get("price"),
                "change_percent": signal.get("change_percent"),
                "volume": signal.get("volume"),
                "avg_volume": signal.get("avg_volume"),
                "rvol": signal.get("rvol"),
                "score": signal.get("score"),
                "chatgpt_decision": signal.get("chatgpt_decision"),
                "chatgpt_risk_flags": signal.get("chatgpt_risk_flags_json"),
                "chatgpt_risk_flags_hard": signal.get("chatgpt_risk_flags_hard_json"),
                "chatgpt_entry_condition": signal.get("chatgpt_entry_condition"),
                "analyst_trade_plan_excerpt": (str(signal.get("analyst_trade_plan_text") or "")[:500]),
                "strategy_name": signal.get("strategy_name"),
                "indicator_lineage_json": signal.get("indicator_lineage_json"),
                "daily_bar_timestamp_ms": signal.get("daily_bar_timestamp_ms"),
                "risk_level": signal.get("risk_level"),
                "data_delay": signal.get("data_delay"),
                "updated_time": signal.get("updated_time"),
                "reason": signal.get("chatgpt_reason"),
            }
            for signal in signals
        ]
        self._append_rows(self.signals_path, rows)

    def save_full_scan(self, rows: List[Dict[str, Any]]) -> None:
        """Append one full scan run so you can audit every ticker that was checked."""
        if not rows:
            return

        self._append_rows(self.full_scan_path, rows)

    def save_trade(self, trade: Dict[str, Any]) -> None:
        self._append_rows(self.trades_path, [trade])

    def _append_rows(self, path: Path, rows: List[Dict[str, Any]]) -> None:
        dataframe = pd.DataFrame(rows)
        header = not path.exists()
        dataframe.to_csv(path, mode="a", index=False, header=header)
