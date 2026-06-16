"""Signal grafigi — sof Pillow bilan svecha + hajm + Entry/SL/TP + S/R zonalari.

Telegram signaliga biriktiriladigan PNG rasm chizadi. Matplotlib kerak emas (faqat Pillow),
shu sabab Render/VPS da yengil va ishonchli. Ma'lumot signaldan keladi (candles + darajalar),
tarmoqqa chiqmaydi — sof birliklar bilan testlanadi.

Darajalar signalning turli kalitlaridan o'qiladi (ignition / AMT / scalp / gap qatlamlari):
- Entry: ignition_entry_zone_low/high, trade_entry, price
- Stop:  stop_suggestion, trade_stop_loss
- TP:    take_profit_suggestion, trade_tp1, trade_tp2
- S/R:   ignition_resistance (qarshilik), amt_val/amt_vah (value area = qo'llab-quvvatlash zonasi), amt_poc
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except ImportError:  # pragma: no cover - Pillow har doim requirements da
    _PIL_OK = False

# Rang sxemasi (Streamlit-uslubidagi to'q fon)
_BG = (14, 17, 23, 255)
_GRID = (40, 46, 56, 255)
_TXT = (210, 215, 222, 255)
_TXT_DIM = (130, 138, 148, 255)
_UP = (38, 166, 154, 255)
_DOWN = (239, 83, 80, 255)
_VOL = (70, 80, 95, 255)
_ENTRY = (66, 135, 245, 255)
_STOP = (239, 83, 80, 255)
_TP = (38, 200, 120, 255)
_POC = (245, 166, 35, 255)
_RES = (171, 110, 240, 255)
_ZONE_SUP = (38, 166, 154, 46)   # value area (support) yarim shaffof
_ZONE_ENTRY = (66, 135, 245, 40)  # entry zona


def _f(val: Any) -> Optional[float]:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def extract_levels(signal: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Signalning turli kalitlaridan savdo darajalarini bitta lug'atga yig'adi."""

    price = _f(signal.get("price"))
    entry = _f(signal.get("trade_entry")) or price
    entry_lo = _f(signal.get("ignition_entry_zone_low"))
    entry_hi = _f(signal.get("ignition_entry_zone_high"))
    stop = _f(signal.get("stop_suggestion")) or _f(signal.get("trade_stop_loss"))
    tp1 = _f(signal.get("take_profit_suggestion")) or _f(signal.get("trade_tp1"))
    tp2 = _f(signal.get("trade_tp2"))
    resistance = _f(signal.get("ignition_resistance"))
    val = _f(signal.get("amt_val"))
    vah = _f(signal.get("amt_vah"))
    poc = _f(signal.get("amt_poc"))
    return {
        "price": price,
        "entry": entry,
        "entry_lo": entry_lo,
        "entry_hi": entry_hi,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "resistance": resistance,
        "val": val,
        "vah": vah,
        "poc": poc,
    }


def _font(size: int) -> Any:
    try:
        return ImageFont.load_default(size=size)
    except (AttributeError, TypeError):  # pragma: no cover - eski Pillow
        return ImageFont.load_default()


def _sorted_bars(candles: List[Dict[str, Any]], max_bars: int) -> List[Dict[str, float]]:
    out: List[Dict[str, float]] = []
    for c in candles or []:
        try:
            out.append(
                {
                    "t": float(c.get("t") or 0),
                    "o": float(c.get("o")),
                    "h": float(c.get("h")),
                    "l": float(c.get("l")),
                    "c": float(c.get("c")),
                    "v": float(c.get("v") or 0),
                }
            )
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda b: b["t"])
    return out[-max_bars:] if max_bars > 0 else out


