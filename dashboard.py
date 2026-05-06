import json
import os

# Render platform: PORT va RENDER=true avtomatik (https://render.com/docs/environment-variables)
# STREAMLIT importidan oldin — telemetry va headless uchun.
if os.environ.get("RENDER", "").strip().lower() == "true":
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from agents.bootstrap_env import ensure_env_file, load_project_env
from agents.scan_pipeline import SidebarControls, build_scan_agents, run_scan_market
from agents.scan_presets import SCAN_PRESETS
from agents.strategy_factory import resolve_strategy_mode
from agents.universe_agent import UniverseAgent


PROJECT_DIR = Path(__file__).parent
ensure_env_file(PROJECT_DIR)
load_project_env(PROJECT_DIR)
os.environ.setdefault("PROJECT_ROOT", str(PROJECT_DIR))

# Looser defaults make empty screens less likely; traders can pick “Conservative” for old behavior.
def _intraday_strategy_mode(mode: str) -> bool:
    return mode.strip().lower() in {"vwap_breakout", "mtrade_high_volatility"}


def _volume_ignition_mode(mode: str) -> bool:
    return mode.strip().lower() == "volume_ignition"


def _strategy_fallback_name(mode: str) -> str:
    m = mode.strip().lower()
    if m == "mtrade_high_volatility":
        return "mtrade_high_volatility"
    if _intraday_strategy_mode(m):
        return "vwap_breakout"
    if m == "volume_ignition":
        return "volume_ignition_scan"
    return "rvol_momentum"


def _strategy_mode_title(mode: str) -> str:
    m = mode.strip().lower()
    if m == "volume_ignition":
        return "Volume ignition skaneri"
    if _intraday_strategy_mode(m):
        return "Intraday VWAP / MTrade"
    return "RVOL momentum"


def init_platform_ui_defaults() -> None:
    """Sidebar personalizatsiya uchun sukutlar (birinchi run)."""

    if "platform_theme" not in st.session_state:
        st.session_state.platform_theme = "dark_lab"
    if "platform_show_chain" not in st.session_state:
        st.session_state.platform_show_chain = True
    if "platform_show_metrics" not in st.session_state:
        st.session_state.platform_show_metrics = True
    if "platform_show_3d" not in st.session_state:
        st.session_state.platform_show_3d = False


def inject_dashboard_styles(theme: str = "dark_lab") -> None:
    """Interfeys: Dark Lab yoki Light Ops — tashqi CDN yo‘q, faqat ichki CSS."""

    if theme == "light_focus":
        css = """
        <style>
            .block-container { max-width: 1450px; padding-top: 1rem; }
            div[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
            .stApp { background: linear-gradient(170deg,#f8fafc 0%,#e2e8f0 55%,#f1f5f9 100%); }
            header[data-testid="stHeader"] { background-color: transparent; }
            [data-testid="stSidebar"] { background: rgba(255,255,255,0.92) !important; border-right: 1px solid #cbd5e1; }
            div[data-testid="stMarkdownContainer"] a { color: #0ea5e9; }
        </style>
        """
    else:
        css = """
        <style>
            .block-container { max-width: 1450px; padding-top: 1rem; }
            div[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
            .stApp {
                background: radial-gradient(circle at 12% -10%, rgba(56,189,248,0.12), transparent 40%),
                    linear-gradient(180deg,#0b1220 0%,#030712 45%,#020617 100%);
                color: #f1f5f9;
            }
            header[data-testid="stHeader"] { background-color: transparent; }
            [data-testid="stSidebar"] {
                background: rgba(15,23,42,0.97) !important;
                border-right: 1px solid #334155 !important;
            }
            hr { border-color: rgba(148,163,184,0.35) !important; }
        </style>
        """

    st.markdown(css, unsafe_allow_html=True)


