# Hasan Auto-Refresh Scalping Signal Scanner

US aksiyalari uchun **avtomatik yangilanadigan skalping signal** dashboard'i (Streamlit).

> ⚠️ **ENG MUHIM QOIDA:** Bu tizim **REAL ORDER QO'YMAYDI**. Auto-buy yo'q, auto-sell yo'q,
> jonli ijro yo'q. V1 — faqat **signal + paper-review**. Standart qaror **qat'iy**:
> setup toza bo'lmasa **NO_TRADE**. Yomon savdodan ko'ra savdoni o'tkazib yuborish yaxshiroq.

---

## Bu nima qiladi?

Asosiy g'oya: **"Hajm o'zi signal emas. Hajm oshganda NARX nima qiladi?"**

Tizim har bir tickerni tekshiradi va **VWAP Reclaim + Volume-Time Confirmation** setup'ini
qidiradi. Keyin 0–10 ball beradi va qaror chiqaradi:

| Ball | Qaror | Rang |
|---|---|---|
| 0–4 | `NO_TRADE` | 🔴 qizil |
| 5–6 | `WATCHLIST` | 🟡 sariq |
| 7–8 | `PAPER_READY` | 🟢 yashil |
| 9–10 | `HIGH_QUALITY_PAPER_READY` | 🟢 to'q yashil |

**Hatto HIGH_QUALITY_PAPER_READY ham avtomatik BUY emas** — faqat manual review ruxsati.

---

## Savdo uslubi (shu tizim uchun)

- Faqat **US aksiyalari**, faqat **LONG/BUY**
- **Day trading / scalping**, asosiy timeframe **5 daqiqa**, yordamchi **1 daqiqa**
- Narx oralig'i **$0.50 – $5.00**
- E'tibor: RVOL, joriy hajm, dollar volume, spread, VWAP reclaim, EMA9/EMA20, 5-min tasdiq
- **Risk nazorati foydadan muhimroq** (prop-uslub)

---

## Fayllar tuzilishi

```
hasan_scalping_scanner/
├── app.py            # Streamlit dashboard (asosiy)
├── data_source.py    # Alpaca → IBKR(placeholder) → yfinance fallback
├── indicators.py     # VWAP, EMA, RVOL, spread, volume spike (sof matematika)
├── strategy.py       # VWAP reclaim + scoring + qaror (qat'iy mantiq)
├── risk_lock.py      # Psixologik himoya + alert format
├── config.py         # Barcha chegaralar va risk qiymatlari
├── requirements.txt
└── README.md
```

---

## O'rnatish va ishga tushirish (Windows)

PowerShell yoki CMD'da, shu papka ichida:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Brauzer avtomatik ochiladi (`http://localhost:8501`).

### Mac / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

---

## Ma'lumot manbalari (tartib)

1. **Alpaca API** — `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` env bo'lsa (realtime quote + bid/ask)
2. **IBKR Web API** — `IBKR_WEB_API_ENABLED=true` bo'lsa (placeholder)
3. **yfinance** — bepul zaxira (kalit shart emas)

> Agar ma'lumot kechikkan yoki to'liq bo'lmasa (masalan bid/ask yo'q), signal
> **WATCHLIST only** deb belgilanadi — `PAPER_READY` bo'la olmaydi.

Kalitlarni o'rnatish (ixtiyoriy, Windows):
```bat
set ALPACA_API_KEY=sizning_kalit
set ALPACA_SECRET_KEY=sizning_sekret
```

---

## Auto-refresh (avtomatik yangilanish)

- Sidebar'dan **30 / 60 soniya / qo'lda** tanlanadi
- **🔄 Scan Now** tugmasi — darhol qayta skanlash
- "Oxirgi yangilanish" vaqti ko'rsatiladi
- Ma'lumot xato bo'lsa — aniq xato xabari chiqadi

---

## Risk-lock (psixologik himoya) 🛡️

Sidebar'da quyidagilarni halollik bilan belgilang — tizim sizni himoya qiladi:

- Kuniga **maksimal 3 savdo**
- Savdo boshiga risk: **$10–$20** (o'rganish bosqichi)
- Kunlik yumshoq stop: **−$50**, qattiq stop: **−$70**
- **Ketma-ket 2 zarar = to'xta**
- Stop-loss yo'q = `NO_TRADE`
- R/R < 1:2 = `NO_TRADE`
- "Zararni qoplamoqchiman" / charchagan / asabiy / chalkash bo'lsangiz → **STOP_TRADING**

STOP_TRADING holatida tizim yangi setup tavsiya qilmaydi.

---

## Setup mantig'i (qisqacha)

**VWAP Reclaim + Volume-Time Confirmation:**
- Narx VWAP ostida/yaqinida edi → VWAP'ni qaytarib egalladi (reclaim)
- 5-min sham VWAP **ustida yopildi**
- Keyingi sham VWAP ustida **ushlab turibdi** yoki retest qilib sakradi
- Hajm portlashi (volume spike) ≥ **1.5x**
- EMA9 ko'tarilmoqda yoki EMA9 > EMA20
- Narx VWAP'dan **juda uzoq emas** (chase yo'q)
- Stop-loss **aniq**, R/R ≥ **1:2**

**Entry:** reclaim sham high ustida YOKI VWAP retest ushlasa.
**Stop:** VWAP ostida YOKI reclaim sham low ostida.
**Target1:** 1R yoki day high. **Target2:** 2R.

Agar stop aniq bo'lmasa yoki R/R < 1:2 → **NO_TRADE**.

---

## Alert formati (Telegram — tayyor, hali yuborilmaydi)

`PAPER_READY` signal uchun matn tayyorlanadi (`risk_lock.build_alert_text`).
Telegram yuborish **hozircha o'chiq** (`send_telegram_alert_placeholder` → `False`).
Keyingi versiyada bot token + chat_id qo'shiladi.

---

## Eslatma / cheklov

- yfinance ma'lumoti **kechikkan** bo'lishi mumkin (realtime emas) → spread ko'pincha UNKNOWN → WATCHLIST.
- Realtime + bid/ask uchun **Alpaca** tavsiya etiladi.
- Bu — **ta'lim/yordam vositasi**, moliyaviy maslahat emas. O'tmish natija kelajak kafolati emas.