def render_signal_chart(
    signal: Dict[str, Any],
    candles: Optional[List[Dict[str, Any]]] = None,
    *,
    out_path: Optional[str] = None,
    max_bars: int = 60,
    width: int = 1000,
    height: int = 620,
) -> Optional[bytes]:
    """Signaldan annotatsiyalangan PNG chizadi; candles bo'lmasa None (chaqiruvchi link'ga qaytadi)."""

    if not _PIL_OK:
        return None
    bars = _sorted_bars(candles if candles is not None else (signal.get("candles") or []), max_bars)
    if len(bars) < 2:
        return None

    levels = extract_levels(signal)
    ticker = str(signal.get("ticker") or "?").upper()

    # Layout
    pad_l, pad_r, pad_t, pad_b = 16, 86, 44, 22
    vol_h = int((height - pad_t - pad_b) * 0.20)
    gap = 14
    price_top = pad_t
    price_bot = height - pad_b - vol_h - gap
    vol_top = price_bot + gap
    vol_bot = height - pad_b
    plot_l = pad_l
    plot_r = width - pad_r

    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    lvl_vals = [v for v in levels.values() if v is not None]
    p_hi = max(highs + lvl_vals)
    p_lo = min(lows + lvl_vals)
    span = max(p_hi - p_lo, 1e-6)
    p_hi += span * 0.04
    p_lo -= span * 0.04
    span = p_hi - p_lo

    def py(price: float) -> float:
        return price_bot - (price - p_lo) / span * (price_bot - price_top)

    n = len(bars)
    slot = (plot_r - plot_l) / n
    body_w = max(2.0, slot * 0.6)

    img = Image.new("RGBA", (width, height), _BG)
    draw = ImageDraw.Draw(img, "RGBA")
    f_sm = _font(13)
    f_lg = _font(18)

    # Sarlavha
    score = signal.get("score")
    rvol = signal.get("rvol")
    strat = str(signal.get("strategy_name") or "").replace("_scan", "")
    bits = [ticker]
    if score is not None:
        bits.append(f"skor {score}")
    if rvol is not None:
        try:
            bits.append(f"RVOL {float(rvol):.2f}")
        except (TypeError, ValueError):
            pass
    if strat:
        bits.append(strat)
    draw.text((pad_l, 12), "  ·  ".join(bits), font=f_lg, fill=_TXT)

    # Gorizontal grid + narx yorliqlari (5 daraja)
    for k in range(5):
        gp = p_lo + span * k / 4
        y = py(gp)
        draw.line([(plot_l, y), (plot_r, y)], fill=_GRID, width=1)
        draw.text((plot_r + 6, y - 7), f"{gp:.2f}", font=f_sm, fill=_TXT_DIM)

    # S/R va entry zonalar (yarim shaffof to'rtburchak)
    if levels["val"] and levels["vah"]:
        y1, y2 = py(levels["vah"]), py(levels["val"])
        draw.rectangle([plot_l, min(y1, y2), plot_r, max(y1, y2)], fill=_ZONE_SUP)
    if levels["entry_lo"] and levels["entry_hi"]:
        y1, y2 = py(levels["entry_hi"]), py(levels["entry_lo"])
        draw.rectangle([plot_l, min(y1, y2), plot_r, max(y1, y2)], fill=_ZONE_ENTRY)

    # Svechalar
    for i, b in enumerate(bars):
        cx = plot_l + (i + 0.5) * slot
        up = b["c"] >= b["o"]
        col = _UP if up else _DOWN
        draw.line([(cx, py(b["h"])), (cx, py(b["l"]))], fill=col, width=1)
        y_o, y_c = py(b["o"]), py(b["c"])
        draw.rectangle([cx - body_w / 2, min(y_o, y_c), cx + body_w / 2, max(y_o, y_c) + 1], fill=col)

    # Hajm panel
    max_v = max((b["v"] for b in bars), default=0) or 1
    draw.line([(plot_l, vol_bot), (plot_r, vol_bot)], fill=_GRID, width=1)
    for i, b in enumerate(bars):
        cx = plot_l + (i + 0.5) * slot
        h = (b["v"] / max_v) * (vol_bot - vol_top)
        col = _UP if b["c"] >= b["o"] else _DOWN
        draw.rectangle([cx - body_w / 2, vol_bot - h, cx + body_w / 2, vol_bot], fill=(col[0], col[1], col[2], 150))
    draw.text((plot_l, vol_top - 2), "Hajm", font=f_sm, fill=_TXT_DIM)

    # Daraja chiziqlari + o'ng yorliq
    line_levels: List[Tuple[str, Optional[float], Tuple[int, int, int, int], bool]] = [
        ("Entry", levels["entry"], _ENTRY, False),
        ("SL", levels["stop"], _STOP, False),
        ("TP1", levels["tp1"], _TP, False),
        ("TP2", levels["tp2"], _TP, True),
        ("POC", levels["poc"], _POC, True),
        ("Res", levels["resistance"], _RES, True),
    ]
    for name, val, col, dashed in line_levels:
        if not val or val <= p_lo or val >= p_hi:
            continue
        y = py(val)
        if dashed:
            _dashed_line(draw, plot_l, plot_r, y, col)
        else:
            draw.line([(plot_l, y), (plot_r, y)], fill=col, width=2)
        draw.text((plot_l + 4, y - 14), f"{name} {val:.2f}", font=f_sm, fill=col)

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    data = out.getvalue()
    if out_path:
        with open(out_path, "wb") as fh:
            fh.write(data)
    return data


def _dashed_line(draw: Any, x0: float, x1: float, y: float, col: Tuple[int, int, int, int]) -> None:
    dash, gap = 9, 6
    x = x0
    while x < x1:
        draw.line([(x, y), (min(x + dash, x1), y)], fill=col, width=2)
        x += dash + gap


def chart_caption(signal: Dict[str, Any]) -> str:
    """Rasm ostidagi qisqa matn (HTML): asosiy darajalar bir qatorda."""

    lv = extract_levels(signal)
    t = str(signal.get("ticker") or "?").upper()
    parts = [f"<b>{t}</b>"]
    if lv["entry"]:
        parts.append(f"Entry <code>{lv['entry']:.2f}</code>")
    if lv["stop"]:
        parts.append(f"SL <code>{lv['stop']:.2f}</code>")
    if lv["tp1"]:
        tp = f"TP <code>{lv['tp1']:.2f}</code>"
        if lv["tp2"]:
            tp += f"/<code>{lv['tp2']:.2f}</code>"
        parts.append(tp)
    if lv["entry"] and lv["stop"] and lv["tp1"] and lv["entry"] > lv["stop"]:
        rr = (lv["tp1"] - lv["entry"]) / (lv["entry"] - lv["stop"])
        parts.append(f"R:R <code>{rr:.2f}</code>")
    return " · ".join(parts)