def render_persona_platform_sidebar() -> None:
    """3D blok va bloklarni boshqarish — siz ulanib qo‘ygan Plotly qatlam ustida ishlaydi."""

    themes = {"dark_lab": "Dark · Lab studio", "light_focus": "Light · Ops desk"}
    keys = list(themes.keys())
    labels = list(themes.values())

    try:
        cur_i = keys.index(st.session_state.platform_theme)
    except ValueError:
        cur_i = 0
        st.session_state.platform_theme = keys[0]

    with st.sidebar.expander("Platform dizayni (personal)", expanded=False):
        st.caption(
            "Tema va panellar shu qurilmaga saqlanadi. "
            "3D manzara — mavjud signal **narx / RVOL / skor** nuqtalari (Scatter3d), alohida 3D-model fayl emas."
        )
        picked_label = st.selectbox(
            "Interfeys muhiti",
            labels,
            index=cur_i,
            help="Streamlit tuzilishi o‘zgarmaydi — fon va panel fonlari bilan ‘platforma’ hissini birlashtiramiz.",
        )
        st.session_state.platform_theme = keys[labels.index(picked_label)]

        st.checkbox(
            "Zanjir (hero) blokini ko‘rsatish",
            key="platform_show_chain",
        )
        st.checkbox(
            "Skan **metrika** kartochkalari",
            key="platform_show_metrics",
        )
        st.checkbox(
            "3D signal manzarasi (Plotly, ixtiyoriy)",
            key="platform_show_3d",
        )


def render_brand_row(desk_label: str) -> None:
    """Tashqi `<div>`siz brend satri."""

    short = "".join(part[0].upper() for part in desk_label.strip().split()[:2] if part)[:3] or "HT"
    col_l, col_r = st.columns([1, 10])
    with col_l:
        st.markdown(f"### `{short}`")
    with col_r:
        st.caption("US skan • RVOL / VWAP / Volume ignition • Paper-ready")
    st.divider()


def render_pipeline_hero(strategy_mode: str, preset: str | None) -> None:
    """Berilgan reja/modullarni bir qarashda ko‘rsatadi."""

    mode_key = strategy_mode.strip().lower()
    title = _strategy_mode_title(strategy_mode)
    preset_txt = preset or "—"

    layers_rvol = [
        "**Universe** → tickerlar ro‘yxati",
        "**MarketData** → kunlik/intraday narxlar",
        "**RVOL Agent** → nisbiy hajm hisobi",
        "**Strategiya** → RVOL momentum qoidalari",
        "**ChatGPT** → WATCH / STRONG_WATCH (maslahat)",
        "**RiskManager + Alpaca** → paper bracket",
    ]
    layers_vwap = [
        "**Universe** → tickerlar",
        "**Intraday bars** → timeframe `.env` dan",
        "**VWAP breakout** → Pine-ga yaqin crossover + SL/TP/TIME",
        "**Plotly chart** → sham + VWAP + BUY/SELL/STOP/TIME",
        "**ChatGPT + Risk + Paper** → xuddi shu zanjir",
    ]
    layers_vi = [
        "**Universe + kunlik OHLCV** → resistance / EMA / ATR",
        "**Volume ignition** → hajm zanjiri + RVOL + liquidity",
        "**Profil matn** → REASON→EXECUTION shabloni",
        "**ChatGPT + Risk + Paper** → tasdiq va buyurtma",
    ]

    if mode_key == "volume_ignition":
        layers_md = "\n".join(f"- {x}" for x in layers_vi)
        focus = "Kunlik asos; intraday grafik shart emas."
    elif _intraday_strategy_mode(strategy_mode):
        layers_md = "\n".join(f"- {x}" for x in layers_vwap)
        focus = "Intraday sessiya bardalari va VWAP chizig‘i muhim."
    else:
        layers_md = "\n".join(f"- {x}" for x in layers_rvol)
        focus = "Filtrlar preset va `.env` bilan silliq sozlanadi."

    with st.container():
        st.caption(f"Rejim · `{strategy_mode}`")
        st.markdown(f"**{title}**")
        st.caption(f"Preset: **{preset_txt}** — {focus}")
    with st.expander(
        "Bo‘lim · zanjir (rejim bo‘yicha modullar) — sarlavhaga bosing",
        expanded=True,
    ):
        st.markdown(layers_md)


def _signal_table_row(signal: Dict[str, Any], strategy_mode: str) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "Ticker": signal.get("ticker"),
        "Strategy": signal.get("strategy_name"),
        "Price": signal.get("price"),
        "Change %": signal.get("change_percent"),
        "Volume": signal.get("volume"),
        "Avg Volume": signal.get("avg_volume"),
        "RVOL": signal.get("rvol"),
        "Score": signal.get("score"),
        "TP": signal.get("take_profit_suggestion"),
        "SL": signal.get("stop_suggestion"),
        "VWAP": signal.get("session_vwap"),
        "RSI (sessiya)": signal.get("rsi_14"),
        "ATR (sessiya)": signal.get("atr_14"),
        "VWAP cross": signal.get("vwap_cross"),
        "ChatGPT": signal.get("chatgpt_decision"),
        "Risk": signal.get("risk_level"),
        "Data delay": signal.get("data_delay"),
        "Updated": signal.get("updated_time"),
    }
    if _volume_ignition_mode(strategy_mode):
        row.update(
            {
                "Ign. bosqich": signal.get("ignition_trend_stage"),
                "R masofa %": signal.get("ignition_distance_to_resistance_pct"),
                "Davom %": signal.get("ignition_continuation_probability"),
                "Ign. risk": signal.get("ignition_risk_level"),
            }
        )
    return row


