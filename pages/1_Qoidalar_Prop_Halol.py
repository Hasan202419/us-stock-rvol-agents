"""Streamlit: Prop firma (namuna) va AAOIFI SS21 uslubidagi halal screening — ma'lumot sahifasi (fatvo emas)."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from agents.bootstrap_env import ensure_env_file, load_project_env

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
ensure_env_file(_PROJECT_ROOT)
load_project_env(_PROJECT_ROOT)


def _inject_prop_page_styles() -> None:
    """Dashboard bilan uyg‘un qorong‘i fon + kartochkalar."""
    st.markdown(
        """
<style>
    .block-container { max-width: 1200px; padding-top: 0.75rem; }
    .stApp {
        background: radial-gradient(circle at 10% -5%, rgba(56,189,248,0.10), transparent 42%),
            linear-gradient(180deg,#0b1220 0%,#030712 50%,#020617 100%);
        color: #e2e8f0;
    }
    header[data-testid="stHeader"] { background-color: transparent; }
    [data-testid="stSidebar"] {
        background: rgba(15,23,42,0.95) !important;
        border-right: 1px solid #334155 !important;
    }
    div[data-testid="stMetric"] {
        background: rgba(15,23,42,0.55);
        border: 1px solid rgba(148,163,184,0.2);
        border-radius: 10px;
        padding: 0.5rem 0.65rem;
    }
    div[data-testid="stMetric"] label { color: #94a3b8 !important; }
    .plan-section {
        border: 1px solid rgba(148,163,184,0.22);
        border-radius: 14px;
        padding: 1rem 1.15rem 1.15rem;
        margin-bottom: 1rem;
        background: rgba(15,23,42,0.45);
    }
    hr { border-color: rgba(148,163,184,0.28) !important; }
</style>
""",
        unsafe_allow_html=True,
    )


def _env(name: str, default: str = "—") -> str:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    return str(v).strip()


def _pct_env(name: str) -> str:
    raw = _env(name, "")
    if raw == "—":
        return "—"
    try:
        x = float(raw)
        return f"{x * 100:.0f}%"
    except ValueError:
        return raw


def _has_key(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _truthy_env(name: str, *, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


st.set_page_config(page_title="Qoidalar — Prop va halol", layout="wide", initial_sidebar_state="auto")
_inject_prop_page_styles()

st.title("Prop firma va halol skrin")
st.caption(
    "Bu sahifa **sinov / nazorat** uchun. Bu yerda yozilganlar **rasmiy fatvo emas**. "
    "AAOIFI va tanlangan prop firma qoidalarini **o‘zingizning mualliflari / schular** bilan tasdiqlang."
)

hero1, hero2, hero3, hero4 = st.columns(4)
hero1.metric("AI provayder", _env("AI_PROVIDER", "auto"))
hero2.metric("Zoya", "Yoqilgan" if _truthy_env("ZOYA_ENABLED", default=True) else "O‘chiq")
hero3.metric(
    "Telegram",
    "Tayyor" if _has_key("TELEGRAM_BOT_TOKEN") and _has_key("TELEGRAM_CHAT_ID") else "Sozlash kerak",
)
hero4.metric(
    "Render",
    "Tayyor" if _has_key("RENDER_API_KEY") and (_has_key("RENDER_SERVICE_ID") or _has_key("RENDER_SERVICE_NAME")) else "Sozlash kerak",
)

t_prop, t_plan, t_ss21, t_flow, t_dis = st.tabs(
    [
        "Prop rejasi (.env)",
        "SI va tarmoq rejasi",
        "AAOIFI SS21",
        "Bot ketma-ketligi",
        "Manbalar",
    ]
)

# --- Tab: Prop ---
with t_prop:
    st.subheader("Prop parametrlari — `.env` dagi `PROP_*`")
    st.caption(
        "Qiymatlar `PROP_FIRM_NAME`, `PROP_PLAN_ADVANCED_USD`, … qatorlaridan o‘qiladi. "
        "Bo‘sh bo‘lsa, qavs ichidagi **namuna** Toro250 Advanced bilan solishtirish uchun."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Firma", _env("PROP_FIRM_NAME", "— (namuna: Toro250)"))
        st.metric("Reja narxi (USD/oy)", _env("PROP_PLAN_ADVANCED_USD", "— (299)"))
        st.metric("Savdo kapitali (USD)", _env("PROP_BUYING_POWER_USD", "— (250,000)"))
    with c2:
        st.metric("Foyda nishoni (USD)", _env("PROP_PROFIT_TARGET_USD", "— (15,000)"))
        st.metric("Foyda nishoni (%)", _env("PROP_PROFIT_TARGET_PCT", "— (6)"))
        st.metric("Kunlik maks. zarar (USD)", _env("PROP_DAILY_MAX_LOSS_USD", "— (1,250)"))
    with c3:
        st.metric("Maks drawdown (USD)", _env("PROP_MAX_DRAWDOWN_USD", "— (7,500)"))
        st.metric("Maks drawdown (%)", _env("PROP_MAX_DRAWDOWN_PCT", "— (3)"))
        st.metric("Izchillik minimumi (%)", _env("PROP_CONSISTENCY_MIN_PCT", "— (50)"))

    st.metric("Minimal aylanma bitimlar", _env("PROP_MIN_ROUND_TRADES", "— (200)"))

    st.divider()

    with st.expander("Namuna qiymatlar va tez eslatma", expanded=False):
        note1, note2 = st.columns(2)
        with note1:
            st.markdown(
                """
- Reja narxi: **$299 / oy**
- Savdo kapitali: **$250,000**
- Foyda nishoni: **$15,000** (~6%)
- Kunlik maks. zarar: **$1,250**
"""
            )
        with note2:
            st.markdown(
                """
- Maks drawdown: **$7,500** (~3%)
- Izchillik: **50%**
- Minimal bitimlar: **200**
- Tekshiruv: `python scripts/check_apis.py`
"""
            )
        st.caption(
            "Prop limitlari hali to‘liq avtopolitsiya qilinmaydi; asosiy `PROP_*` qiymatlar `.env.example` oxirida izoh bilan bor."
        )

# --- Tab: SI va tarmoq rejasi ---
with t_plan:
    st.subheader("Sun’iy intellekt provayderlari va ixtiyoriy xizmatlar")
    st.caption("Kalit matnlari ko‘rsatilmaydi — faqat **sozlangan / yo‘q** va rejim.")

    ap = _env("AI_PROVIDER", "auto")
    st.markdown(f"**AI_PROVIDER:** `{ap}`")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Til modeli (LLM)**")
        st.write("- OpenAI: " + ("kalit sozlangan" if _has_key("OPENAI_API_KEY") else "yo‘q / bo‘sh"))
        st.write("- DeepSeek: " + ("kalit sozlangan" if _has_key("DEEPSEEK_API_KEY") else "yo‘q / bo‘sh"))
        st.caption(f"model: `{_env('DEEPSEEK_MODEL', 'deepseek-chat')}` · manzil: `{_env('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')}`")
    with col_b:
        st.markdown("**Ma’lumot & broker**")
        st.write("- Polygon: " + ("✓" if _has_key("POLYGON_API_KEY") else "—"))
        st.write("- Alpaca: " + ("✓" if _has_key("ALPACA_API_KEY") and _has_key("ALPACA_SECRET_KEY") else "—"))
        st.write("- Finnhub: " + ("✓" if _has_key("FINNHUB_API_KEY") else "—"))

    st.markdown("**Halol / Zoya**")
    ze = _truthy_env("ZOYA_ENABLED", default=True)
    st.write(f"- Zoya yoqilgan: **{'ha' if ze else 'yo‘q'}**")
    st.write("- Zoya kaliti: " + ("sozlangan" if _has_key("ZOYA_API_KEY") else "yo‘q"))
    st.caption("401 bo‘lsa yoki Zoya kerak bo‘lmasa: `ZOYA_ENABLED=false` va kalitni bo‘sh qoldiring — `check_apis` yashil.")

    st.markdown("**Boshqa**")
    st.write("- FMP / NewsAPI / GitHub / Supabase: faqat `.env` da yo‘q bo‘lsa ishlatilmaydi.")
    st.divider()
    st.markdown("**Mahalliy → Render chiqarish**")
    st.code(
        """1. streamlit run dashboard.py
2. python scripts/check_apis.py
3. .\\scripts\\verify_local.ps1
4. Render: dashboard yoki deploy hook orqali nashr""",
        language="text",
    )

# --- Tab: SS21 ---
with t_ss21:
    st.subheader("Halol cheklovlar — `.env` (0–1 sonlar)")
    h1, h2, h3 = st.columns(3)
    with h1:
        st.metric("HALAL_MAX_DEBT_RATIO", _pct_env("HALAL_MAX_DEBT_RATIO"))
    with h2:
        st.metric("HALAL_MAX_CASH_RATIO", _pct_env("HALAL_MAX_CASH_RATIO"))
    with h3:
        st.metric("HALAL_MAX_IMPURE_REV", _pct_env("HALAL_MAX_IMPURE_REV"))

    st.subheader("Halollik darvozasi (AAOIFI Shariah Standards — Financial Papers, uslubiy checklist)")
    st.markdown(
        """
**Asosiy g‘oya:** avval **biznes va moliyaviy nisbatlar**, keyin texnik savdo.

**Botdagi `apply_halal_gate`:** `.env` da yuqoridagi `HALAL_*` (masalan `0.30` = 30%). Zoya hisoboti + ixtiyoriy `ratios` dict:
`debt_ratio`, `cash_ratio`, `impure_revenue_pct`.
"""
    )

    with st.expander("(A) Biznes faoliyati — odatda rad", expanded=False):
        st.markdown(
            """
- Riba/oddiy bank, oddiy sug‘urta (conventional), alkogol, qimor, cho‘chqa/asosan nojoiz oziq-ona, tamas, kattalik kontent,
  asosiy biznes bo‘yicha tamaki, qurol (metodologiyaga qarab) va hokazo.

Zoya yoki qo‘lda soha filtri — **`NON_COMPLIANT`** boʻlsa darvoza rad qiladi.
"""
        )

    with st.expander("(B) Moliyaviy nisbatlar (SS21 uslubida ko‘p qo‘llanadi)", expanded=True):
        st.markdown("Foizlar **0.30 = 30%** ko‘rinishida `ratios` ga uzating (masalan `0.18` = 18%).")
        st.code(
            """Qarz nisbati = Foiz toʻlovli qarzlar / Bozor qiymati  →  ≤ HALAL_MAX_DEBT_RATIO
Naqd nisbati  = (Naqd + foiz taʼsirli qimmatli qog‘ozlar) / Bozor qiymati  →  ≤ HALAL_MAX_CASH_RATIO
Nojoʻy daromad ulushi = Halol boʻlmas daromad / Jami daromad  →  ≤ HALAL_MAX_IMPURE_REV""",
            language="text",
        )

    with st.expander("(C) Poklantirish (dividendlardan)", expanded=False):
        st.markdown(
            """
Agar **aralash (mixed)** boʻlgan boʻlsa, odatda nojoʻy ulush foiziga proporsional **sadaqa** hisoblanadi (portfel va dividend maʼlumotlari kerak).
Bot hozircha bu pulni avtomatik **ajratmaydi** — faqat darvoza holati chiqariladi.
"""
        )

    with st.expander("(D) Holat nomlari", expanded=False):
        st.markdown(
            """
- **SOF HALOL** — nojoʻiz daromad amaliyotda 0 va chegaralar toʻgʻri.
- **HALOL MOS / ARALASH** — koʻrsatkichlar ichida, ammo poklantirish talab qilinishi mumkin.
- **SHUBHALI** — qoʻlda qaror.
- **HALOL EMAS** — savdoni taʼqiqlash (`HALAL_PASS = False`).

**Savdoga ruxsat:** `HALAL_PASS` true boʻlsa — keyingi bosqich: RVOL / VWAP / risk menejer.
"""
        )

with t_flow:
    flow1, flow2 = st.columns(2)
    with flow1:
        st.info(
            "Bu ketma‑ketlik: halol tekshirish → texnik koʻrsatkichlar → SI tahlili → risk → qog‘oz savdo (`paper`)."
        )
    with flow2:
        st.info(
            "Agar **qog‘oz savdoga tayyor = yoʻq** boʻlsa, `Paper` boʻlakida blok sababi chiqadi (`Paper ready = No`)."
        )
    st.markdown(
        """
```
1. Halol skrinning (Zoya + nisbatlar)
2. Fundamental / yangiliklar (ixtiyoriy)
3. Texnik signal (RSI, EMA, VWAP, hajm)
4. Risk: % hisob-kitob, SL majburiy, kunlik/bitim limiti
5. Qog‘oz savdo yoki keyin „jonli“ rejim — prop chegaralari bilan nazorat
```

**Qoida:** halol boʻlmagan boʻlsa (**halol darvozi** oʻtkazmaydi) ko‘pchilik BUY strategiyalari ishlamaydi.
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
