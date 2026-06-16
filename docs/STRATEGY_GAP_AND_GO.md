# Gap-and-Go strategiyasi — bozor tadqiqoti va spetsifikatsiya

> Status: v1 (kunlik shamlarda backtest qilinadigan model). Jonli skan + `backtest_engine` + `/discover` sweep bilan integratsiya qilingan.

## 1. Edge / sabab (nega ishlaydi)

**Gap-and-Go** — eng eski va eng hujjatlangan momentum kunlik-savdo (day-trade) qoliplaridan biri. G'oya:

- Aksiya kechagi yopilishdan sezilarli **gap up** bilan ochiladi (katalizator: hisobot, yangilik, sektor harakati, premarket hajmi).
- Gap **abnormal hajm (RVOL)** bilan birga kelsa — bu institutsional qiziqish belgisidir, shunchaki shovqin emas.
- Agar narx ochilishdan keyin gapni **ushlab tursa** (gapni to'ldirib pastga tushmasa) va kunni yuqori qismida yopsa — qisqa muddatli **davom (continuation)** ehtimoli yuqori bo'ladi.

Aksincha holat — **gap-and-fade**: gap up ochiladi, lekin sotuvchilar narxni kechagi yopilish tomon qaytaradi. Strategiyaning vazifasi — *go* (davom) ni *fade* (qaytish) dan ajratish. Buni biz **yopilish o'rni** (close position) bilan qilamiz.

## 2. Kirish shartlari (kunlik model)

`gap = (bugun_open − kecha_close) / kecha_close × 100`

| Qoida | Kalit | Sukut | Izoh |
|---|---|---|---|
| Gap up | `gap_up` | `GAP_GO_MIN_GAP_PCT=3` | Gap ≥ 3% |
| Gap charchamagan | `gap_exhausted` | `GAP_GO_MAX_GAP_PCT=20` | Gap ≤ 20% (blow-off/parabolikni chetlash) |
| Abnormal hajm | `rvol` | `GAP_GO_MIN_RVOL=2` | RVOL ≥ 2× |
| Likvidlik | `liquidity` | `GAP_GO_MIN_AVG_VOLUME=500000` | O'rtacha hajm yetarli |
| Narx pol | `price_min` | `GAP_GO_MIN_PRICE=2` (yoki `MIN_PRICE`) | Penny stocklarni chetlash |
| Gap ushlandi ("Go") | `held_gap` | `GAP_GO_MIN_CLOSE_POSITION=0.5` | Yopilish kun diapazonining yuqori yarmida **va** kechagi yopilishdan yuqori |

Barcha qoidalar o'tsa → `strategy_pass = True`.

## 3. Risk / chiqish

- **Entry**: gap kuni yopilishi (kunlik model; jonli day-trade da ochilish/premarket-high breakout bo'ladi).
- **Stop**: gap kuni pasti (`low`) ostida — chunki u gapni "ushlab turdi". Juda uzoq bo'lsa `GAP_GO_STOP_CAP_PCT=8%` bilan cheklanadi.
- **Target**: `entry + GAP_GO_REWARD_R × risk` (sukut `GAP_GO_REWARD_R=2` → 2R).
- `backtest_engine` bu `stop_suggestion`/`take_profit_suggestion` ni oldinga qarab (target/stop/timeout) o'lchaydi.

## 4. Sozlamalar (.env)

```bash
STRATEGY_MODE=gap_and_go          # jonli skan shu strategiyani ishlatsin
GAP_GO_MIN_GAP_PCT=3
GAP_GO_MAX_GAP_PCT=20
GAP_GO_MIN_RVOL=2
GAP_GO_MIN_AVG_VOLUME=500000
GAP_GO_MIN_PRICE=2
GAP_GO_MIN_CLOSE_POSITION=0.5
GAP_GO_STOP_CAP_PCT=8
GAP_GO_REWARD_R=2
```

## 5. Sinash (backtest + discovery)

```bash
# Bitta ticker:
python scripts/simple_backtest.py NVDA --strategy gap_go --horizon 10

# Telegram:
/backtest NVDA gap         # gap-and-go backtest
/discover                  # TELEGRAM_BACKTEST_STRATEGY=gap_and_go bo'lsa sweep gap grid ustida
```

`/discover` (yoki `sweep_thresholds`) `GAP_GO_MIN_GAP_PCT × GAP_GO_MIN_RVOL` to'rini bir nechta ticker tarixida sinab, **expectancy** bo'yicha eng yaxshi sozlamani topadi.

## 6. Cheklovlar / keyingi qadamlar

- Kunlik model gapni *kun yopilishida* baholaydi; haqiqiy intraday gap-and-go ochilish + premarket-high breakout + VWAP stop bilan ishlaydi (intraday data kerak — keyingi versiya).
- "Go" tasdig'i hozir faqat yopilish o'rniga tayanadi; intradayda birinchi 1–5 daqiqa barlari aniqroq.
- Katalizator (hisobot/yangilik) hozir filtrlanmaydi — gap + RVOL uni bilvosita ushlaydi.
- O'tmish natija kelajak kafolati emas; har doim paper-test (`/paper preview`) bilan tasdiqlang.
