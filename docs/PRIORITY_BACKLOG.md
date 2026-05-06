# Ustunlik asosida backlog (texnik xulosa + mavjud kod)

Masalan ustun tartib bilan PR larga ajratiladi. Batafsil jadval: [`TEXNIK_XULOSA_GAP_MATRIX.md`](TEXNIK_XULOSA_GAP_MATRIX.md).

## P0 — barqarorlik va narxi

| Vazifa | Maqsad |
|--------|--------|
| LLM 429/backoff va max_retries | Tekshirish: [`agents/chatgpt_analyst_agent.py`](../agents/chatgpt_analyst_agent.py) (`OPENAI_ANALYSIS_MAX_RETRIES`, `OPENAI_ANALYSIS_RETRY_BASE_SEC`) |
| Telegram bitta polling / webhook holatlarida 409 monitoring | Qo‘lda; worker loglari |

## P1 — funksiya (minimal ROI)

| Vazifa | Holat |
|--------|-------|
| Backtest MVP — SMA crossover + CLI + `/backtest` | **Qilingan**: [`agents/simple_backtest_mvp.py`](../agents/simple_backtest_mvp.py), [`scripts/simple_backtest.py`](../scripts/simple_backtest.py), Telegram |
| Polygon/Yahoo keyin kunlik uchun Alpha Vantage | **Qilingan**: [`agents/alpha_vantage_client.py`](../agents/alpha_vantage_client.py), [`MarketDataAgent`](../agents/market_data_agent.py) |
| Skan uchun PDF OCR vositalari | [`scripts/extract_pdf_text.py`](../scripts/extract_pdf_text.py) + [`requirements-tools.txt`](../requirements-tools.txt) |

## P2 — kengaytirish

| Vazifa | Izoh |
|--------|------|
| **Webhook rejimi** (HTTPS domen + Render routing) | Hozir asosan long-polling; [`telegram_command_bot`](../scripts/telegram_command_bot.py) |
| **Foydalanuvchi DSL** qoida matni (.envdan emas runtime parser) | Hujjatdagi vizyon; kodda strategiya parametrlari |
| **vectorbt / Backtrader** chuqur backtest | KPI, walk-forward, parametrlarni optimallaash |
| Navbat (**Redis/RQ**) + **WebSocket** real-vaqt | Yuqori hajm uchun |
| Telegram **chat/user bo‘yicha rate limit** | Spam/oldini olish |
| Monitoring (Sentry, metrik exporter) | Xulosa ijodiy bosqichi |

## P3 — hujjat / kitob

| Vazifa | Izoh |
|--------|------|
| `Engineering_the_Trading_Edge.pdf` OCR | Qo‘lda: [`docs/generated/ENGINEERING_THE_TRADING_EDGE_NOTE.md`](generated/ENGINEERING_THE_TRADING_EDGE_NOTE.md); matndan keyin VWAP/session qoidalari bilan kodni tekshirish |

Har bir ustun uchun GitHub Issues yoki ichki kartochka ochib, “Definition of Done” ni aniq yozing (masalan, backtest uchun: sinf testlari + dokumentatsiya + `/help` yangilanishi).
