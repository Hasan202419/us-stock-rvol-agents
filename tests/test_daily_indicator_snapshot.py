from agents.indicators import snapshot_from_daily_candles


def test_snapshot_from_daily_trend_series() -> None:
    candles = []
    price = 10.0
    for idx in range(40):
        t = 1_700_000_000_000 + idx * 86_400_000
        o = price
        price += 0.15 + (idx % 3) * 0.02
        c = price
        h = max(o, c) + 0.05
        l = min(o, c) - 0.05
        v = 1_000_000 + idx * 500
        candles.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})

    snap = snapshot_from_daily_candles(candles)
    assert snap["closes_series_len"] == len(candles)
    assert snap["ema_9"] is not None
    assert snap["rsi_14"] is not None
    assert snap["atr_14"] is not None
