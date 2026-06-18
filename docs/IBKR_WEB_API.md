# IBKR hosted Web API — noutbuk/Gateway shart emas

Bot endi IBKR ma'lumotini **ikki yo'l** bilan olishi mumkin:

| Yo'l | Talab | Telefonda? |
|---|---|---|
| **Eski**: `ib_insync` + IB Gateway/TWS | Kompyuterda dastur **doim ochiq** (24/7) | ❌ Yo'q |
| **Yangi**: Client Portal **Web API** (REST) | Gateway bulutda yoki OAuth-proksi | ✅ Ha — hech narsa ochiq turmaydi |

Kod avtomatik **avval Web API** ni sinaydi (`IBKR_WEB_API_ENABLED=true` bo'lsa), bo'lmasa
eski `ib_insync` ga tushadi. Hech biri bo'lmasa — Alpaca/Polygon/Yahoo ishlaydi (hozirgidek).

## Sozlash (Render → Environment)

```
IBKR_WEB_API_ENABLED=true
IBKR_WEB_API_BASE_URL=https://<gateway-yoki-proksi>/v1/api
IBKR_WEB_API_TOKEN=<ixtiyoriy Bearer token (OAuth/sessiya)>
IBKR_WEB_API_VERIFY_SSL=false   # self-signed gateway uchun
```

`MARKET_DATA_PROVIDER_PRIORITY` ga `ibkr` qo'shilsa, skan IBKR'dan candles+quote oladi.

## `IBKR_WEB_API_BASE_URL` ni qayerdan olish

Client Portal Web API'ni gateway'siz (noutboksiz) ishlatishning amaliy variantlari:

1. **Client Portal Gateway'ni bulutda ishga tushirish** (Render/VPS) — IBKR'ning kichik
   Java gateway'i headless ishlaydi; noutbuk shart emas. Eslatma: IBKR har ~24 soatda
   qayta login (2FA) talab qiladi.
2. **OAuth Web API** (1st-party) — to'liq hosted, qayta login shart emas, lekin IBKR'dan
   OAuth consumer (kalit/sertifikat) tasdiqlatish kerak. Asosan muassasa/biznes uchun.

> Eng tez yo'l — Client Portal Gateway'ni alohida Render servicesida ishga tushirib, uning
> ichki URL'ini `IBKR_WEB_API_BASE_URL` ga qo'yish.

## Endpointlar (modul ichida)

- `POST /iserver/secdef/search` — symbol → conid
- `GET /iserver/marketdata/snapshot` — jonli narx (maydonlar: 31/87/7296/83/70/71/7295)
- `GET /iserver/marketdata/history` — kunlik OHLCV (period=Nd, bar=1d)
- `GET /iserver/auth/status` yoki `/tickle` — sog'liq tekshiruvi (`/status` qatorida)

## Tekshirish

```
/status        → "IBKR Web API: ulangan (...)" ko'rinsa, ishlayapti
```

Keyin `/scan`, `/buy AAPL`, `/flow NVDA` IBKR ma'lumotidan ham foydalanadi
(`quote_source=ibkr_web`).

## Cheklov

- Realtime narx uchun IBKR market-data **obunasi** kerak bo'lishi mumkin; tarixiy kunlik
  (TRADES) odatda obunaqiz ham ishlaydi.
- Gateway varianti har ~24 soatda qayta autentifikatsiya talab qiladi (IBKR siyosati).
