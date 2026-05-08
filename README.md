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

- `render.yaml` Streamlit web service va Telegram worker'ni belgilaydi.
- `sync: false` bo'lgan kalitlar Git'dan ko'chmaydi, ularni Render Dashboard'da to'ldiring.
- Web deploy uchun Blueprint sync, deploy hook yoki Render API flow ishlatish mumkin.

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