def _chart_ms_to_et(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC).astimezone(ZoneInfo("America/New_York"))


def render_vwap_mtrade_chart(signal: Dict[str, Any]) -> None:
    """Plotly: sham + sessiya VWAP va Pine uslubidagi BUY / SELL / STOP / TIME markerlari."""

    try:
        import plotly.graph_objects as go
    except ImportError:
        st.warning("`plotly` topilmadi. `pip install -r requirements.txt`")
        return

    bars = signal.get("chart_session_bars") or []
    vwaps = signal.get("chart_vwap_series")
    markers = signal.get("mtrade_chart_markers")

    if not bars or vwaps is None or len(bars) < 2:
        st.caption("Chart uchun yerda mavjud kunlik bardalar kam.")
        return

    x_et = [_chart_ms_to_et(int(b["t"])) for b in bars]

    def _flt(bar: Dict[str, Any], key_primary: str, key_alt: str) -> float:
        val = bar.get(key_primary)
        if val is None:
            val = bar.get(key_alt)
        return float(val) if val not in (None, "") else 0.0

    opens = [
        (_flt(b, "o", "open") or _flt(b, "c", "close"))
        for b in bars
    ]
    highs_list = [_flt(b, "h", "high") or _flt(b, "c", "close") for b in bars]
    lows_list = [_flt(b, "l", "low") or _flt(b, "c", "close") for b in bars]
    closes_plot = [_flt(b, "c", "close") for b in bars]

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=x_et,
            open=opens,
            high=highs_list,
            low=lows_list,
            close=closes_plot,
            name="OHLC",
            increasing_line_color="#22c55e",
            decreasing_line_color="#ef4444",
        )
    )

    vw_x, vw_y = [], []
    for t_dt, vw in zip(x_et, vwaps):
        if vw is not None:
            vw_x.append(t_dt)
            vw_y.append(float(vw))
    if vw_x:
        fig.add_trace(
            go.Scatter(
                x=vw_x,
                y=vw_y,
                mode="lines",
                name="VWAP",
                line={"color": "#38bdf8", "width": 2},
            )
        )

    palette: Dict[str, tuple[str, str, int]] = {
        "BUY": ("#22c55e", "triangle-up", 14),
        "SELL": ("#f97316", "circle", 12),
        "STOP": ("#dc2626", "x", 13),
        "TIME": ("#a855f7", "diamond", 11),
    }
    if markers:
        for evt, spec in palette.items():
            pts = [m for m in markers if m.get("event") == evt]
            if not pts:
                continue
            color, sym, sz = spec
            mx = [_chart_ms_to_et(int(m["t"])) for m in pts]
            my = [float(m["price"]) for m in pts]
            fig.add_trace(
                go.Scatter(
                    x=mx,
                    y=my,
                    mode="markers+text",
                    text=[evt] * len(pts),
                    textposition="top center",
                    marker={"symbol": sym, "size": sz, "color": color, "line": {"width": 1, "color": "#0f172a"}},
                    textfont={"size": 10, "color": color},
                    name=evt,
                )
            )

    tf = signal.get("chart_timeframe_minutes", "?")
    tkr = signal.get("ticker", "")
    st_name = signal.get("strategy_name", "")
    fig.update_layout(
        title=f"{tkr} · {st_name} · {tf}m",
        xaxis_rangeslider_visible=False,
        height=520,
        template="plotly_dark",
        margin={"l": 48, "r": 28, "t": 48, "b": 44},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    fig.update_xaxes(showgrid=True, gridcolor="#334155")
    fig.update_yaxes(showgrid=True, gridcolor="#334155")
    _chart_key = f"mtrade_vwap_chart_{tkr}_{tf}_{len(bars)}".replace(" ", "_")[:120]
    try:
        st.plotly_chart(fig, use_container_width=True, key=_chart_key)
    except TypeError:
        st.plotly_chart(fig, use_container_width=True)


def render_signals_spatial_landscape(signals: List[Dict[str, Any]]) -> None:
    """Scatter3d: narx × RVOL × skor — mavjud Plotly/agent ma'lumoti."""

    try:
        import plotly.graph_objects as go
    except ImportError:
        st.warning("`plotly` topilmadi. `pip install -r requirements.txt`")
        return

    rows: List[Tuple[float, float, float, str]] = []
    for s in signals[:150]:
        px = float(s.get("price") or 0)
        rv = float(s.get("rvol") or 0)
        sc = float(s.get("score") or 0)
        tk = str(s.get("ticker") or "").strip().upper()
        if not tk:
            continue
        rows.append((px, rv, sc, tk))

    if len(rows) < 2:
        st.caption("Bu manzara uchun kamida ikkita ticker kerak.")
        return

    xs = [r[0] for r in rows]
    ys = [r[1] for r in rows]
    zs = [r[2] for r in rows]
    texts = [r[3] for r in rows]

    is_dark = st.session_state.get("platform_theme", "dark_lab") == "dark_lab"
    tmpl = "plotly_dark" if is_dark else "plotly_white"
    scene_bg = "#0f172a" if is_dark else "#ffffff"

    fig = go.Figure(
        data=[
            go.Scatter3d(
                x=xs,
                y=ys,
                z=zs,
                mode="markers+text",
                text=texts,
                textposition="top center",
                textfont={"size": 10},
                marker={
                    "size": 7,
                    "color": zs,
                    "colorscale": "Temps",
                    "opacity": 0.88,
                    "showscale": True,
                    "colorbar": {"title": "Skor", "tickfont": {"size": 10}, "titlefont": {"size": 11}},
                },
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Narx: %{x}<br>"
                    "RVOL: %{y}<br>"
                    "Skor: %{z}<extra></extra>"
                ),
            )
        ]
    )

    fig.update_layout(
        template=tmpl,
        title={"text": "3D nuqtalar — signal maydoni", "font": {"size": 15}},
        height=520,
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        scene={
            "xaxis_title": "Narx ($)",
            "yaxis_title": "RVOL",
            "zaxis_title": "Skor",
            "bgcolor": scene_bg,
            "aspectmode": "cube",
        },
    )

    _safe = "".join(texts[:3]) + "_" + str(len(rows))
    plot_key = "spatial_landscape_" + _safe.replace(" ", "_")[:104]
    try:
        st.plotly_chart(fig, use_container_width=True, key=plot_key)
    except TypeError:
        st.plotly_chart(fig, use_container_width=True)




