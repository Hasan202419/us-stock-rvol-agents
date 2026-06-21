# Hasan Zone Breakout VWAP Scalping Signal Bot

US aksiyalari uchun **signal-only Telegram bot** — zona breakout + VWAP reclaim + hajm-vaqt
tasdig'i asosida yuqori sifatli setup paydo bo'lganda **Telegram alert** yuboradi.

> ⚠️ **ENG MUHIM QOIDA:** Bu bot **REAL ORDER QO'YMAYDI**. Auto-buy yo'q, auto-sell yo'q,
> jonli ijro yo'q. Faqat **signal + Telegram xabar**. Standart qaror **qat'iy**: setup toza
> bo'lmasa **NO_TRADE**. *Yomon savdodan ko'ra savdoni o'tkazib yuborish yaxshiroq.*

---

## Bot nima qiladi?

Asosiy g'oya: **"Hajm o'zi signal emas. Zona o'zi signal emas. Eng yaxshi signal — narx muhim
zona ichida konsolidatsiya qilib, zona yuqorisini buzib, VWAP'ni qaytarib egallab, hajm bilan
tasdiqlangan, aniq stop-loss va 1:2 risk/reward bo'lganda."**

Har 60 soniyada (sozlanadi) ikki rejimda skanlaydi, ball beradi va qaror chiqaradi:

| Ball | Qaror | Telegram |
|---|---|---|
| 0–5 | `NO_TRADE` | ❌ |
| 6–8 | `WATCHLIST` | ❌ |
| 9–11 | `PAPER_READY` | ✅ |
| 12+ | `HIGH_QUALITY_PAPER_READY` | ✅ |

