import json
import os
import re

# Render platform: PORT va RENDER=true avtomatik (https://render.com/docs/environment-variables)
# STREAMLIT importidan oldin — telemetry va headless uchun.
if os.environ.get("RENDER", "").strip().lower() == "true":
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from agents.bootstrap_env import ensure_env_file, load_project_env
from agents.scan_pipeline import SidebarControls, build_scan_agents, run_scan_market
from agents.scan_presets import SCAN_PRESETS
from agents.strategy_factory import resolve_strategy_mode
from agents.trade_plan_format import deterministic_trade_plan_from_signal
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
            div[data-testid="stMetric"] {
                border: 1px solid rgba(148,163,184,0.22);
                border-radius: 14px;
                padding: 0.35rem 0.55rem;
                box-shadow: 0 8px 22px rgba(2,6,23,0.08);
            }
            div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
            .stButton > button {
                border-radius: 10px !important;
                border: 1px solid rgba(148,163,184,0.28) !important;
                box-shadow: 0 4px 14px rgba(2,6,23,0.08);
            }
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
            div[data-testid="stMetric"] {
                border: 1px solid rgba(148,163,184,0.22);
                border-radius: 14px;
                padding: 0.35rem 0.55rem;
                background: linear-gradient(160deg, rgba(15,23,42,0.72) 0%, rgba(2,6,23,0.86) 100%);
                box-shadow: 0 10px 26px rgba(2,6,23,0.26);
            }
            div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
            .stButton > button {
                border-radius: 10px !important;
                border: 1px solid rgba(148,163,184,0.28) !important;
                background: linear-gradient(180deg, rgba(30,41,59,0.88), rgba(15,23,42,0.95)) !important;
            }
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


def render_ai_provider_status() -> None:
    """DeepSeek/OpenAI ulanish holatini bir qarashda ko'rsatish."""

    ai_provider = (os.getenv("AI_PROVIDER", "auto").strip().lower() or "auto")
    ds_key = bool(os.getenv("DEEPSEEK_API_KEY", "").strip())
    oa_key = bool(os.getenv("OPENAI_API_KEY", "").strip())
    ds_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"

    if ai_provider == "deepseek":
        route = "DeepSeek (primary)"
    elif ai_provider == "openai":
        route = "OpenAI (primary)"
    else:
        route = "Auto: DeepSeek -> OpenAI fallback"

    cols = st.columns(4)
    cols[0].metric("AI route", route)
    cols[1].metric("DeepSeek", "Connected" if ds_key else "Missing key")
    cols[2].metric("OpenAI", "Connected" if oa_key else "Missing key")
    cols[3].metric("DeepSeek model", ds_model)

    if not ds_key and not oa_key:
        st.warning("AI kalitlari topilmadi: DEEPSEEK_API_KEY yoki OPENAI_API_KEY ni yoqing.")
    elif ai_provider == "deepseek" and not ds_key:
        st.warning("AI_PROVIDER=deepseek, lekin DEEPSEEK_API_KEY yo'q. Fallback uchun OpenAI ishlashi mumkin.")
    elif ai_provider == "openai" and not oa_key:
        st.warning("AI_PROVIDER=openai, lekin OPENAI_API_KEY yo'q. Fallback uchun DeepSeek ishlashi mumkin.")
    else:
        st.caption("AI provayder holati normal. Skan natijasida `AI` ustunida qarorlar ko'rinadi.")


def _display_metric(signal: Dict[str, Any], *keys: str) -> Any:
    """Jadvalda None o‘rniga —; RVOL rejimida kunlik indikatorlarni ham qabul qiladi."""

    for key in keys:
        val = signal.get(key)
        if val is not None and val != "":
            return val
    return "—"


def _signal_row_status(signal: Dict[str, Any]) -> str:
    if signal.get("watchlist_only"):
        return "WATCHLIST"
    if signal.get("paper_trade_ready"):
        return "PAPER READY"
    if signal.get("strategy_pass"):
        return "PASS"
    return "BLOCKED"


