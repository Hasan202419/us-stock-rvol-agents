# Order Flow strategiyasi — CLC qoidasi (`/flow`)

Manba: **The Order Flow Playbook** (Fabio Valentini / Carmine Rosato). Asosiy g'oya —
yalang'och narx (candlestick) yolg'on gapirishi mumkin; haqiqiy maqsad **Order Flow**da.
Uchala ustun mos kelmaguncha BUY tugmasi bosilmaydi.

## CLC qoidasi (Carmine Rosato)

| Ustun | Savol | Bizda hisoblanishi (OHLCV proksisi) |
|---|---|---|
| **Context** | Bozor Qafas (Balance) yoki Siqilish (Squeeze) rejimidami? Kim qopqonda? | Konsolidatsiya qutisi (Cage) aniqlanadi; oxirgi sham qafas tepasidan chiqsa — Siqilish (breakout long). Qafas o'rtasida — savdo yo'q. |
| **Location** | Narx muhim darajadami (qafas/value chekkasi) yoki o'rtadami? | `amt_val`/`amt_vah`/`amt_poc_proxy` bo'lsa: VAH ustida yoki VAL chekkasida — kuchli; POC (o'rta) yaqinida — yangi kirish emas. VAL/VAH yo'q bo'lsa qafas chekkasi ishlatiladi. |
| **Confirmation** | Speed of Tape tezlashyaptimi? Katta buyurtmalar yutilyaptimi (absorption)? | RVOL ≥ chegara (Speed of Tape proksisi) + **Initiative Candle** (kuchli tana, tepada yopilish). Absorption (katta hajm + kichik natija + pastda yopilish) — reversal ogohlantirishi. |

> "Uchala ustun mos kelmaguncha, men hech qachon tugmani bosmayman."

## Verdikt va ikon

- 🟢 **KIRISH** — uchala ustun ✅ (3/3)
- 🟡 **KUTING** — ikkita ustun (2/3)
- ⛔ **O'TKAZ** — ikkitadan kam, **yoki** Absorption ogohlantirishi (har qanday holatda)

## Telegram

```
/flow NVDA      → Order Flow CLC hisobot (ikon + 3 ustun + tahlil)
/buy NVDA       → BUY hisobotiga Order Flow (CLC) qatori avtomatik qo'shiladi
```

`/flow` ma'lumotni avval oxirgi `/scan2b` dan, bo'lmasa jonli `MarketDataAgent` dan oladi
(`/scan` shart emas).

## ENV sozlamalari

| Variable | Sukut | Vazifa |
|---|---|---|
| `ORDERFLOW_CAGE_LOOKBACK` | 10 | Qafas (Cage) uchun nechta oldingi sham |
| `ORDERFLOW_MIN_RVOL` | 1.8 | Speed of Tape proksisi minimal RVOL |
| `ORDERFLOW_MIN_BODY_FRAC` | 0.5 | Initiative Candle minimal tana ulushi (tana/diapazon) |
| `ORDERFLOW_MIN_CLOSE_POS` | 0.6 | Initiative Candle minimal yopilish o'rni (0=quyi, 1=tepa) |

## Cheklov / eslatma

- Haqiqiy DOM/footprint/tape ma'lumoti yo'q — barchasi OHLCV + hajm + VAL/VAH/POC
  proksilaridan deterministik hisoblanadi. Bu — **yondashuv**, aniq order-flow terminali emas.
- Eng yaxshi natija intraday (1m/5m) shamlarda — `/scan2b` MTF konveyeri bilan.
- O'tmish/model — kelajak kafolati emas.