Telegramga **faqat PAPER_READY va HIGH_QUALITY_PAPER_READY** yuboriladi (10 daqiqa dedup —
spam yo'q). **Hatto HIGH_QUALITY ham avtomatik BUY emas** — faqat manual review.

---

## Multi-timeframe (vaqt oraliqlari)

- **1H** — asosiy demand/supply (qo'llab-quvvatlash/qarshilik) zonalari, kontekst
- **5M** — asosiy setup: konsolidatsiya, VWAP reclaim, hajm portlashi
- **3M** — tezroq tasdiq: zona buzilishi, higher-low
- **1M** — faqat kirish vaqtini aniqlash (yolg'iz signal bermaydi)

---

## Fayllar tuzilishi

```
hasan_zone_breakout_bot/
├── main.py            # kirish nuqtasi (continuous / --once)
├── config.py          # barcha sozlamalar (.env dan o'qiydi)
├── data_alpaca.py     # Alpaca ma'lumoti (1-manba)
├── data_ibkr.py       # IBKR.com Web API (hosted) yoki ib_insync Gateway
├── data_yfinance.py   # bepul zaxira (faqat test)
├── indicators.py      # VWAP, EMA9/20, ATR, RVOL, spread, hajm portlashi
├── zones.py           # demand/supply zona + consolidation + breakout
├── market_regime.py   # SPY/QQQ rejimi (bullish/choppy/bearish)
├── strategy.py        # zona-breakout scoring + qaror
├── risk_lock.py       # prop himoya (3 savdo/kun, -50/-70, emotsional lock)
├── telegram_bot.py    # REAL Telegram yuborish + dedup
├── scanner.py         # 2 rejim: Large Cap + Penny Momentum
├── logger.py          # scan_log.csv + alerts_log.csv
├── halal_filter.py    # halal_watchlist.csv asosida HALAL_STATUS
├── halal_watchlist.csv
├── requirements.txt
├── .env.example
└── README.md
```

---

## 1-qadam: Python o'rnatish

[python.org/downloads](https://www.python.org/downloads/) dan **Python 3.10+** ni yuklab,
o'rnating. Windows'da o'rnatishda **"Add Python to PATH"** ni belgilang.

Tekshirish (CMD/PowerShell):
```
python --version
```

## 2-qadam: Virtual muhit (venv)

Loyiha papkasida:
```
python -m venv .venv
.venv\Scripts\activate
```
(Mac/Linux: `python3 -m venv .venv && source .venv/bin/activate`)

## 3-qadam: Kutubxonalarni o'rnatish

```
pip install -r requirements.txt
```

## 4-qadam: .env faylni yaratish

```
copy .env.example .env
```
(Mac/Linux: `cp .env.example .env`). Keyin `.env` ni ochib kalitlarni qo'ying.

## 5-qadam: Telegram bot token olish

1. Telegram'da **@BotFather** ni oching → `/newbot` → nom bering.
2. BotFather sizga **token** beradi (masalan `123456:ABC-...`) → `.env` da `TELEGRAM_BOT_TOKEN=` ga qo'ying.

## 6-qadam: Telegram chat ID olish

1. O'z botingizga biror xabar yozing.
2. Brauzerda oching: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. `"chat":{"id":123456789}` — shu raqamni `.env` da `TELEGRAM_CHAT_ID=` ga qo'ying.

## 7-qadam: Alpaca API kalitlari (tavsiya — realtime + bid/ask)

1. [alpaca.markets](https://alpaca.markets/) da ro'yxatdan o'ting (Paper account bepul).
2. **API Key** va **Secret Key** ni `.env` ga qo'ying:
   ```
   ALPACA_API_KEY=...
   ALPACA_SECRET_KEY=...
   ALPACA_BASE_URL=https://paper-api.alpaca.markets
   ```

### IBKR.com (ixtiyoriy — Gateway/noutbuk shart emas)
Hosted Client Portal Web API'ni yoqish uchun `.env` da:
```
IBKR_WEB_API_ENABLED=true
IBKR_WEB_API_BASE_URL=https://<sizning-gateway>/v1/api
```
Bo'lmasa Alpaca/yfinance ishlaydi.

## 8-qadam: Botni ishga tushirish

**Davomiy (continuous) rejim** — har 60 soniyada skanlaydi:
```
python main.py
```

**Bir marta skan** (sinov uchun):
```
python main.py --once
```

**Kalitsiz sinov** (Telegram o'rniga konsolga chiqaradi):
```
python main.py --once --dry-telegram --source yfinance
```

## To'xtatish

Continuous rejimda **Ctrl + C** bosing.

---

## Windows tezkor buyruqlar (hammasi birga)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python main.py
```

---

## Ikki skaner rejimi

**MODE 1 — Large Cap Quality:** AAPL, NVDA, TSLA, AMD, MSFT, META, GOOGL, AMZN, AVGO, PLTR,
SOFI, ARM, QQQ, SPY (likvid, tor spread, kuchli dollar volume).

**MODE 2 — Penny Momentum:** $0.50–$5.00, joriy hajm ≥1M, RVOL ≥2, dollar volume ≥$500k,
% o'zgarish +3%..+20%, spread ≤2%.

`.env` da `SCAN_MODE=large_cap | penny | both` bilan tanlanadi.

---

## Risk-lock (psixologik himoya) 🛡️

- Kuniga **maksimal 3 savdo**
- Risk: **$10–$20** (o'rganish bosqichi)
- Kunlik yumshoq stop **−$50**, qattiq stop **−$70**
- **Ketma-ket 2 zarar = STOP_TRADING**
- Stop yo'q = `NO_TRADE` · R/R < 1:2 = `NO_TRADE` · choppy bozor = WATCHLIST only

---

## Halal filtr

`halal_watchlist.csv` (format: `ticker,status`) — COMPLIANT / NOT_COMPLIANT. Ro'yxatda
bo'lmasa **UNKNOWN** va alertда "Halal status not verified." ogohlantirishi chiqadi.

---

## Loglar

- `scan_log.csv` — har skan natijasi
- `alerts_log.csv` — yuborilgan Telegram alertlar

---

## Nega bu bot signal-only?

- **Sizni himoya qiladi:** emotsional savdo, qasos (revenge) savdosi, ortiqcha savdo va
  stop-loss'siz savdolardan saqlaydi.
- **Order yo'q:** kodda hech qanday buy/sell/execute funksiyasi YO'Q — faqat `sendMessage`.
- **Qaror siznikida:** bot faqat "bu yerga qarang" deydi; kirish/chiqishni siz qo'lда,
  intizom bilan qilasiz.
- Bu — **ta'lim/yordam vositasi**, moliyaviy maslahat emas. O'tmish natija kelajak kafolati emas.