def _split_pass_and_watchlist(signals: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    passes = [s for s in signals if not s.get("watchlist_only")]
    watchlist = [s for s in signals if s.get("watchlist_only")]
    return passes, watchlist


def _signal_table_row(signal: Dict[str, Any], strategy_mode: str) -> Dict[str, Any]:
    paper_ready = bool(signal.get("paper_trade_ready"))
    block_reason = str(signal.get("paper_trade_block_reason") or "").strip()
    intraday = _intraday_strategy_mode(strategy_mode)
    rsi_label = "RSI (sessiya)" if intraday else "RSI (kunlik)"
    atr_label = "ATR (sessiya)" if intraday else "ATR (kunlik)"
    row: Dict[str, Any] = {
        "Holat": _signal_row_status(signal),
        "Ticker": signal.get("ticker"),
        "Price": signal.get("price"),
        "RVOL": signal.get("rvol"),
        "Score": signal.get("score"),
        "AI": signal.get("chatgpt_decision"),
        "Paper": "READY" if paper_ready else "BLOCKED",
        "Why blocked": block_reason or "—",
        "Strategy": signal.get("strategy_name"),
        "Change %": signal.get("change_percent"),
        "Volume": signal.get("volume"),
        "Avg Volume": signal.get("avg_volume"),
        "TP": _display_metric(signal, "take_profit_suggestion", "trade_tp1"),
        "SL": _display_metric(signal, "stop_suggestion", "trade_stop_loss"),
        "Kirish/SL/TP": _display_metric(signal, "trade_levels_line"),
        "VWAP": _display_metric(signal, "session_vwap"),
        rsi_label: _display_metric(signal, "rsi_14", "daily_rsi_14"),
        atr_label: _display_metric(signal, "atr_14", "daily_atr_14"),
        "VWAP cross": _display_metric(signal, "vwap_cross"),
        "Risk": _display_metric(signal, "risk_level"),
        "Data delay": signal.get("data_delay"),
        "Updated": signal.get("updated_time"),
        "TV Chart": tradingview_url(signal.get("ticker")),
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


def tradingview_url(ticker: Any) -> str:
    t = str(ticker or "").strip().upper()
    if not t:
        return ""
    # Odatda US aksiyalar uchun NASDAQ prefiksi eng ko'p ishlaydi; foydalanuvchi istasa /tv orqali exchange bilan ham yuboradi.
    symbol = t if ":" in t else f"NASDAQ:{t}"
    return f"https://www.tradingview.com/chart/?symbol={quote(symbol, safe=':')}"


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
    """Scatter3d + 2D: narx × RVOL × skor — kamroq shovqin, ko‘proq qaror qo‘llovi."""

    try:
        import plotly.graph_objects as go
    except ImportError:
        st.warning("`plotly` topilmadi. `pip install -r requirements.txt`")
        return

    rows: List[Tuple[float, float, float, str]] = []
    ranked_signals = sorted(signals, key=lambda item: (bool(item.get("paper_trade_ready")), float(item.get("score") or 0)), reverse=True)
    subset = ranked_signals[:30]
    for s in subset:
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

    top_labels = set(texts[:8])
    fig = go.Figure(
        data=[
            go.Scatter3d(
                x=xs,
                y=ys,
                z=zs,
                mode="markers+text",
                text=[t if t in top_labels else "" for t in texts],
                textposition="top center",
                textfont={"size": 10},
                marker={
                    "size": [10 if subset[i].get("paper_trade_ready") else 6 for i in range(len(subset))],
                    "color": zs,
                    "colorscale": "Temps",
                    "opacity": 0.88,
                    "showscale": True,
                    "colorbar": {
                        "title": {"text": "Skor", "font": {"size": 11}},
                        "tickfont": {"size": 10},
                    },
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
        title={"text": "3D signal maydoni (top 30, label faqat eng muhimlar)", "font": {"size": 15}},
        height=520,
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        scene={
            "xaxis_title": "Narx ($)",
            "yaxis_title": "RVOL",
            "zaxis_title": "Skor",
            "bgcolor": scene_bg,
            "aspectmode": "data",
        },
    )

    _safe = "".join(texts[:3]) + "_" + str(len(rows))
    plot_key = "spatial_landscape_" + _safe.replace(" ", "_")[:104]
    c3d, c2d = st.columns([3, 2])
    with c3d:
        try:
            st.plotly_chart(fig, use_container_width=True, key=plot_key)
        except TypeError:
            st.plotly_chart(fig, use_container_width=True)
    with c2d:
        fig2 = go.Figure(
            data=[
                go.Scatter(
                    x=ys,
                    y=zs,
                    mode="markers+text",
                    text=[t if t in top_labels else "" for t in texts],
                    textposition="top center",
                    marker={
                        "size": [10 if subset[i].get("paper_trade_ready") else 7 for i in range(len(subset))],
                        "color": xs,
                        "colorscale": "Blues",
                        "showscale": True,
                        "colorbar": {"title": "Narx"},
                    },
                    hovertemplate="<b>%{text}</b><br>RVOL: %{x}<br>Skor: %{y}<extra></extra>",
                )
            ]
        )
        fig2.update_layout(
            template=tmpl,
            title={"text": "2D fokus — RVOL × Skor", "font": {"size": 14}},
            height=520,
            margin={"l": 10, "r": 10, "t": 40, "b": 10},
            xaxis_title="RVOL",
            yaxis_title="Skor",
        )
        st.plotly_chart(fig2, use_container_width=True)




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

    max_symbols = st.sidebar.slider(
        "Skan qilinadigan tickers", min_value=10, max_value=15000, value=300, step=10
    )
    st.sidebar.caption("Katta qiymatlar (1000+) barcha US aksiyalariga yaqinroq qamrov beradi, lekin vaqt ko‘proq oladi.")

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
    mode_now = os.getenv("TRADING_MODE", "paper")
    base_now = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    st.sidebar.write(f"TRADING_MODE: `{mode_now}`")
    st.sidebar.write(f"ALPACA_BASE_URL: `{base_now}`")
    st.sidebar.write(f"MAX_POSITION_SIZE_USD: `{os.getenv('MAX_POSITION_SIZE_USD', '10000')}`")
    if mode_now.strip().lower() != "paper" or "paper-api.alpaca.markets" not in base_now:
        st.sidebar.warning("Paper orderlar blok bo‘lishi mumkin: `TRADING_MODE=paper` va `ALPACA_BASE_URL=...paper-api...` bo‘lsin.")

    st.sidebar.divider()
    with st.sidebar.expander("Qisqa yordam", expanded=False):
        st.markdown(
            """
1. **Run market scan** ni bosing.
2. **Mos kelganlar** — tez qaror jadvali.
3. **Barcha skan** — nega o‘tmaganini ko‘rsatadi.
4. **Paper savdo** — faqat tayyor signal bilan order preview.

**Streamlit ishga tushirish**:
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

    ready_signals = [signal for signal in signals if signal.get("paper_trade_ready")]
    blocked_signals = [signal for signal in signals if not signal.get("paper_trade_ready")]
    show_blocked = st.checkbox(
        "Bloklangan setup-larni ham ko‘rsat",
        value=not bool(ready_signals),
        help="O‘chiq bo‘lsa faqat paper-trade tayyor signallar ko‘rinadi.",
    )

    available_signals = signals if show_blocked or not ready_signals else ready_signals
    if not available_signals:
        st.warning("Paper savdo uchun hali tayyor signal yo‘q.")
        return

    def _paper_label(signal: Dict[str, Any]) -> str:
        status = "READY" if signal.get("paper_trade_ready") else "BLOCKED"
        reason = str(signal.get("paper_trade_block_reason") or "").strip()
        suffix = f" — {reason}" if reason else ""
        return f"{signal['ticker']} [{status}]{suffix}"

    selected_label = st.selectbox(
        "Ticker",
        [_paper_label(signal) for signal in available_signals],
        key="paper_pick_ticker",
    )
    selected_signal = next(signal for signal in available_signals if _paper_label(signal) == selected_label)
    selected_ticker = str(selected_signal["ticker"])
    tv_link = tradingview_url(selected_ticker)

    if blocked_signals and ready_signals:
        st.caption(
            f"Paper-ready: **{len(ready_signals)}** · bloklangan setup: **{len(blocked_signals)}**. "
            "Bloklanganlar scannerdan o‘tgan, lekin savdoga hali tayyor emas."
        )
    elif blocked_signals and not ready_signals:
        st.warning("Hozircha barcha setup bloklangan — AI yoki RiskManager izohlarini pastda ko‘ring.")

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

    q1, q2, q3 = st.columns(3)
    q1.link_button("TradingView chart", tv_link, use_container_width=True)
    q2.link_button(
        "Finviz snapshot",
        f"https://finviz.com/quote.ashx?t={selected_ticker}",
        use_container_width=True,
    )
    q3.caption("Chartni alohida tabda ochib, entry/SL ni tez tekshiring.")

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
        "reason": selected_signal.get("chatgpt_reason"),
    }
    order = {"quantity": int(quantity), "stop_loss": float(stop_loss), "take_profit": float(take_profit)}
    approved, reason = agents["risk"].approve_order(selected_signal, analyst_view, order)

    ai_cols = st.columns(4)
    ai_cols[0].metric("AI decision", selected_signal.get("chatgpt_decision") or "—")
    ai_cols[1].metric("Allow order", "Yes" if selected_signal.get("chatgpt_allow_order") else "No")
    ai_cols[2].metric("Paper ready", "Yes" if selected_signal.get("paper_trade_ready") else "No")
    ai_cols[3].metric("Risk level", selected_signal.get("risk_level") or "—")

    if selected_signal.get("paper_trade_block_reason"):
        st.warning(f"Paper block: {selected_signal.get('paper_trade_block_reason')}")
    if selected_signal.get("paper_ready_blocked_field"):
        st.caption(f"paper_ready_blocked: {selected_signal.get('paper_ready_blocked_field')}")
    hard_flags = _parse_json_list(selected_signal.get("chatgpt_risk_flags_hard_json"))
    if hard_flags:
        st.caption(f"Hard AI flags: {', '.join(hard_flags)}")
    st.caption(selected_signal.get("chatgpt_reason") or "AI izohi yo‘q.")

    plan_md = (selected_signal.get("analyst_trade_plan_text") or "").strip()
    if not plan_md:
        plan_md = deterministic_trade_plan_from_signal(
            selected_signal,
            lang=os.getenv("ANALYST_TRADE_PLAN_LANG", "en"),
        )
    if plan_md.strip():
        with st.expander("Professional trade plan (analyst framework)", expanded=False):
            st.markdown(plan_md)

    st.write(f"RiskManager status: {'Approved' if approved else 'Blocked'} - {reason}")
    with st.expander("Nega order ketmayapti? (tez diagnostika)", expanded=not approved):
        st.markdown(
            f"""
- `TRADING_MODE`: `{os.getenv('TRADING_MODE', 'paper')}`
- `ALPACA_BASE_URL`: `{os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')}`
- `MAX_POSITION_SIZE_USD`: `{os.getenv('MAX_POSITION_SIZE_USD', '10000')}`
- `MAX_RISK_PCT_OF_EQUITY`: `{os.getenv('MAX_RISK_PCT_OF_EQUITY', os.getenv('MAX_RISK_PCT', '1.0'))}`
- `MIN_RISK_REWARD_RATIO`: `{os.getenv('MIN_RISK_REWARD_RATIO', '2.0')}`
- RiskManager reason: **{reason}**
"""
        )
        st.caption(
            "Agar `Blocked` chiqsa, odatda sabab: AI allow=false, R:R past, stop noto‘g‘ri, quantity risk budgetdan katta, "
            "yoki notional `MAX_POSITION_SIZE_USD` dan yuqori."
        )
        if not approved:
            suggestions: List[str] = []
            text_reason = str(reason or "")

            m_qty = re.search(r"risk budget qty (\d+)", text_reason)
            if m_qty:
                suggestions.append(f"Quantity ni <b>{m_qty.group(1)}</b> yoki undan pastga tushiring.")

            m_notional = re.search(r"Position size \$([0-9.]+) exceeds \$([0-9.]+)", text_reason)
            if m_notional and price > 0:
                try:
                    max_notional = float(m_notional.group(2))
                    max_qty = int(max_notional // price)
                    if max_qty > 0:
                        suggestions.append(
                            f"Notional limit uchun quantity taxminan <b>{max_qty}</b> yoki past bo‘lsin "
                            f"(narx ${price:.2f} atrofida)."
                        )
                except ValueError:
                    pass

            if "Risk:reward too low" in text_reason and price > 0 and stop_loss > 0 and stop_loss < price:
                min_rr = float(os.getenv("MIN_RISK_REWARD_RATIO", "2.0"))
                risk_per_share = price - stop_loss
                suggested_tp = round(price + (min_rr * risk_per_share), 4)
                suggestions.append(
                    f"R:R oshirish uchun Take Profitni kamida <b>{suggested_tp}</b> ga qo‘ying "
                    f"(joriy min R:R = {min_rr})."
                )

            if "Stop loss must be below the current price" in text_reason:
                suggestions.append(f"Stop lossni narxdan past qo‘ying (masalan <b>{round(price * 0.98, 4)}</b>).")

            if "AI analyst did not allow" in text_reason or "AI analyst decision is not watch-worthy" in text_reason:
                suggestions.append(
                    "Bu setup AI tomonidan bloklangan: avval boshqa ticker tanlang yoki keyingi /scan natijasini kuting."
                )

            if suggestions:
                st.markdown("##### Tez auto-fix tavsiyalar")
                for s in suggestions:
                    st.markdown(f"- {s}", unsafe_allow_html=True)

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
    render_ai_provider_status()
    st.divider()

    st.session_state.setdefault("signals", [])
    st.session_state.setdefault("full_scan", [])
    st.session_state.setdefault("scan_summary", None)

    c_run, c_hint = st.columns([1, 2])
    with c_run:
        run_clicked = st.button("Run market scan", type="primary", use_container_width=True)
    with c_hint:
        st.caption(
            "Skandan keyin yuqorida umumiy metrikalar, pastda esa **tez qaror jadvali**, to‘liq skan va paper savdo yangilanadi."
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
        paper_ready = int(summary.get("paper_ready_signals", 0))
        cols = st.columns(4)
        cols[0].metric("Skanlangan", scanned, help="Universe dan olingan symbolar soni")
        cols[1].metric("Signal (pass)", eligible, help="Strategiya filtridan o‘tgan va AI ko‘rilgan setup.")
        cols[2].metric("Paper ready", paper_ready, help="Paper savdo uchun hozir tayyor setup.")
        cols[3].metric("Bloklangan", max(eligible - paper_ready, 0), help="Scan o‘tgan, lekin savdoga hali tayyor emas.")
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

    pass_signals, watchlist_signals = _split_pass_and_watchlist(signals)
    table = signals_dataframe(pass_signals, current_mode)
    watchlist_table = signals_dataframe(watchlist_signals, current_mode) if watchlist_signals else None

    with tabs[0]:
        st.subheader("Tez qaror jadvali")
        if not summary:
            st.info("Avval **Run market scan**.", icon="📡")
        elif table.empty and not watchlist_signals:
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
            if pass_signals:
                st.caption(
                    "Faqat strategiya filtridan o‘tgan setup-lar. "
                    "`Paper=READY` va yuqori `Score` ustunlariga qarang."
                )
                st.dataframe(
                    table,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "TV Chart": st.column_config.LinkColumn(
                            "TV Chart",
                            help="TradingView chartni yangi tabda oching",
                            display_text="Chart",
                        )
                    },
                )
            elif watchlist_signals:
                st.warning(
                    "Hozircha **haqiqiy signal yo‘q** — pastda faqat kuzatuv ro‘yxati (filtrlardan to‘liq o‘tmagan).",
                    icon="⚠️",
                )

            wl_count = int(summary.get("watchlist_fallback_count") or len(watchlist_signals))
            if watchlist_signals and watchlist_table is not None:
                with st.expander(
                    f"Kuzatuv ro‘yxati ({wl_count}) — signal emas, yaqin kandidatlar",
                    expanded=not pass_signals,
                ):
                    st.caption(
                        "RVOL yoki boshqa qoidalar yetmagan tickerlar. "
                        "KIRISH/SL/TP taxminiy — savdo uchun PASS kerak."
                    )
                    st.dataframe(watchlist_table, use_container_width=True, hide_index=True)

            if st.session_state.get("platform_show_3d", False) and pass_signals:
                with st.expander("3D va 2D signal fokus manzarasi", expanded=False):
                    render_signals_spatial_landscape(pass_signals)

            if _intraday_strategy_mode(str(current_mode)):
                sigs_with_chart = [s for s in pass_signals if s.get("chart_session_bars")]
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
                missing_reason_count = 0
                for signal in pass_signals:
                    ticker = signal["ticker"]
                    decision = signal.get("chatgpt_decision") or "—"
                    reason = str(signal.get("chatgpt_reason") or "").strip()
                    if not reason or reason.lower() == "no reason supplied.":
                        missing_reason_count += 1
                        reason = "Batafsil izoh qaytmadi (qisqa AI javob)."
                    st.markdown(f"- **{ticker}** · `{decision}` · {reason}")
                if missing_reason_count:
                    st.caption(f"Izohsiz yoki qisqa javob: {missing_reason_count} ta ticker.")

            if _volume_ignition_mode(str(current_mode)) and pass_signals:
                with st.expander("Volume ignition — strukturali tahlil (REASON→EXECUTION)", expanded=False):
                    pick_vi = st.selectbox(
                        "Ticker",
                        [s["ticker"] for s in pass_signals],
                        key="vi_professional_outline",
                    )
                    svi = next(s for s in pass_signals if s["ticker"] == pick_vi)
                    st.markdown(svi.get("ignition_professional_outline") or "—")

            if pass_signals:
                with st.expander("Professional trade plan (analyst framework)", expanded=False):
                    pick_plan = st.selectbox(
                        "Ticker",
                        [s["ticker"] for s in pass_signals],
                        key="moskelgan_trade_plan_ticker",
                    )
                    sig_plan = next(s for s in pass_signals if s["ticker"] == pick_plan)
                    plan_md = (str(sig_plan.get("analyst_trade_plan_text") or "")).strip()
                    if not plan_md:
                        plan_md = deterministic_trade_plan_from_signal(
                            sig_plan,
                            lang=os.getenv("ANALYST_TRADE_PLAN_LANG", "en"),
                        )
                    if plan_md.strip():
                        st.markdown(plan_md)
                    else:
                        st.caption("Trade plan hali yo‘q — skanni LLM yoki ignition bilan qayta ishga tushiring.")

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
        render_paper_trading_panel(pass_signals if summary else signals)


if __name__ == "__main__":
    main()
