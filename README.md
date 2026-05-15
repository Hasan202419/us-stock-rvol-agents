# us-stock-rvol-agents

Bu loyiha AQSh aksiyalarining AYNI (`relative volume / rvol`) va boshqa strategiyalar asosida skan, signal, AI tahlil, paper-order oqimi va Telegram integratsiyasini bir joyga to'playdi.

Ushbu README loyihani shaxsiy foydalanishga moslashtirish, API kalitlarini xavfsiz saqlash, lokalda ishga tushirish va Render'ga chiqarish bo'yicha amaliy ko'rsatma beradi.

## Tez boshlash

1. Kodni klonlash:

```bash
git clone https://github.com/Hasan202419/us-stock-rvol-agents.git
cd us-stock-rvol-agents
```

2. Virtual muhit va talablarni o'rnatish:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .\\.venv\\Scripts\\activate
pip install --upgrade pip
pip install -r requirements.txt
```

3. `.env` faylini sozlash:

```bash
cp .env.example .env
# yoki Windows PowerShell:
# copy .env.example .env
```

`.env` ichida odatda quyidagilar kerak bo'ladi:

- `OPENAI_API_KEY` yoki `DEEPSEEK_API_KEY`
- `POLYGON_API_KEY` yoki `FINNHUB_API_KEY` yoki Yahoo fallback
- `ALPACA_API_KEY` va `ALPACA_SECRET_KEY`
- `TELEGRAM_BOT_TOKEN` va `TELEGRAM_CHAT_ID`
- `RENDER_SERVICE_ID` yoki `RENDER_DEPLOY_HOOK_URL`

Paper orderlar tez blok bo‘lsa:
- `MAX_POSITION_SIZE_USD` ni realistik qiymatga qo‘ying (masalan `10000`).
- `TRADING_MODE=paper` va `ALPACA_BASE_URL=https://paper-api.alpaca.markets` ekanini tekshiring.

## Xavfsizlik

- Hech qachon haqiqiy API kalitlarini GitHub'ga commit qilmang.
- `.env` fayli `.gitignore` ichida ekanini tekshiring.
- Public repo bo'lsa, GitHub'da `private` qilishni ko'rib chiqing.
- Deploy kalitlarini repo ichiga emas, Render env vars ichiga joylang.

## Local start

Dashboard only:

```powershell
cd C:\Users\o8324\us-stock-rvol-agents
.\scripts\start_platform.ps1
```

Dashboard + Telegram bot:

```powershell
cd C:\Users\o8324\us-stock-rvol-agents
.\scripts\start_platform.ps1 -WithTelegram
```

Open `http://localhost:8501/`.

Minimal qo'l bilan ishga tushirish:

```bash
streamlit run dashboard.py
python scripts/telegram_command_bot.py
```

## Verification

Quick local verify:

```powershell
.\scripts\verify_local.ps1
```

Full queue:

```powershell
.\scripts\run_queue.ps1
```

API-only check:

```powershell
python scripts\check_apis.py
```

## Render

- `render.yaml` Streamlit **web** xizmati va Telegram **worker**ini belgilaydi.
- `sync: false` bo'lgan kalitlar Git'dan ko'chmaydi, ularni Render Dashboard → **Environment** da to'ldiring.
- Web uchun Blueprint sync, deploy hook yoki Render API orqali publish qilish mumkin.

### 24 / 7 ishlaydimi? (terminal vs bulut)

- **Kompyuterdagi terminal**da `streamlit run dashboard.py` yoki `python scripts/telegram_command_bot.py` ishlatsangiz, bu faqat **lokal** rejimdir. Terminal oynasini **yopsangiz** yoki kompyuter **olovatsangiz**, jarayon to'xtaydi — bu Render'dagi bot yoki sayt bilan aralashmasin.
- **Haqiqiy 24/7** uchun ikkala xizmat ham **Render Dashboard**da **Live** (yashil), so'ng ulanishlari:
  - **Telegram**: alohida **worker** konteyneri (`us-stock-rvol-telegram-bot`) `scripts/telegram_command_bot.py` ni uzoq vaqt ishga tushirib turadi (**long polling**). Kompyuteringiz o'chiq bo'lsa ham bot javob berishi shu yerni **Logs**idagi xatosiz ishga tushishiga bog'liq.
  - **Veb**: brauzerda ochadigan manzil **Render web URL** (`https://…onrender.com`), `http://localhost:8501` emas. Localhost faqat sizning mashinangizda ishlaydi.