def build_agents() -> Dict[str, Any]:
    """Create the agents after .env values have loaded (dashboard + paper panel)."""

    return build_scan_agents(PROJECT_DIR)


@st.cache_data(ttl=180, show_spinner=False)
def cached_universe_symbols(limit: int, use_finviz_elite: bool) -> Tuple[str, ...]:
    """Cache the latest universe pull so rapid rescans do not re-hit Alpaca/Polygon."""

    return tuple(UniverseAgent().fetch_symbols(limit=limit, use_finviz_elite=use_finviz_elite))


def scan_market(tickers: List[str], controls: SidebarControls) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Run the pipeline with Streamlit progress; logic lives in agents.scan_pipeline."""

    progress = st.progress(0.0, text="Stage 1 · fetching symbols…")
    return run_scan_market(tickers, controls, repo_root=PROJECT_DIR, progress=progress)



def signals_dataframe(signals: List[Dict[str, Any]], strategy_mode: str = "rvol") -> pd.DataFrame:
    rows = [_signal_table_row(signal, strategy_mode) for signal in signals]
    return pd.DataFrame(rows)


def full_scan_dataframe(full_scan_views: List[Dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(full_scan_views)


def render_sidebar() -> SidebarControls:
    render_persona_platform_sidebar()

    st.sidebar.header("Workspace")
    desk_label = st.sidebar.text_input("Shaxsiy nom", value="HaSan RVOL Lab", help="Sarlavhada ko‘rinadi — kalit emas.")

    st.sidebar.header("Scanner settings")
    st.sidebar.caption(
        "Barcha ko‘rinishlar DATA_DELAY bo‘yicha yorliq bilan. "
        f"Yahoo fallback: `YAHOO_FINANCE_ENABLED={os.getenv('YAHOO_FINANCE_ENABLED', 'true')}`."
    )

    max_symbols = st.sidebar.slider("Skan qilinadigan tickers", min_value=10, max_value=400, value=120, step=10)

    _fa = os.getenv("FINVIZ_ELITE_AUTH", "").strip()
    _fq = os.getenv("FINVIZ_ELITE_EXPORT_QUERY", "").strip()
    finviz_ready = bool(_fa and _fq)
    finviz_csv_universe = st.sidebar.checkbox(
        "Universe: Finviz Elite CSV",
        value=False,
        disabled=not finviz_ready,
        help="Finviz Elite eksport CSV dan ticker ro‘yxati (.env: FINVIZ_ELITE_AUTH + FINVIZ_ELITE_EXPORT_QUERY). "
        "Yo‘q bo‘lsa Alpaca → Polygon.",
    )
    if not finviz_ready:
        st.sidebar.caption("Finviz uchun `.env` ga FINVIZ_ELITE_AUTH va FINVIZ_ELITE_EXPORT_QUERY qoshing.")
    elif os.getenv("FETCH_UNIVERSE_FINVIZ_FIRST", "").strip().lower() in {"1", "true", "yes", "on"}:
        st.sidebar.caption("`FETCH_UNIVERSE_FINVIZ_FIRST=true` — Finviz avtomatik birinchi navbatda.")

    max_workers = st.sidebar.slider(
        "Parallel oqimlar (tezlik)",
        min_value=2,
        max_value=20,
        value=int(os.getenv("SCAN_MAX_WORKERS", "10")),
        help="Ko‘proq ishchi = tezroq, lekin provayder limitiga ehtiyot bo‘ling.",
    )

    st.sidebar.header("RVOL presetlari")
    preset_choice = st.sidebar.radio(
        "Filtr kayfiyati",
        options=["Explorer", "Balanced", "Conservative", "Custom"],
        index=1,
        help="Explorer eng yumshoq; Conservative productionga yaqin.",
    )

    if preset_choice == "Custom":
        with st.sidebar.expander("Custom numeric gates", expanded=True):
            min_rvol = st.slider("MIN_RVOL", 0.8, 4.0, 1.2, 0.05)
            min_price = st.slider("MIN_PRICE ($)", 0.5, 20.0, 1.0, 0.25)
            min_volume = st.number_input("MIN_VOLUME", min_value=10_000, value=150_000, step=10_000)
            min_change = st.slider("MIN_CHANGE_% (manfiy = qizil kunlar)", -5.0, 2.0, -1.5, 0.1)
        thresholds = {
            "min_rvol": float(min_rvol),
            "min_price": float(min_price),
            "min_volume": int(min_volume),
            "min_change_percent": float(min_change),
        }
    else:
        thresholds = dict(SCAN_PRESETS[preset_choice])
        st.sidebar.write(
            f"Aktiv: RVOL≥{thresholds['min_rvol']}, "
            f"price≥${thresholds['min_price']}, "
            f"vol≥{int(thresholds['min_volume']):,}, "
            f"change≥{thresholds['min_change_percent']} %"
        )

    st.sidebar.header("Strategiya (.env)")
    st.sidebar.write(f"STRATEGY_MODE: `{os.getenv('STRATEGY_MODE', 'rvol')}`")
    _sm = os.getenv("STRATEGY_MODE", "rvol")
    if _intraday_strategy_mode(_sm):
        st.sidebar.write(f"INTRADAY_TIMEFRAME_MINUTES: `{os.getenv('INTRADAY_TIMEFRAME_MINUTES', '5')}`")
    if _volume_ignition_mode(_sm):
        st.sidebar.caption(
            "Volume ignition: `IGNITION_MIN_RVOL`, `IGNITION_MIN_AVG_VOLUME` (sukut 1M), "
            "qarshilik `%` — `.env.example`."
        )

    st.sidebar.header("Broker / risk (.env)")
    st.sidebar.write(f"TRADING_MODE: `{os.getenv('TRADING_MODE', 'paper')}`")
    st.sidebar.write(f"MAX_POSITION_SIZE_USD: `{os.getenv('MAX_POSITION_SIZE_USD', '100')}`")

    st.sidebar.divider()
    with st.sidebar.expander("Bo‘limlarni qanday ochaman?", expanded=True):
        st.markdown(
            """
