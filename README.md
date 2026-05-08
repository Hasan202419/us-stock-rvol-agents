# us-stock-rvol-agents

Bu loyiha AQSh aksiyalarining AYNI (relative volume / rvol) va boshqa strategiyalar asosida skan va signal yuboradigan dashboard + Telegram bot to'plami.

Ushbu README loyihani shaxsiy foydalanishga moslashtirish, kerakli API kalitlarini joylashtirish va xavfsiz saqlash bo'yicha oddiy ko'rsatmalarni o'zbek tilida beradi.

Tez boshlash

1) Kodni klonlash:

```bash
git clone https://github.com/Hasan202419/us-stock-rvol-agents.git
cd us-stock-rvol-agents
```

2) Virtual muhit va talablarni o'rnatish:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .\\.venv\\Scripts\\activate
pip install --upgrade pip
pip install -r requirements.txt
```

3) .env faylini sozlash:

- Faylni nusxalash va maxfiy kalitlarni kiritish:

```bash
cp .env.example .env
# yoki Windows PowerShell:
# copy .env.example .env
```

- .env ichida quyidagi kalitlarni to'ldiring (hech qachon real kalitlarni repoga commit qilmang):

  - OPENAI_API_KEY — LLM chaqiriqlari uchun (yoki DEEPSEEK).
  - POLYGON_API_KEY yoki FINNHUB_API_KEY yoki YAHOO fallback.
  - ALPACA_API_KEY va ALPACA_SECRET_KEY (agar alpaca bilan order jo'natishmoqchi bo'lsangiz).
  - TELEGRAM_BOT_TOKEN va TELEGRAM_CHAT_ID — Telegram bot va chat uchun.
  - RENDER_SERVICE_ID / RENDER_DEPLOY_HOOK_URL — agar Render-ga joylayotgan bo'lsangiz.

- .env.example fayli loyihaning qaysi kalitlarni kutishini ko'rsatadi. .env faylini Git dan chiqarib yuborish uchun .gitignore-ga qo'shing (ko'pincha .env avtomatik chiqariladi).

Xavfsizlik bo'yicha tavsiyalar

- Hech qachon haqiqiy API kalitlarini GitHub-ga push qilmang.
- Localda .env faylni .gitignore ro'yxatida ekanligiga ishonch hosil qiling.
- Loyiha GitHub sahifasida public bo'lsa, reponi private (xususiy) qiling: Repository → Settings → Danger Zone → Change repository visibility → Make private.
- Continuous Deployment (Render yoki boshqa) ishlatganda, keys-ni Render / Vercel / netlify muhiti o'zgaruvchilari (Env Vars) sifatida qo'shing — bu orqali repo ichiga kalit qo'yilmaydi.

Minimal ishga tushirish

- Dashboard (Streamlit):

```bash
streamlit run dashboard.py
# yoki render.yaml bo'yicha deploy qiling
```

- Telegram bot (lokal):

```bash
python scripts/telegram_command_bot.py
```

API to'ldirishni tekshirish (tez):

```bash
# .env to'ldirilganligini tekshirish
python -c "import os; print('OPENAI=', bool(os.getenv('OPENAI_API_KEY')))
"
```

Yordamchi fayllar

- .env.example — barcha kutilayotgan o'zgaruvchilar ro'yxatini o'z ichiga oladi.
- render.yaml — Render uchun blueprint; deploy muhit o'zgaruvchilarini avtomatlashtirish uchun ishlatiladi.

Qanday qilib reponi shaxsiy (private) qilasiz

1. GitHub sahifasida repoga o'ting.
2. Settings → Danger Zone bo'limiga kiring.
3. Change repository visibility → Make private.
4. Agar repo public bo'lsa va siz uni private qilganingizda, forklar va boshqa public URL-lar saqlanib qolishi mumkin — diqqat bilan tekshiring.

Keyingi qadamlar (men bajara oladigan ishlar)

- Agar xohlasangiz, men README.md-ni to'liq o'zbek tilida yanada kengaytiraman (misollar, tez-yo'l troubleshooting, ko'proq buyruqlar).
- Men .github/workflows yoki render.yaml asosida deploy skriptlarini tekshirib, maxfiylar qanday ulanishini tushuntirib beraman.
- Agar siz ruxsat bersangiz, repoga yangi fayllar (masalan, API checklist) qo'shishim yoki README ni yana yangilashim mumkin.

---

Menga ayting: README-ni yana kengaytiraymi yoki biror faylni bevosita repoga qo'shaymi?