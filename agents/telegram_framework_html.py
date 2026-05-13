"""Telegram HTML: skan xabarining oxirida yig‘iladigan (expandable) qoida bloklari + LLM uchun qisqa appendix."""

from __future__ import annotations

import html

# ChatGPT/DeepSeek system xabariga qo‘shiladi (token tejash — qisqa, lekin tuzilma saqlangan).
ANALYST_LLM_SYSTEM_APPENDIX = (
    "Framework (advisory, JSON schema o‘zgarmaydi): "
    "(1) REASON/EDGE — catalyst, earnings, unusual volume, breakout/momentum. "
    "(2) ANALYSIS — fundamentals + sector; TA: trend, S/R, volume, price action. "
    "(3) PREDICTION — bullish bias, move size, ehtiyotkor ehtimol. "
    "(4) RISK — support, downside, vol, R:R. "
    "(5) SETUP — entry zone, SL, TP, faqat misoliy hajm. "
    "(6) EXECUTION — tasdiq, intizom, SL darhol, boshqarish. "
    "Volume ignition skaneri: RVOL, hajm zanjiri, 3 kunlik o‘sish cheklovi, qarshilik yaqinligi, "
    "parabolikdan qochish, suyuqlik (avg vol). "
    "HASAN-style: long-only, paper, NYSE/NASDAQ/AMEX likvid; BUY faqat gate+skor kuchli; WATCH marginal; AVOID zaif; "
    "majburiy savdo yo‘q. Fakt: faqat signal JSON + yangiliklar."
)


def _expandable(title: str, body: str) -> str:
    """Telegram Bot API 7.0+ HTML: `<blockquote expandable>`. Eski mijozlarda oddiy blockquote ko‘rinadi."""
    t = html.escape(title.strip(), quote=True)
    b = html.escape(body.rstrip(), quote=True)
    return f'<blockquote expandable><b>{t}</b>\n{b}</blockquote>\n\n'


def build_telegram_framework_appendices_html() -> str:
    """Skan /signals xabarining oxiriga qo‘shiladi — uchta yig‘iladigan blok."""

    analyst = (
        "OUTPUT (matn rejasi): Ticker · Company · Reason (Catalyst) · Technical Setup · "
        "Entry · Stop · Target · R/R · Position size (misol) · Execution · Summary.\n"
        "1) REASON — yangilik/katalizator, EPS/tovar o‘sishi, g‘ayritabiiy hajm, breakout.\n"
        "2) ANALYSIS — kompaniya/sektor; trend, S/R, hajm, tasdiqlovchi price action.\n"
        "3) PREDICTION — bullish yo‘nalish, harakat taxmini, ehtimollik tilida ehtiyotkor.\n"
        "4) RISK — support, pastga xavf, volatillik, R:R.\n"
        "5) TRADING SETUP — kirish, SL, TP, misoliy hajm.\n"
        "6) EXECUTION — tasdiqdan keyin kirish, SL darhol, foyda boshqaruvi."
    )

    ignition = (
        "US volume ignition: oxirgi 3 shamda hajm o‘sishi; hajm ≥ 2× 20 kunlik o‘rtacha; RVOL ≥ 2; "
        "3 kun ichida +10% dan past; qarshilik yaqin (~5%); higher low; EMA9 ustida, EMA20 dan juda uzoq emas; "
        "ATR o‘sishi. AVOID: +20% dan yuqori, parabolik spike, <1M o‘rtacha hajm.\n"
        "OUTPUT: Ticker, Price, Volume pattern, RVOL, R masofa %, Trend stage (Accumulation/Ignition/Breakout), "
        "Entry zone, Continuation probability, Risk."
    )

    hasan = (
        "HASAN AI (adaptive long-only, 5m asos): rejim (BULL/NEUTRAL/BEAR/NEWS_LOCK); "
        "skrener: likvidlik (avg vol, dollar vol), RVOL, kataliz; signal: VWAP/EMA9/EMA20 (5m mantiq; "
        "1m/10m/1H katta TF filtrlari — mavjud bo‘lsa kunlik/intraday snapshot bilan); RSI/ADX, struktura; "
        "skor: hajm/trend/structure/momentum/market/catalyst; BUY ≥70 + gate OK, WATCH 60–69, REJECT gate yomon; "
        "risk: kirish/SL/TP, R:R, hajm; chiqish: TP/SL, VWAP/EMA9 yo‘qotish, sessiya oxiri; "
        "faqat Alpaca paper, bracket. Har signal: Ticker, Company, Regime, Setup, Score, Reason, Entry, SL, T1/T2, R:R, Size, Risk, BUY/WATCH/REJECT."
    )

    return (
        "<b>Qo‘llanma (yig‘iladi)</b>\n"
        + _expandable("1) Professional analyst framework", analyst)
        + _expandable("2) Volume ignition scanner", ignition)
        + _expandable("3) HASAN AI long-only system", hasan)
        + "<i>Skan natijalari yuqorida; bu bloklar faqat tuzilma. Savdo qarori dashboard/RiskManager.</i>\n"
    )