**Chap panel** — scanner sozlamalari, preset va `.env` haqidagi qatorlar.

**Asosidagi 3 ta yorliq (tab)**  
- **Mos kelganlar** — o‘tgan signallar jadvalidan keyin yashirin **bo‘limlar** bor: ularning **sarlavhasiga bir marta bosasiz**, ichki matn ochiladi.  
- **Barcha skan** — har bir ticker va *Failed Rules*.  
- **Paper savdo** — tanlangan signal bo‘yicha buyurtma.

**Qanday farq qiladi?**  
- **Tab**: tepada yozuv ustiga bosasiz (`Mos kelganlar` va hokazo).  
- **Expander**: jadvaldan keyingi yozuv ustiga bosasiz (`ChatGPT izohlari`, `Intraday grafik` va hokazo).

**Katak kartochka** tepada — rejim va preset; ostidagi **Bo‘lim · zanjir** ham expander (`expanded` sukutda ochiq).

**Streamlit ishga tushirish** (`cd` loyiha ildiziga):  
`streamlit run dashboard.py`
"""
        )

    return SidebarControls(
        desk_label=desk_label.strip() or "HaSan RVOL Lab",
        max_symbols=int(max_symbols),
        preset_name=preset_choice,
        rvol_thresholds=thresholds,
        max_workers=int(max_workers),
        finviz_csv_universe=finviz_csv_universe,
    )


def render_paper_trading_panel(signals: List[Dict[str, Any]]) -> None:
    st.subheader("Paper savdo")
    st.info(
        "ChatGPT faqat maslahatchi. **RiskManager** hajm, R:R va kill-switch bo‘yicha tekshiradi; buyurtma "
        "**Alpaca paper** akkauntiga ketadi."
    )

    if not signals:
        st.write("Hozircha strategiya filtridan o‘tgan signal yo‘q — avval skan qiling.")
        return

    agents = build_agents()
    mode = resolve_strategy_mode()

    tickers = [signal["ticker"] for signal in signals]
    selected_ticker = st.selectbox("Ticker", tickers, key="paper_pick_ticker")
    selected_signal = next(signal for signal in signals if signal["ticker"] == selected_ticker)

    if _volume_ignition_mode(mode) and selected_signal.get("volume_pattern_summary"):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Ign. bosqich", selected_signal.get("ignition_trend_stage") or "—")
        with c2:
            st.metric("R masofa %", selected_signal.get("ignition_distance_to_resistance_pct") or "—")
        with c3:
            st.metric("Davom % (model)", selected_signal.get("ignition_continuation_probability") or "—")
        with st.expander("Hajm patterni (qisqa)"):
            st.caption(selected_signal.get("volume_pattern_summary") or "—")

    if selected_signal.get("chart_session_bars"):
        st.markdown("##### Intraday — sham, VWAP, markerlar")
        render_vwap_mtrade_chart(selected_signal)

    st.markdown("##### Buyurtma parametrlari")

    price = float(selected_signal.get("price") or 0)
    qty_suggest, sizing_note = agents["risk"].suggest_quantity(selected_signal)
    st.caption(sizing_note)

    quantity = st.number_input("Quantity", min_value=1, value=max(1, qty_suggest) if qty_suggest else 1, step=1)
    if selected_signal.get("stop_suggestion"):
        default_stop = round(float(selected_signal["stop_suggestion"]), 4)
    elif price > 0:
        default_stop = round(price * 0.95, 2)
    else:
        default_stop = 0.01
    stop_loss = st.number_input("Required stop loss", min_value=0.01, value=float(default_stop), step=0.01)

    if selected_signal.get("take_profit_suggestion"):
        default_tp = round(float(selected_signal["take_profit_suggestion"]), 4)
    elif price > 0:
        default_tp = round(price * 1.04, 2)
    else:
        default_tp = 0.01
    take_profit = st.number_input("Take profit (bracket)", min_value=0.01, value=float(default_tp), step=0.01)

    def _parse_json_list(blob: Any) -> list[str]:
        if blob is None:
            return []
        if isinstance(blob, list):
            return [str(x) for x in blob]
        try:
            out = json.loads(str(blob))
            return [str(x) for x in out] if isinstance(out, list) else []
        except json.JSONDecodeError:
            return []

    analyst_view = {
        "decision": selected_signal.get("chatgpt_decision"),
        "risk_level": selected_signal.get("risk_level"),
        "allow_order": selected_signal.get("chatgpt_allow_order", False),
        "risk_flags_hard": _parse_json_list(selected_signal.get("chatgpt_risk_flags_hard_json")),
        "paper_ready_blocked": selected_signal.get("paper_ready_blocked_field"),
    }
    order = {"quantity": int(quantity), "stop_loss": float(stop_loss), "take_profit": float(take_profit)}
    approved, reason = agents["risk"].approve_order(selected_signal, analyst_view, order)
    st.write(f"RiskManager status: {'Approved' if approved else 'Blocked'} - {reason}")

    if st.button("Submit Alpaca Paper Order", disabled=not approved):
        result = agents["trader"].submit_order(
            selected_ticker,
            int(quantity),
            float(stop_loss),
            approved,
            take_profit=float(take_profit),
        )
        poll = agents["trader"].fetch_order(str(result.get("order_id", "")))
        trade_log = {
            "ticker": selected_ticker,
            "quantity": int(quantity),
            "price": price,
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "risk_approved": approved,
            "risk_reason": reason,
            "alpaca_status": result.get("status"),
            "alpaca_order_id": result.get("order_id", ""),
            "alpaca_parent_status": poll.get("status") if poll else "",
            "message": result.get("message"),
            "submitted_at": result.get("submitted_at"),
            "realized_pnl": 0,
        }
        agents["logger"].save_trade(trade_log)
        st.write(result)
        if poll:
            st.write("Order poll:", poll.get("status"), poll.get("filled_qty"), poll.get("filled_avg_price"))


def main() -> None:
    st.set_page_config(page_title="HaSan Trading Desk", layout="wide", initial_sidebar_state="expanded")

    init_platform_ui_defaults()
    inject_dashboard_styles(st.session_state.platform_theme)

    controls = render_sidebar()
    render_brand_row(controls.desk_label)
    st.title(f"{controls.desk_label}")
    st.caption(
        "Deterministik skaner + AI maslahati. Savdo faqat **RiskManager** tekshiruvidan keyin, **paper Alpaca** orqali."
    )

    st.session_state.setdefault("signals", [])
    st.session_state.setdefault("full_scan", [])
    st.session_state.setdefault("scan_summary", None)

    c_run, c_hint = st.columns([1, 2])
    with c_run:
        run_clicked = st.button("Run market scan", type="primary", use_container_width=True)
    with c_hint:
        st.caption(
            "Skandan keyin **Mos kelganlar** (o‘tganlar) va **Barcha skan** (sabablar jadvali) yangilanadi."
        )

    if run_clicked:
        use_finviz = controls.finviz_csv_universe or os.getenv("FETCH_UNIVERSE_FINVIZ_FIRST", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        tickers = list(cached_universe_symbols(controls.max_symbols, use_finviz))
        signals_new, full_scan_new, summary_new = scan_market(tickers, controls)
        st.session_state.signals = signals_new
        st.session_state.full_scan = full_scan_new
        st.session_state.scan_summary = summary_new

    signals = st.session_state.signals
    full_scan_views = st.session_state.full_scan
    summary = st.session_state.scan_summary

    env_mode = os.getenv("STRATEGY_MODE", "rvol")
    current_mode = str(summary.get("strategy_mode", env_mode)) if summary else env_mode
    scan_preset = str(summary.get("scan_preset")) if summary else None

    if st.session_state.get("platform_show_chain", True):
        render_pipeline_hero(current_mode, scan_preset)
        st.divider()
    elif summary:
        st.caption(f"Rejim · `{current_mode}` — chap panel › **Platform dizayni**: hero blok yashirish yoqilgan.")

    if summary and st.session_state.get("platform_show_metrics", True):
        scanned = int(summary["tickers_scanned"])
        eligible = int(summary["eligible_signals"])
        cols = st.columns(4)
        cols[0].metric("Skanlangan", scanned, help="Universe dan olingan symbolar soni")
        cols[1].metric("Signal (pass)", eligible, help="Strategiya + ChatGPT oqimi")
        cols[2].metric("Filtrdan tushgan", max(scanned - eligible, 0))
        cols[3].metric("Parallel ishchilar", int(summary.get("parallel_workers", 1)))
        thresholds = summary.get("rvol_thresholds") or {}
        st.caption(
            f"So‘nggi skan: preset **{summary.get('scan_preset')}**, `STRATEGY_MODE={summary.get('strategy_mode')}`, "
            f"RVOL ≥ {thresholds.get('min_rvol', '—')}, change% ≥ {thresholds.get('min_change_percent', '—')}."
        )
        st.caption(f"Aktiv rejim · **{_strategy_mode_title(current_mode)}**")
    elif summary:
        st.caption(
            f"Skan: **{summary.get('tickers_scanned')}** symbol, pass **{summary.get('eligible_signals')}** — "
            "metrika blokini **Platform dizayni**dan yoqing."
        )

    if not summary:
        if st.session_state.get("platform_show_chain", True):
            st.info(
                "Boshlash uchun **Run market scan** bosing — rejimga mos zanjir yuqoridagi expander’da qisqacha yozilgan.",
                icon="📡",
            )
        else:
            st.info("Boshlash uchun **Run market scan** bosing.", icon="📡")

    tabs = st.tabs(["Mos kelganlar", "Barcha skan", "Paper savdo"])

    table = signals_dataframe(signals, current_mode)

    with tabs[0]:
        st.subheader("Saralangan signal jadvali")
        if not summary:
            st.info("Avval **Run market scan**.", icon="📡")
        elif table.empty:
            if _intraday_strategy_mode(str(current_mode)):
                st.warning(
                    "Hozircha VWAP cross signali yo‘q. **Barcha skan** tabida batafsil ko‘ring yoki "
                    "Explorer presetini sinab ko‘ring."
                )
            elif _volume_ignition_mode(str(current_mode)):
                st.warning(
                    "Volume ignition filtrlari juda qattiq (RVOL, hajm, qarshilik). **Barcha skan**da *Ign Stage* / "
                    "*Ign R dist%* ustunlariga qarang yoki `.env` da `IGNITION_*` qiymatlarini yumshoqroq qiling."
                )
            else:
                st.warning(
                    "Skan tugadi, lekin hech kim barcha filtrlardan o‘tmadi. **Barcha skan** tabida "
                    "sabablar bor. Tez yechim: sidebar → **Explorer** preset."
                )
        else:
            st.caption(
                "Pastda jadvaldan keyin **yopiq bo‘limlar**: ularning sarlavhasiga bosing — ichida grafik, ChatGPT, "
                "volume ignition matni."
            )
            st.dataframe(table, use_container_width=True, hide_index=True)

            if st.session_state.get("platform_show_3d", False):
                with st.expander("3D signal manzarasi (Scatter3d — narx × RVOL × skor)", expanded=False):
                    render_signals_spatial_landscape(signals)

            if _intraday_strategy_mode(str(current_mode)):
                sigs_with_chart = [s for s in signals if s.get("chart_session_bars")]
                if sigs_with_chart:
                    with st.expander("Intraday grafik (sham + VWAP + BUY/SELL/STOP/TIME)", expanded=False):
                        pick = st.selectbox(
                            "Ticker (chart)",
                            [s["ticker"] for s in sigs_with_chart],
                            key="moskelgan_chart_ticker",
                        )
                        picked = next(s for s in sigs_with_chart if s["ticker"] == pick)
                        render_vwap_mtrade_chart(picked)

            with st.expander("ChatGPT izohlari"):
                for signal in signals:
                    st.markdown(
                        f"**{signal['ticker']}**: {signal.get('chatgpt_reason', 'No reason supplied.')}"
                    )

            if _volume_ignition_mode(str(current_mode)) and signals:
                with st.expander("Volume ignition — strukturali tahlil (REASON→EXECUTION)", expanded=False):
                    pick_vi = st.selectbox(
                        "Ticker",
                        [s["ticker"] for s in signals],
                        key="vi_professional_outline",
                    )
                    svi = next(s for s in signals if s["ticker"] == pick_vi)
                    st.markdown(svi.get("ignition_professional_outline") or "—")

    with tabs[1]:
        st.subheader("Barcha tekshirilgan symbolar")
        st.caption("“Mos kelganlar” bo‘sh bo‘lsa ham, bu yerda barcha ticker va *Failed Rules* ko‘rinadi.")

        scan_df = full_scan_dataframe(full_scan_views)

        if not summary:
            st.info("Skan qilinmagan — avval **Run market scan**.")
        elif scan_df.empty:
            st.warning("Skan natijasi bo‘sh — API yoki internetni tekshiring.", icon="⚠️")
        else:
            st.dataframe(scan_df, use_container_width=True, hide_index=True)

            csv_bytes = scan_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "CSV yuklab olish",
                data=csv_bytes,
                file_name="full_scan_snapshot.csv",
                mime="text/csv",
                help="Mahalliy Excel’da ochish uchun.",
            )

            st.caption("Diskdan: `logs/full_scan.csv`, signal loglari: `logs/signals.csv`.")

    with tabs[2]:
        render_paper_trading_panel(signals)


if __name__ == "__main__":
    main()
