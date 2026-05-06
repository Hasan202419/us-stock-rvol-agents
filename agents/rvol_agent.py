from typing import Any, Dict


class RVOLAgent:
    """Calculate relative volume from current and average volume."""

    def calculate(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        avg_volume = float(market_data.get("avg_volume") or 0)
        volume = float(market_data.get("volume") or 0)
        rvol = volume / avg_volume if avg_volume > 0 else 0.0

        enriched = dict(market_data)
        enriched["rvol"] = round(rvol, 2)
        return enriched