- **«Veb ishlamayapti»** deb turganingizda: avvalo Dashboardda **web** servis **Sleeping** yoki **Failed** emasligini tekshiring. **Free** tarifda ba'zan veb so'rovsiz uzoq vaqt turib **uxlab** qoladi; `render.yaml`da `plan: starter` ko'rsatilgan — lekin hisobda servis hali ham bepul rejimda qolgan bo'lishi mumkin; shuni Render → **Instance** / **Plan** dan tekshiring.

Tez tekshiruv (`.env`da `RENDER_API_KEY`, `RENDER_WORKER_SERVICE_ID` bo'lsa):

```powershell
python scripts\render_worker_smoke.py
```

Worker + env sinxron + Telegram test (PowerShell):

```powershell
.\scripts\sync_render_telegram_env_and_smoke.ps1
```

Yana bir bor deploy qilish:

```powershell
python scripts\trigger_render_deploy.py
```

## Useful env compatibility

Older project env names are accepted during bootstrap:

- `MASSIVE_API_KEY` -> `POLYGON_API_KEY`
- `ALPACA_API_KEY_ID` -> `ALPACA_API_KEY`
- `ALPACA_API_SECRET_KEY` -> `ALPACA_SECRET_KEY`
- `ALPACA_KEY_ID` -> `ALPACA_API_KEY`

Optional provider order:

```env
MARKET_DATA_PROVIDER_PRIORITY=polygon,yahoo,alpaca,finnhub,alpha_vantage
```

## Yordamchi fayllar

- `.env.example` — kutilayotgan env ro'yxati
- `render.yaml` — Render blueprint
- `scripts/start_platform.ps1` — lokal dashboard / bot start
- `scripts/verify_local.ps1` — tez lokal verify
- `scripts/run_queue.ps1` — to'liq tekshiruv navbati
- `scripts/render_worker_smoke.py` — Render worker holati + Telegram API tez test
- `scripts/sync_render_telegram_env_and_smoke.ps1` — env sinxron + smoke

## Telegram chart va keng skan

- `/tv AAPL` yoki `/tv NASDAQ:NVDA` — TradingView chart link yuboradi.
- `/scan` — oddiy skan (`TELEGRAM_MAX_SYMBOLS`; **0 = cheklovsiz**, API dagi barcha US tradable).
- `/scanall` — keng qamrov (`TELEGRAM_MAX_SYMBOLS_ALL`; **0 = cheklovsiz**).
- `/plan` yoki `/plan AAPL` — oxirgi skandan professional trade plan matni.
- **Babir + AMT avtomatik**: `TELEGRAM_AUTO_PUSH_ENABLED=true` — worker fonida keng skan (`TELEGRAM_AUTO_PUSH_USE_SCANALL=true` → ko‘p ticker). Har pushda **2 xabar**: (1) Babir signallar/kuzatuv + ichida **AMT BUY · VAL↑** kartochkalari; (2) to‘liq AMT ro‘yxati. Ma’lumot: **Yahoo** (intraday birinchi) + **Polygon/Massive** (`POLYGON_API_KEY` / `MASSIVE_API_KEY`). Parallel: `TELEGRAM_SCAN_MAX_WORKERS=16` (ketma-ket emas).
- `/status` — worker/env tez diagnostika (paper config, keylar, risk limitlar).
- `/risk` — risk limitlarni alohida ko‘rsatadi.
- **Deyarli barcha AQSH aksiyalari**: `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` yoki `POLYGON_API_KEY` bo‘lishi kerak (bo‘lmasa — qisqa fallback ro‘yxat). `.env` da `TELEGRAM_MAX_SYMBOLS=0` yoki `TELEGRAM_MAX_SYMBOLS_ALL=0` — API qaytargan barcha US tradable; keyin Telegramda `/scanall` (avto-pushda ham). Skan vaqti va API limitlari ticker soniga qarab keskin oshadi; `SCAN_MAX_WORKERS` ni ehtiyotkorlik bilan oshiring.
- **Kunlik tayyorlov (O‘zbekiston vaqti)**: `.env` da `TELEGRAM_AUTO_PUSH_AT=18:30` va `TELEGRAM_AUTO_PUSH_TZ=Asia/Tashkent` (default TZ) — avtomatik push faqat **NY hafta ichidagi** kunlarda shu soatda ishlaydi (shanba/yakshanba ET da o‘tkazib yuboriladi). NY bayram kunlari hozircha hisobga olinmaydi. Soatni NY ochilishidan oldin qoldirish uchun taxminan **18:00–19:00** oralig‘ida sinab ko‘ring (DST bilan bir necha daqiqa siljishi mumkin).

## Analyst trade plan + Volume Ignition

- **`STRATEGY_MODE=volume_ignition`** — kunlik shamlar bo‘yicha “volume ignition” filtri ([agents/strategy_volume_ignition.py](agents/strategy_volume_ignition.py)). Skaner quyidagi mezonlarni tekshiradi; har biri `.env` da `IGNITION_*` (yoki umumiy `MIN_*`) bilan sozlanadi:

| Skaner mezoni | Env kaliti | Sukut (misol) |
|---------------|------------|---------------|
| Oxirgi 3 kun ketma-ket hajm o‘sishi | (kodda `volume_three_up`) | — |
| Joriy hajm ≥ N× 20 kunlik o‘rtacha | `IGNITION_VOL_VS_20D_AVG` | `2` |
| RVOL ≥ N | `IGNITION_MIN_RVOL` | `2` |
| 3 kunlik narx o‘sishi ≤ N% | `IGNITION_MAX_3DAY_GAIN_PCT` | `10` |
| Qarshilikgacha masofa ≤ N% | `IGNITION_MAX_RES_DISTANCE_PCT` | `5` |
| Qarshilik lookback (kun) | `IGNITION_RESISTANCE_LOOKBACK` | `20` |
| Yuqori dip (higher low) | (kodda `higher_low`) | — |
| Narx > EMA9, EMA20 dan juda uzoq emas | `IGNITION_EMA_EXTENSION_MAX_PCT` | `8` |
| ATR o‘sishi | (kodda `atr_rising`) | — |
| Cho‘zilgan harakat taqiqi | `IGNITION_EXTENDED_MOVE_BAN_PCT`, `IGNITION_EXTENDED_LOOKBACK` | `20`, `20` |
| Parabolik diapazon / 2 kun sakrash | `IGNITION_PARABOLIC_RANGE_PCT`, `IGNITION_PARABOLIC_2DAY_JUMP_PCT` | `15`, `8` |
| Minimal o‘rtacha kunlik hajm | `IGNITION_MIN_AVG_VOLUME` | `1000000` |
| Minimal narx (umumiy) | `MIN_PRICE` | `1` |
| Minimal kunlik hajm (umumiy) | `MIN_VOLUME` | `200000` |

`ignition_trend_stage` qiymatlari: **Accumulation** → **Ignition** → **Breakout** (qarshilik yaqinligi va hajm kontekstiga qarab).
- **LLM professional plan**: `ANALYST_TRADE_PLAN_ENABLED=true` (sukut) — ChatGPT/DeepSeek JSON ichida `trade_plan` obyekti (company, catalyst, TA, risk, entry/stop/target, R:R, execution, summary). Matn dashboard va `analyst_trade_plan_text` maydonida; LLM o‘chiq bo‘lsa deterministik reja [agents/trade_plan_format.py](agents/trade_plan_format.py) dan to‘ldiriladi.
- **Telegram**: `/plan` yoki `/plan AAPL` — oxirgi `/scan` natijasidan (`state/last_telegram_scan.json`) bitta ticker bo‘yicha to‘liq plan matni.
- **Paper savdo**: [agents/risk_manager_agent.py](agents/risk_manager_agent.py) `allow_order`, qaror, SL/TP va R:R tekshiruvi — plan tavsiya; buyruq avtomatik emas.
- **Market Shield** ([agents/market_shield.py](agents/market_shield.py)): har skan oldidan SPY/QQQ/VIX → `BULL` / `NEUTRAL` / `RISK_OFF` / `NEWS_LOCK`; long BUY va paper faqat regime ruxsat berganda. TradingView referens: [pine/market_shield_filter.pine](pine/market_shield_filter.pine).
- **Eslatma**: LLM va skaner matnlari tahlil/tavsiya; broker buyrug‘i yoki investitsiya kafolati emas. `ANALYST_TRADE_PLAN_ENABLED=false` bilan token xarajatini kamaytirish mumkin.

- Eslatma: aniq **son** limit qo‘yganingizda ro‘yxat API dan katta bo‘lsa, ba’zi yo‘llarda **alfavit bo‘yicha kesiladi**. **0** (cheklovsiz) rejimda Alpaca bitta javobda beradi; Polygon esa sahifalab to‘liq yig‘adi (Polygon tomonda max ~5000 sahifa xavfsizlik cheklovi).