"""main.py — Hasan Zone Breakout VWAP Scalping Signal Bot (kirish nuqtasi).

XAVFSIZLIK: bu bot REAL ORDER QO'YMAYDI. Auto-buy/sell/execute yo'q. Faqat signal +
Telegram alert. Standart qat'iy: setup toza bo'lmasa NO_TRADE.

Ishga tushirish:
    python main.py                 # continuous (har REFRESH_SECONDS)
    python main.py --once          # bir marta skan
    python main.py --once --dry-telegram   # Telegram o'rniga konsolga (kalitsiz)
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# To'g'ridan-to'g'ri `python main.py` uchun paketni import yo'liga qo'shamiz
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from hasan_zone_breakout_bot import config, logger, scanner, telegram_bot  # noqa: E402
from hasan_zone_breakout_bot.market_regime import get_market_regime  # noqa: E402


def is_market_open() -> bool:
    """US bozori ochiqmi (NY, dushanba-juma, 09:30-16:00)? Bayramlar hisobga olinmaydi (sodda)."""
    try:
        ny = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        ny = datetime.now(UTC)
    if ny.weekday() >= 5:  # 5=shanba, 6=yakshanba
        return False
    minutes = ny.hour * 60 + ny.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


def run_once(*, dry: bool, preferred: str = "auto") -> None:
    """Bir marta: bozor rejimi -> skan -> log -> (kerak bo'lsa) Telegram alert."""
    market_open = is_market_open()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] Skan boshlandi · bozor {'OCHIQ' if market_open else 'YOPIQ'} · manba={preferred}")

    if not market_open:
        print("Bozor yopiq — MARKET_CLOSED, yangi signal yuborilmaydi (faqat log).")

    regime = get_market_regime(preferred=preferred)
    print(f"Bozor rejimi: {regime.get('regime')}")

    signals = scanner.scan_all(regime, market_open=market_open, preferred=preferred)

    alerts_sent = 0
    for sig in signals:
        logger.log_scan(sig)
        decision = sig.get("decision")
        # Telegram faqat PAPER_READY+ va bozor ochiq bo'lsa
        if market_open and decision in config.TELEGRAM_ALERT_DECISIONS:
            if telegram_bot.maybe_alert(sig, regime, dry=dry):
                logger.log_alert(sig)
                alerts_sent += 1

    # Qisqa hisobot
    ready = [s for s in signals if str(s.get("decision", "")).endswith("PAPER_READY")]
    watch = [s for s in signals if s.get("decision") == "WATCHLIST"]
    print(f"Natija: {len(signals)} ticker · PAPER_READY {len(ready)} · WATCHLIST {len(watch)} · alert {alerts_sent}")
    for s in ready[:10]:
        print(f"  {s.get('decision'):26} {s.get('ticker'):6} score={s.get('score')} "
              f"entry={s.get('entry')} stop={s.get('stop_loss')} rr={s.get('risk_reward')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hasan Zone Breakout VWAP Scalping Signal Bot (signal-only)")
    parser.add_argument("--once", action="store_true", help="Bir marta skan (continuous emas)")
    parser.add_argument("--dry-telegram", action="store_true", help="Telegram o'rniga konsolga chiqarish")
    parser.add_argument("--source", default="auto", choices=["auto", "alpaca", "ibkr", "yfinance"],
                        help="Ma'lumot manbai (sukut auto)")
    args = parser.parse_args()

    print("=" * 60)
    print("Hasan Zone Breakout VWAP Scalping Signal Bot")
    print("⚠️  SIGNAL-ONLY — real order yo'q, auto-buy/sell yo'q.")
    print("=" * 60)

    if args.once:
        run_once(dry=args.dry_telegram, preferred=args.source)
        return

    interval = max(15, config.REFRESH_SECONDS)
    print(f"Continuous rejim — har {interval}s. To'xtatish: Ctrl+C")
    try:
        while True:
            try:
                run_once(dry=args.dry_telegram, preferred=args.source)
            except Exception as exc:  # noqa: BLE001 — sikl to'xtamasin
                print(f"Skan xatosi: {exc}", flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nBot to'xtatildi (Ctrl+C). Xayr!")


if __name__ == "__main__":
    main()
