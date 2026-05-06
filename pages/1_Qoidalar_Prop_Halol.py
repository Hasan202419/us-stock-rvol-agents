"""Streamlit: Prop firma (namuna) va AAOIFI SS21 uslubidagi halal screening — ma'lumot sahifasi (fatvo emas)."""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Qoidalar — Prop & Halol", layout="wide", initial_sidebar_state="auto")

st.title("Prop firma va halol skrin (eslatma)")
st.caption(
    "Bu sahifa **sinov / nazorat** uchun. Bu yerda yozilganlar **rasmiy fatvo emas**. "
    "AAOIFI va tanlangan prop firma qoidalarini **o‘zingizning mualliflari / schular** bilan tasdiqlang."
)

t_prop, t_ss21, t_flow, t_dis = st.tabs(
    ["Prop firma (namuna)", "AAOIFI SS21 checklist", "Bot ketma-ketligi", "Izohlar va manbalar"]
)

with t_prop:
    st.subheader("Toro250 — Advanced (siz keltirgan namuna)")
    st.markdown(
        """
| Ko‘rsatkich | Qiymat (namuna) |
|-------------|------------------|
| Reja narxi | **$299** / oy |
| Buying power | **$250,000** |
| Profit target | **$15,000** (~**6%**) |
| Daily max loss | **$1,250** |
| Max drawdown | **$7,500** (~**3%**) |
| Consistency (minimum) | **50%** |
| Minimum round trades | **200** |

**Sinovda nima bo‘lishi mumkin:** `python scripts/check_apis.py` — API lar; **paper** — buyurtma simulyatsiyasi.
Prop limitlari (kunlik yo‘qotish, drawdown, 200 round trip) **alohida hisob kitob** — hozirgi kodda avtomatik “Prop politsiyasi” yo‘q;
`.env.example` oxirida `PROP_*` izohli qatorlar bor (kelajakda botga ulash mumkin).

**Eslatma:** Firma nomi va raqamlar o‘zgartirilishi mumkin — har doim **o‘z shartnomasi** ustuvor.
"""
    )

with t_ss21:
    st.subheader("Halollik darvozasi (AAOIFI Shariah Standards — Financial Papers, uslubiy checklist)")
    st.markdown(
        """
**Asosiy g‘oya:** avval **biznes va moliyaviy nisbatlar**, keyin texnik savdo.

**Botdagi `apply_halal_gate`:** `.env` da `HALAL_MAX_DEBT_RATIO`, `HALAL_MAX_CASH_RATIO`, `HALAL_MAX_IMPURE_REV`
(barchasi **0–1** oraliqda, masalan `0.30` = 30%). Zoya hisoboti + ixtiyoriy `ratios` dict:
`debt_ratio`, `cash_ratio` (cash + foizli qimmatliklar / market cap uslubida siz hisoblaysiz), `impure_revenue_pct`.
"""
    )

    with st.expander("A) Biznes faoliyati — odatda rad", expanded=False):
        st.markdown(
            """
- Riba/oddiy bank, oddiy sug‘urta (conventional), alkogol, qimor, cho‘chqa/asosan nojoiz oziq-ona, tamas, kattalik kontent,
  asosiy biznes bo‘yicha tamaki, qurol (metodologiyaga qarab) va hokazo.

Zoya yoki qo‘lda industry filtr — **NON_COMPLIANT** bo‘lsa gate rad qiladi.
"""
        )

    with st.expander("B) Moliyaviy nisbatlar (SS21 uslubida ko‘p ishlatiladi)", expanded=True):
        st.markdown("Foizlar **0.30 = 30%** ko‘rinishida `ratios` ga uzating (masalan `0.18` = 18%).")
        st.code(
            """Debt ratio = Interest-bearing debt / Market cap  →  ≤ HALAL_MAX_DEBT_RATIO
Cash ratio  = (Cash + interest-bearing securities) / Market cap  →  ≤ HALAL_MAX_CASH_RATIO
Impure rev. = Non-halal revenue / Total revenue  →  ≤ HALAL_MAX_IMPURE_REV""",
            language="text",
        )

    with st.expander("C) Purification (dividenddan)", expanded=False):
        st.markdown(
            """
Agar **mixed** bo‘lsa, odatda nojoiz ulush foiziga proporsional **sadaqa** hisoblanadi (portfolio va divident ma’lumotlari kerak).
Bot hozircha bu pulni avtomatik **ajratmaydi** — faqat gate holati.
"""
        )

    with st.expander("D) Holatlar (nomlash)", expanded=False):
        st.markdown(
            """
- **PURE HALAL** — nojoiz daromad praktik 0 va cheklovlar ok.
- **HALAL-COMPLIANT / MIXED** — cheklovlar ichida, lekin purification kerak bo‘lishi mumkin.
- **SHUBHALI** — qo‘lda qaror.
- **NOT HALAL** — savdoga yo‘l qo‘ymang (`HALAL_PASS = False`).

**Savda ruxsati:** `HALAL_PASS` True bo‘lsa, keyin RVOL / VWAP / risk manager.
"""
        )

with t_flow:
    st.markdown(
        """
```
1. Halal screening (Zoya + ratios)
2. Fundamental / yangiliklar (ixtiyoriy)
3. Texnik signal (RSI, EMA, VWAP, hajm)
4. Risk: % hisob, SL majburiy, kunlik/trade limit
5. Paper yoki (keyinroq) live — prop limitlariga mos nazorat
```

**Qoida:** Agar **halal gate** rad qilsa — **BUY ishga tushmaydi** (agar strategiya halol bilan integratsiya qilingan bo‘lsa).
"""
    )

with t_dis:
    st.warning(
        "Dastur va bu sahifa **moliyaviy maslahat yoki shariat fatvosi emas**. "
        "Prop shartlari o‘zgarishi mumkin; AAOIFI hujjatlari rasmiy manbadan o‘qing."
    )
    st.markdown(
        """
- [AAOIFI — Shariah standards](https://aaoifi.com/shariah-standards-3/?lang=en)
- [OIC Exchanges — AAOIFI screening taqdimoti (PDF)](https://www.oicexchanges.org/files/1---shari-ah-screening-in-the-islamic-capital-markets-dr-hamed-merah-secretary-general-aaoifi.pdf)
"""
    )
