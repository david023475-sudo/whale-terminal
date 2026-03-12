# =============================================================================
# WHALE TERMINAL ELITE — app.py  v8.0
# Upgrades: Conservative Fair Value, Interactive Chart, Earnings Warning
# =============================================================================
from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime
import os, json, requests
try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

# ── yahooquery — richer fundamentals, analyst estimates, balance sheet ────────
# Primary source for all financial ratios, EV, analyst EPS estimates.
# Install: pip install yahooquery
try:
    from yahooquery import Ticker as YQTicker
    _YQ_AVAILABLE = True
except ImportError:
    _YQ_AVAILABLE = False
    YQTicker = None  # type: ignore

# ── yahoo_fin — lightweight last-resort fallback for key stats ────────────────
# Install: pip install yahoo_fin requests_html
try:
    import yahoo_fin.stock_info as _yf_fin
    _YFIN_AVAILABLE = True
except ImportError:
    _YFIN_AVAILABLE = False
    _yf_fin = None  # type: ignore

from langchain_groq import ChatGroq

from whale_terminal_modules import (
    AuthManager, PortfolioManager, WatchlistManager,
    render_watchlist_sidebar, render_watchlist_page,
    render_dcf_tab, render_relative_strength_tab, render_backtest_tab,
    render_polymarket_tab,
    get_auto_peers, render_peer_group_info,
    _strip_tz, SECTOR_ETF_MAP, SECTOR_COLORS,
)

# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="🐳 Whale Terminal Elite", layout="wide",
                   initial_sidebar_state="expanded")

# ===================== GLOBAL THEME CSS =====================================
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif !important; }
.main { background: #080c1a; }
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #06091a 0%, #0d1128 100%) !important;
    border-right: 1px solid #1e2a45;
}
div[data-testid="stMetric"] {
    background: linear-gradient(135deg,rgba(13,17,40,0.95),rgba(8,12,26,0.95));
    border:1px solid #1e2a45; border-left:3px solid #58a6ff; border-radius:12px;
    padding:18px 20px; transition:all 0.25s;
}
div[data-testid="stMetric"]:hover {
    border-left-color:#e3b341; transform:translateY(-3px);
    box-shadow:0 8px 24px rgba(88,166,255,0.15);
}
div[data-testid="stMetricLabel"] {
    color:#58a6ff !important; font-weight:700 !important;
    font-size:0.8rem !important; text-transform:uppercase; letter-spacing:1.2px;
}
div[data-testid="stMetricValue"] {
    color:#f0f6fc !important; font-size:1.7rem !important; font-weight:800 !important;
}
.page-title {
    background: linear-gradient(90deg,#58a6ff 0%,#e3b341 100%);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    font-size:2rem; font-weight:900; margin-bottom:4px;
}
.ticker-chip {
    display:inline-block; background:rgba(88,166,255,0.12);
    border:1px solid rgba(88,166,255,0.3); border-radius:6px;
    padding:3px 10px; color:#58a6ff;
    font-family:'JetBrains Mono',monospace; font-weight:600; font-size:0.85rem;
}
.info-card {
    background:rgba(13,17,40,0.9); border:1px solid #1e2a45; border-radius:12px;
    padding:20px 24px; margin-bottom:16px;
}
.gold-accent { border-left:3px solid #e3b341; }
.risk-card {
    background:rgba(13,17,40,0.9); border:1px solid #1e2a45;
    border-left:3px solid #e3b341; border-radius:10px;
    padding:14px 18px; margin-bottom:8px;
}
.agent-verdict {
    background: linear-gradient(135deg,rgba(30,42,69,0.95),rgba(13,17,40,0.98));
    border:1px solid rgba(88,166,255,0.25); border-radius:14px;
    padding:24px 28px; margin:16px 0;
}
.stButton > button[kind="primary"] {
    background:linear-gradient(135deg,#e3b341 0%,#f0c55a 100%) !important;
    color:#0a0e1a !important; border:none; font-weight:800; border-radius:8px;
}
.stButton > button[kind="primary"]:hover {
    background:linear-gradient(135deg,#f0c55a 0%,#e3b341 100%) !important;
    box-shadow:0 6px 18px rgba(227,179,65,0.35) !important;
}
.stButton > button { border-radius:8px; font-weight:600; transition:all 0.2s; }
.dataframe th {
    background:rgba(13,17,40,0.95) !important; color:#58a6ff !important;
    font-weight:700 !important;
}
.dataframe td { color:#c9d1d9 !important; }
input, .stTextInput input {
    background:rgba(13,17,40,0.9) !important; border:1px solid #1e2a45 !important;
    color:#f0f6fc !important; border-radius:8px !important;
}
input:focus, .stTextInput input:focus {
    border-color:#58a6ff !important;
    box-shadow:0 0 0 2px rgba(88,166,255,0.2) !important;
}
hr { border:none; height:1px;
    background:linear-gradient(90deg,transparent,#1e2a45,transparent); margin:28px 0; }
.stAlert {
    background:rgba(13,17,40,0.9) !important;
    border-left:3px solid #58a6ff !important; border-radius:8px !important;
}
.stTabs [data-baseweb="tab-list"] {
    background:rgba(13,17,40,0.8); border-radius:10px; padding:4px;
}
.stTabs [data-baseweb="tab"] { border-radius:7px; color:#8b949e; font-weight:600; }
.stTabs [aria-selected="true"] {
    background:rgba(88,166,255,0.15) !important; color:#58a6ff !important;
}
.stRadio > label { display:none; }
</style>""", unsafe_allow_html=True)

# ── Phone Mode CSS — injected only when toggle is ON ─────────────────────────
if st.session_state.get("phone_mode", False):
    st.markdown("""<style>
/* ═══ Phone Mode ═══════════════════════════════════════════════════════
   Root cause of tl1 ("P.. $..."): Streamlit's st.columns() creates a
   horizontal flexbox. On a narrow screen each column gets ~20% width,
   forcing stMetricLabel to truncate with "...".
   Fix A — stack columns vertically (flex-direction:column).
   Fix B — give every column 100% width so labels have room to render.
   Fix C — remove ALL text-overflow/overflow/white-space constraints on
            the metric label and value nodes.
   ═══════════════════════════════════════════════════════════════════════ */

[data-testid="stApp"] { background:#0e1117 !important; }

/* Phone frame — max 450px centred */
[data-testid="stAppViewContainer"] {
    max-width: 450px !important;
    width: 100% !important;
    margin: 0 auto !important;
    background: #080c1a !important;
    border-left:  1px solid #1e2a45 !important;
    border-right: 1px solid #1e2a45 !important;
    min-height: 100vh !important;
    overflow-x: hidden !important;
}
[data-testid="stAppViewBlockContainer"], .block-container {
    max-width: 450px !important;
    padding-left:  14px !important;
    padding-right: 14px !important;
    box-sizing: border-box !important;
    overflow-x: hidden !important;
}

/* FIX A+B: Stack columns, full width each */
[data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
    align-items: stretch !important;
    gap: 6px !important;
    overflow-x: hidden !important;
}
[data-testid="column"] {
    width: 100% !important;
    min-width: 100% !important;
    max-width: 100% !important;
    flex: 0 0 100% !important;
    overflow: visible !important;
}

/* FIX C: Metric label & value — remove ALL clipping */
[data-testid="stMetric"] {
    width: 100% !important;
    box-sizing: border-box !important;
    padding: 14px 16px !important;
    margin-bottom: 6px !important;
}
/* The label node Streamlit generates: <div data-testid="stMetricLabel"> */
[data-testid="stMetricLabel"] {
    overflow: visible !important;
    white-space: normal !important;
    text-overflow: unset !important;
    width: 100% !important;
    max-width: none !important;
    font-size: 0.78rem !important;
    color: #8b949e !important;
}
/* Sometimes the label is wrapped in a <label> or <div> child */
[data-testid="stMetricLabel"] > * {
    overflow: visible !important;
    white-space: normal !important;
    text-overflow: unset !important;
}
[data-testid="stMetricValue"] {
    overflow: visible !important;
    white-space: normal !important;
    text-overflow: unset !important;
    font-size: 1.25rem !important;
    color: #f0f6fc !important;
    word-break: break-word !important;
}
[data-testid="stMetricDelta"] { font-size: 0.72rem !important; }

/* Plotly charts */
[data-testid="stPlotlyChart"] {
    width: 100% !important;
    max-width: 422px !important;
    overflow-x: auto !important;
}
/* DataFrames */
[data-testid="stDataFrame"], [data-testid="stTable"] {
    width: 100% !important;
    max-width: 422px !important;
    overflow-x: auto !important;
    display: block !important;
}
/* Tabs */
.stTabs [data-baseweb="tab-list"] { flex-wrap: wrap !important; gap: 4px !important; }
.stTabs [data-baseweb="tab"]      { font-size: 0.72rem !important; padding: 5px 8px !important; }

html { font-size: 14px !important; }
/* Prevent iOS auto-zoom on inputs */
input, textarea, select, .stTextInput input { font-size: 16px !important; }

/* On actual phones — drop the decorative frame */
@media (max-width: 480px) {
    [data-testid="stAppViewContainer"] {
        border: none !important; max-width: 100% !important;
    }
    [data-testid="stAppViewBlockContainer"], .block-container {
        padding-left: 10px !important; padding-right: 10px !important;
    }
}
</style>""", unsafe_allow_html=True)

# ===================== CONFIG — secrets via st.secrets =======================
# ─────────────────────────────────────────────────────────────────────────────
# HARDCODED FALLBACKS — edit these if st.secrets is not loading correctly.
# These are only used when st.secrets and environment variables both return
# empty strings (e.g. during local dev without a secrets.toml, or if Streamlit
# Cloud fails to inject secrets). Remove or blank them out for production.
# ─────────────────────────────────────────────────────────────────────────────
_FALLBACK_FMP_API_KEY    = "a"
_FALLBACK_SUPABASE_URL   = "a"
_FALLBACK_SUPABASE_KEY   = "a"
_FALLBACK_GROQ_API_KEY   = "a"
_FALLBACK_NEWS_API_KEY   = "a"
_FALLBACK_ALPACA_KEY     = ""   # not configured yet
_FALLBACK_ALPACA_SECRET  = ""   # not configured yet

_FALLBACKS: dict[str, str] = {
    "FMP_API_KEY":    _FALLBACK_FMP_API_KEY,
    "SUPABASE_URL":   _FALLBACK_SUPABASE_URL,
    "SUPABASE_ANON_KEY": _FALLBACK_SUPABASE_KEY,
    "GROQ_API_KEY":   _FALLBACK_GROQ_API_KEY,
    "NEWS_API_KEY":   _FALLBACK_NEWS_API_KEY,
    "ALPACA_KEY":     _FALLBACK_ALPACA_KEY,
    "ALPACA_SECRET":  _FALLBACK_ALPACA_SECRET,
}

# Helper: st.secrets first, os.environ second, hardcoded fallback third
def _secret(key: str, default: str = "") -> str:
    """
    Priority:
      1. st.secrets[key]   — Streamlit Cloud / .streamlit/secrets.toml
      2. os.environ[key]   — Docker / local env vars
      3. _FALLBACKS[key]   — hardcoded values above (last resort)
      4. default           — empty string (feature degrades gracefully)
    Never raises; missing secrets disable features without crashing.
    """
    try:
        v = str(st.secrets[key])
        if v:
            return v
    except (KeyError, FileNotFoundError, Exception):
        pass
    env_val = os.environ.get(key, "")
    if env_val:
        return env_val
    return _FALLBACKS.get(key, default)

GROQ_API_KEY  = _secret("GROQ_API_KEY")
FMP_API_KEY   = _secret("FMP_API_KEY")
NEWS_API_KEY  = _secret("NEWS_API_KEY")
ALPACA_KEY    = _secret("ALPACA_KEY")
ALPACA_SECRET = _secret("ALPACA_SECRET")
SUPABASE_URL  = _secret("SUPABASE_URL")
SUPABASE_KEY  = _secret("SUPABASE_ANON_KEY")

# Warn once at startup if the LLM key is missing
if not GROQ_API_KEY:
    st.warning(
        "**GROQ_API_KEY** is not configured — AI analysis will be unavailable.  \n"
        "Add it to `.streamlit/secrets.toml` (local) or the Streamlit Cloud "
        "**Secrets** panel:  \n```toml\nGROQ_API_KEY = \"gsk_...\"\n```",
    )

# Initialise LLM — gracefully disabled if key is absent
if GROQ_API_KEY:
    os.environ["GROQ_API_KEY"] = GROQ_API_KEY   # langchain-groq reads from env
    try:
        llm = ChatGroq(model_name="llama-3.1-8b-instant", temperature=0.1)
    except Exception as _llm_err:
        st.warning(f"Could not initialise Groq LLM: {_llm_err}")
        llm = None
else:
    llm = None

@st.cache_resource
def _auth():    return AuthManager(SUPABASE_URL, SUPABASE_KEY)
@st.cache_resource
def _wm():      return WatchlistManager(SUPABASE_URL, SUPABASE_KEY)
@st.cache_resource
def _portmgr(): return PortfolioManager(SUPABASE_URL, SUPABASE_KEY)

auth    = _auth()
wm      = _wm()
portmgr = _portmgr()

if not auth.is_logged_in():
    auth.render_auth_page()
    st.stop()

USER_ID    = auth.user_id()
USER_EMAIL = auth.user_email()

_DEFAULTS = {
    "active_page":"🏠 Home","analysis_ticker":"NVDA","analysis_timeframe":"1Y",
    "show_advanced":True,"show_ai_verdict":True,"dcf_growth":0.20,"dcf_wacc":0.10,
    "account_size":10000,"risk_pct":0.01,"atr_mult":2.0,
    "analysis_loaded":False,"last_ticker":"","auto_peers":[],
    "chart_indicators":["SMA 50","SMA 200"],
    "chart_show_studies":True,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state: st.session_state[k] = v

PAGES = ["🏠 Home","🔍 Stock Analysis","👀 Watchlist","💼 Portfolio","📰 Global News","⚙️ Settings"]

# ===================== SIDEBAR ===============================================
with st.sidebar:
    st.markdown(
        "<div style='margin-bottom:20px;'>"
        "<div style='font-size:1.6rem;font-weight:900;background:linear-gradient(90deg,#58a6ff,#e3b341);"
        "-webkit-background-clip:text;-webkit-text-fill-color:transparent;'>🐳 Whale Terminal</div>"
        "<div style='color:#8b949e;font-size:0.78rem;margin-top:2px;'>Signed in as "
        f"<span style='color:#58a6ff;'>{USER_EMAIL}</span></div></div>",
        unsafe_allow_html=True,
    )
    active = st.session_state["active_page"]
    for page in PAGES:
        is_a = page == active
        bg = ("background:linear-gradient(135deg,rgba(88,166,255,0.15),rgba(227,179,65,0.06));"
              "border:1px solid rgba(88,166,255,0.3);color:#58a6ff;") if is_a else ""
        st.markdown(
            f"<div style='{bg}display:flex;align-items:center;gap:10px;padding:11px 16px;"
            f"border-radius:9px;margin-bottom:3px;font-weight:700;font-size:0.92rem;'>{page}</div>",
            unsafe_allow_html=True,
        )
        if st.button(page, key=f"nav_{page}", use_container_width=True):
            st.session_state["active_page"] = page; st.rerun()
    st.markdown("---")
    run_analysis = False
    if active == "🔍 Stock Analysis":
        st.markdown("**⚙️ Analysis Controls**")
        new_ticker = st.text_input(
            "Ticker", value=st.session_state["analysis_ticker"],
            help="Stock symbol to analyse", key="sidebar_ticker",
        ).upper().strip()
        if new_ticker and new_ticker != st.session_state["analysis_ticker"]:
            st.session_state["analysis_ticker"] = new_ticker
            st.session_state["auto_peers"]      = []
            st.session_state["analysis_loaded"] = False
        st.session_state["analysis_timeframe"] = st.selectbox(
            "Timeframe", ["1D","5D","1M","3M","6M","1Y","2Y","5Y"], index=5, key="sidebar_tf"
        )
        st.session_state["show_advanced"]   = st.checkbox("Advanced Analytics", True, key="cb_adv")
        st.session_state["show_ai_verdict"] = st.checkbox("AI Agent Verdict",   True, key="cb_ai")
        with st.expander("🧮 DCF Parameters"):
            st.session_state["dcf_growth"] = st.slider("Growth Rate %",5,60,20,key="sl_g")/100
            st.session_state["dcf_wacc"]   = st.slider("WACC %",7,18,10,key="sl_w")/100
        with st.expander("⚖️ Risk Management"):
            st.session_state["account_size"] = st.number_input(
                "Account Size ($)",1000,10_000_000,10_000,1000,key="ni_acc",
                help="Total trading account capital")
            st.session_state["risk_pct"] = st.slider(
                "Risk / Trade %",0.5,3.0,1.0,0.25,key="sl_risk",
                help="Max % of account to risk per trade")/100
            st.session_state["atr_mult"] = st.slider(
                "ATR Multiplier",1.0,4.0,2.0,0.5,key="sl_atr",
                help="Stop distance = ATR × multiplier")
        run_analysis = st.button("🚀 RUN ANALYSIS",type="primary",use_container_width=True)
        st.markdown("---")
        render_watchlist_sidebar(wm, USER_ID, st.session_state["analysis_ticker"])
    st.markdown("---")
    _pm = st.toggle(
        "📱 Phone Mode",
        value=st.session_state.get("phone_mode", False),
        key="phone_mode_toggle",
        help="Stacks metric cards vertically — prevents labels from truncating on narrow screens.",
    )
    st.session_state["phone_mode"] = _pm
    st.markdown("---")
    if st.button("🚪 Sign Out",use_container_width=True,key="so_btn"):
        auth.sign_out(); st.rerun()
    st.markdown(
        "<div style='text-align:center;color:#3d4a5c;font-size:0.72rem;margin-top:16px;'>"
        "Whale Terminal Elite v8.5<br>Institutional Intelligence</div>",
        unsafe_allow_html=True,
    )

# =============================================================================
# SHARED DATA HELPERS
# ─────────────────────────────────────────────────────────────────────────────
# Source architecture:
#   OHLCV history   → yfinance primary (FMP fallback kept for intraday)
#   Fundamentals    → yahooquery PRIMARY → yfinance FALLBACK → yahoo_fin LAST RESORT
#   Forward P/E     → yfinance earnings_estimate "+1y" avg  (NOT info["forwardEps"])
#   Caching         → @st.cache_data(ttl=3600) on every network call
# =============================================================================
RANGE_MAP = {
    "1D":{"period":"1d","interval":"5m"},  "5D":{"period":"5d","interval":"15m"},
    "1M":{"period":"1mo","interval":"1d"}, "3M":{"period":"3mo","interval":"1d"},
    "6M":{"period":"6mo","interval":"1d"}, "1Y":{"period":"1y","interval":"1d"},
    "2Y":{"period":"2y","interval":"1wk"}, "5Y":{"period":"5y","interval":"1wk"},
}

# ── FMP sentinel ──────────────────────────────────────────────────────────────
class _Blocked:
    """Singleton sentinel: FMP returned a plan/legacy block, not real data."""
    _inst = None
    def __new__(cls):
        if cls._inst is None: cls._inst = super().__new__(cls)
        return cls._inst
    def __repr__(self): return "<FMP_BLOCKED>"
_FMP_BLOCKED = _Blocked()

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"

def _fmp_get(path: str, params: dict | None = None, _ui_errors: bool = False):
    """
    Central FMP v3 request helper.
      - Returns parsed data (list/dict) on success.
      - Returns _FMP_BLOCKED sentinel on 403 / Error Message (plan restriction).
      - Returns None on empty response, timeout, or network error.
    """
    if not FMP_API_KEY:
        return _FMP_BLOCKED
    full_url = f"{FMP_BASE_URL}{path}"
    try:
        p = {"apikey": FMP_API_KEY}
        if params:
            p.update(params)
        r = requests.get(full_url, params=p, timeout=10)
        if r.status_code == 403:
            print(f"[FMP 403] {path} — switching to Yahoo Finance fallback")
            return _FMP_BLOCKED
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "Error Message" in data:
            print(f"[FMP blocked] {path}: {data['Error Message'][:140]}")
            return _FMP_BLOCKED
        if data is None or (isinstance(data, (list, dict)) and len(data) == 0):
            if _ui_errors:
                st.warning("No data found for this ticker. Please verify the symbol is correct.")
            return None
        return data
    except requests.exceptions.HTTPError as exc:
        if exc.response.status_code == 403:
            return _FMP_BLOCKED
        print(f"[FMP HTTP {exc.response.status_code}] {path}: {exc}")
        return None
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        print(f"[FMP network error] {path}: {exc}")
        return None
    except Exception as exc:
        print(f"[FMP error] {path}: {exc}")
        return None

# ── Shared float helper ───────────────────────────────────────────────────────
def _sf(v) -> float | None:
    """Safe float cast; returns None on failure or NaN."""
    try:
        f = float(v)
        return None if (f != f) else f   # NaN check
    except (TypeError, ValueError):
        return None

# =============================================================================
# HYBRID FUNDAMENTALS ENGINE
# Three cached fetchers; _merge_dicts combines them with first-non-None wins.
# =============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def _yq_fundamentals(ticker: str) -> dict:
    """
    PRIMARY fundamentals source — yahooquery.
    Fetches financialData, defaultKeyStatistics, summaryDetail, assetProfile,
    price, and earnings_trend (for analyst EPS estimates).
    Returns {} if yahooquery is unavailable or raises.
    """
    if not _YQ_AVAILABLE:
        return {}
    try:
        t  = YQTicker(ticker)

        # One network round-trip each — yahooquery batches these internally
        fd = (t.financial_data  or {}).get(ticker) or {}
        ks = (t.default_key_statistics or {}).get(ticker) or {}
        sd = (t.summary_detail   or {}).get(ticker) or {}
        ap = (t.asset_profile    or {}).get(ticker) or {}
        pr = (t.price            or {}).get(ticker) or {}

        def _g(d, *keys):
            for k in keys:
                v = _sf(d.get(k))
                if v is not None:
                    return v
            return None

        live_price = _g(pr, "regularMarketPrice") or _g(fd, "currentPrice")
        mkt_cap    = _g(pr, "marketCap")
        total_debt = _g(fd, "totalDebt")
        total_cash = _g(fd, "totalCash")
        ebitda     = _g(fd, "ebitda")
        revenue    = _g(fd, "totalRevenue")

        # EV computed explicitly — more accurate than stale key-metrics value
        ev = None
        if mkt_cap is not None:
            ev = mkt_cap + (total_debt or 0) - (total_cash or 0)
        ev_ebitda  = (ev / ebitda  if ev and ebitda  and ebitda  != 0 else None)
        ev_revenue = (ev / revenue if ev and revenue and revenue != 0 else None)

        # ── Forward EPS & P/E from earnings_trend "+1y" ───────────────────────
        # Yahoo Finance definition: Forward P/E = price / next-fiscal-year analyst EPS.
        # yahooquery exposes this via earnings_trend[period="+1y"].earningsEstimate.avg
        fwd_eps = None
        fwd_pe  = None
        peg     = None
        try:
            trend_raw = t.earnings_trend
            # yahooquery returns {ticker: {trend: [...]}} or DataFrame depending on version
            if isinstance(trend_raw, dict):
                rows = (trend_raw.get(ticker) or {}).get("trend") or []
            else:
                rows = []
            for row in rows:
                period = str(row.get("period", "")).strip()
                if period == "+1y":
                    fwd_eps = _sf((row.get("earningsEstimate") or {}).get("avg"))
                    break
            # PEG: fwdPE / 5-yr growth rate
            for row in rows:
                if str(row.get("period", "")).strip() == "+5y":
                    gr = _sf(row.get("growth"))
                    if gr and gr > 0:
                        gr_pct = gr * 100 if abs(gr) <= 1 else gr
                        if fwd_eps and fwd_eps > 0 and live_price and gr_pct > 0:
                            peg = (live_price / fwd_eps) / gr_pct
                    break
        except Exception as _e:
            print(f"[yq earnings_trend] {ticker}: {_e}")

        if fwd_eps is not None and fwd_eps > 0 and live_price:
            fwd_pe = live_price / fwd_eps

        return {
            "symbol":   ticker.upper(),
            "longName": pr.get("longName") or pr.get("shortName") or "",
            "sector":   ap.get("sector", ""),
            "industry": ap.get("industry", ""),
            "longBusinessSummary": ap.get("longBusinessDescription", ""),
            "website":  ap.get("website", ""),
            "country":  ap.get("country", ""),
            "fullTimeEmployees": _sf(ap.get("fullTimeEmployees")),
            "currentPrice":  live_price,
            "previousClose": _g(pr, "regularMarketPreviousClose"),
            "open":          _g(pr, "regularMarketOpen"),
            "dayHigh":       _g(pr, "regularMarketDayHigh"),
            "dayLow":        _g(pr, "regularMarketDayLow"),
            "volume":        _g(pr, "regularMarketVolume"),
            "marketCap":     mkt_cap,
            "beta":          _g(sd, "beta"),
            "fiftyTwoWeekHigh": _g(sd, "fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow":  _g(sd, "fiftyTwoWeekLow"),
            # Valuation
            "trailingPE":   _g(sd, "trailingPE"),
            "forwardPE":    fwd_pe,          # price ÷ +1y analyst EPS
            "pegRatio":     peg,
            "priceToSalesTrailing12Months": _g(sd, "priceToSalesTrailing12Months"),
            "priceToBook":  _g(ks, "priceToBook"),
            "enterpriseToEbitda":  ev_ebitda,
            "enterpriseToRevenue": ev_revenue,
            "enterpriseValue":     ev,
            # EPS
            "trailingEps":  _g(ks, "trailingEps"),
            "forwardEps":   fwd_eps,         # +1y analyst consensus
            # Analyst target
            "targetMeanPrice": _g(fd, "targetMeanPrice"),
            # Profitability
            "profitMargins":    _g(fd, "profitMargins"),
            "operatingMargins": _g(fd, "operatingMargins"),
            "grossMargins":     _g(fd, "grossMargins"),
            "returnOnEquity":   _g(fd, "returnOnEquity"),
            "returnOnAssets":   _g(fd, "returnOnAssets"),
            # Balance sheet
            "totalDebt":    total_debt,
            "totalCash":    total_cash,
            "debtToEquity": _g(fd, "debtToEquity"),
            "quickRatio":   _g(fd, "quickRatio"),
            "currentRatio": _g(fd, "currentRatio"),
            "bookValue":    _g(ks, "bookValue"),
            # Cash flows
            "freeCashflow":      _g(fd, "freeCashflow"),
            "operatingCashflow": _g(fd, "operatingCashflow"),
            # Income
            "totalRevenue":      revenue,
            "ebitda":            ebitda,
            "netIncomeToCommon": _g(ks, "netIncomeToCommon"),
            # Growth
            "revenueGrowth":          _g(fd, "revenueGrowth"),
            "earningsGrowth":         _g(fd, "earningsGrowth"),
            "quarterlyRevenueGrowth": _g(fd, "revenueGrowth"),
            "revenuePerShare":        _g(fd, "revenuePerShare"),
            "sharesOutstanding":      _g(ks, "sharesOutstanding"),
            "_source": "yahooquery",
        }
    except Exception as exc:
        print(f"[yq fundamentals error] {ticker}: {exc}")
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def _yf_fundamentals(ticker: str) -> dict:
    """
    SECONDARY fundamentals source — yfinance.
    ─────────────────────────────────────────────────────────────────────────
    CRITICAL: Forward EPS uses ticker.earnings_estimate.loc["+1y"]["avg"]
    — NOT info["forwardEps"], which is unreliable and often represents the
    wrong forecast year (e.g. Tesla: info["forwardEps"] ≈ 2.81 → P/E ≈ 145,
    but Yahoo Finance uses +1y avg ≈ 2.0 → P/E ≈ 200).
    ─────────────────────────────────────────────────────────────────────────
    Returns {} on failure.
    """
    if not _YF_AVAILABLE:
        return {}
    try:
        t    = yf.Ticker(ticker)
        info = t.info or {}
        if not info:
            return {}

        price      = _sf(info.get("currentPrice") or info.get("regularMarketPrice"))
        mkt_cap    = _sf(info.get("marketCap"))
        total_debt = _sf(info.get("totalDebt"))
        total_cash = _sf(info.get("totalCash"))
        ebitda     = _sf(info.get("ebitda"))
        revenue    = _sf(info.get("totalRevenue"))

        # EV explicitly computed (marketCap + debt − cash)
        ev = None
        if mkt_cap is not None:
            ev = mkt_cap + (total_debt or 0) - (total_cash or 0)
        ev_ebitda  = (ev / ebitda  if ev and ebitda  and ebitda  != 0 else None)
        ev_revenue = (ev / revenue if ev and revenue and revenue != 0 else None)

        # ── Forward EPS: use earnings_estimate "+1y" — correct Yahoo Finance method
        # Do NOT use info["forwardEps"] — it frequently contains the wrong year.
        fwd_eps = None
        fwd_pe  = None
        try:
            est = t.earnings_estimate
            if est is not None and not getattr(est, "empty", True):
                if "+1y" in est.index:
                    fwd_eps = _sf(est.loc["+1y"].get("avg"))
        except Exception as _ee:
            print(f"[yf earnings_estimate] {ticker}: {_ee}")

        if fwd_eps is not None and fwd_eps > 0 and price:
            fwd_pe = price / fwd_eps

        return {
            "symbol":   info.get("symbol") or ticker.upper(),
            "longName": info.get("longName") or info.get("shortName") or "",
            "sector":   info.get("sector", ""),
            "industry": info.get("industry", ""),
            "longBusinessSummary": info.get("longBusinessSummary", ""),
            "website":  info.get("website", ""),
            "country":  info.get("country", ""),
            "fullTimeEmployees": _sf(info.get("fullTimeEmployees")),
            "currentPrice":  price,
            "previousClose": _sf(info.get("previousClose") or info.get("regularMarketPreviousClose")),
            "open":          _sf(info.get("open") or info.get("regularMarketOpen")),
            "dayHigh":       _sf(info.get("dayHigh") or info.get("regularMarketDayHigh")),
            "dayLow":        _sf(info.get("dayLow")  or info.get("regularMarketDayLow")),
            "volume":        _sf(info.get("volume")  or info.get("regularMarketVolume")),
            "marketCap":     mkt_cap,
            "beta":          _sf(info.get("beta")),
            "fiftyTwoWeekHigh": _sf(info.get("fiftyTwoWeekHigh")),
            "fiftyTwoWeekLow":  _sf(info.get("fiftyTwoWeekLow")),
            # Valuation — forwardPE derived from +1y analyst consensus
            "trailingPE":   _sf(info.get("trailingPE")),
            "forwardPE":    fwd_pe,
            "pegRatio":     _sf(info.get("pegRatio")),
            "priceToSalesTrailing12Months": _sf(info.get("priceToSalesTrailing12Months")),
            "priceToBook":  _sf(info.get("priceToBook")),
            "enterpriseToEbitda":  ev_ebitda,
            "enterpriseToRevenue": ev_revenue,
            "enterpriseValue":     ev,
            # EPS — trailingEps from info is fine; forwardEps is the corrected +1y value
            "trailingEps":  _sf(info.get("trailingEps")),
            "forwardEps":   fwd_eps,
            "targetMeanPrice": _sf(info.get("targetMeanPrice")),
            "profitMargins":    _sf(info.get("profitMargins")),
            "operatingMargins": _sf(info.get("operatingMargins")),
            "grossMargins":     _sf(info.get("grossMargins")),
            "returnOnEquity":   _sf(info.get("returnOnEquity")),
            "returnOnAssets":   _sf(info.get("returnOnAssets")),
            "totalDebt":    total_debt,
            "totalCash":    total_cash,
            "debtToEquity": _sf(info.get("debtToEquity")),
            "quickRatio":   _sf(info.get("quickRatio")),
            "currentRatio": _sf(info.get("currentRatio")),
            "bookValue":    _sf(info.get("bookValue")),
            "freeCashflow":      _sf(info.get("freeCashflow")),
            "operatingCashflow": _sf(info.get("operatingCashflow")),
            "totalRevenue":    revenue,
            "ebitda":          ebitda,
            "netIncomeToCommon": _sf(info.get("netIncomeToCommon")),
            "revenuePerShare":   _sf(info.get("revenuePerShare")),
            "revenueGrowth":     _sf(info.get("revenueGrowth")),
            "earningsGrowth":    _sf(info.get("earningsGrowth")),
            "quarterlyRevenueGrowth": _sf(info.get("revenueGrowth")),
            "sharesOutstanding": _sf(info.get("sharesOutstanding")),
            "_source": "Yahoo Finance",
        }
    except Exception as exc:
        print(f"[yf fundamentals error] {ticker}: {exc}")
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def _yfin_fundamentals(ticker: str) -> dict:
    """
    LAST-RESORT fundamentals source — yahoo_fin.
    Returns a sparse dict with only the fields yahoo_fin provides.
    Returns {} if yahoo_fin is unavailable or fails.
    """
    if not _YFIN_AVAILABLE:
        return {}
    try:
        stats = _yf_fin.get_stats_valuation(ticker)
        quote = _yf_fin.get_quote_table(ticker)

        def _gs(label: str) -> float | None:
            try:
                row = stats[stats.iloc[:, 0].str.contains(label, case=False, na=False)]
                return _sf(row.iloc[0, 1]) if not row.empty else None
            except Exception:
                return None

        def _gq(key: str) -> float | None:
            try: return _sf(quote.get(key))
            except: return None

        return {
            "currentPrice":  _gq("Quote Price"),
            "trailingPE":    _gs("Trailing P/E"),
            "priceToBook":   _gs("Price/Book"),
            "priceToSalesTrailing12Months": _gs("Price/Sales"),
            "enterpriseToEbitda": _gs("Enterprise Value/EBITDA"),
            "enterpriseToRevenue": _gs("Enterprise Value/Revenue"),
            "pegRatio":      _gs("PEG Ratio"),
            "_source": "yahoo_fin",
        }
    except Exception as exc:
        print(f"[yahoo_fin fundamentals error] {ticker}: {exc}")
        return {}


def _merge_dicts(*dicts: dict) -> dict:
    """
    Merge fundamentals dicts left-to-right: first non-None value wins.
    yahooquery → yfinance → yahoo_fin → FMP profile extras.
    This means the best/most-reliable source for each field always prevails.
    """
    all_keys: set = set()
    for d in dicts:
        all_keys.update(d.keys())
    result: dict = {}
    for key in all_keys:
        for d in dicts:
            val = d.get(key)
            if val is not None:
                result[key] = val
                break
        else:
            result[key] = None
    return result


# ─── yfinance normaliser (used only when FMP profile is fully blocked) ────────
def _yf_info_to_dict(info: dict) -> dict:
    """
    Full yfinance .info → standard schema normaliser.
    Used as emergency fallback when FMP profile call is blocked.
    Forward P/E here falls back to info["forwardPE"] since we don't have
    a separate earnings_estimate call in this emergency path.
    """
    return {
        "symbol":   info.get("symbol"),
        "longName": info.get("longName") or info.get("shortName"),
        "sector":   info.get("sector"),
        "industry": info.get("industry"),
        "longBusinessSummary": info.get("longBusinessSummary", ""),
        "website":  info.get("website", ""),
        "country":  info.get("country", ""),
        "fullTimeEmployees": _sf(info.get("fullTimeEmployees")),
        "currentPrice":  _sf(info.get("currentPrice") or info.get("regularMarketPrice")),
        "previousClose": _sf(info.get("previousClose") or info.get("regularMarketPreviousClose")),
        "open":          _sf(info.get("open") or info.get("regularMarketOpen")),
        "dayHigh":       _sf(info.get("dayHigh") or info.get("regularMarketDayHigh")),
        "dayLow":        _sf(info.get("dayLow")  or info.get("regularMarketDayLow")),
        "volume":        _sf(info.get("volume")  or info.get("regularMarketVolume")),
        "marketCap":     _sf(info.get("marketCap")),
        "beta":          _sf(info.get("beta")),
        "fiftyTwoWeekHigh": _sf(info.get("fiftyTwoWeekHigh")),
        "fiftyTwoWeekLow":  _sf(info.get("fiftyTwoWeekLow")),
        "trailingPE":    _sf(info.get("trailingPE")),
        "forwardPE":     _sf(info.get("forwardPE")),
        "pegRatio":      _sf(info.get("pegRatio")),
        "priceToSalesTrailing12Months": _sf(info.get("priceToSalesTrailing12Months")),
        "priceToBook":   _sf(info.get("priceToBook")),
        "enterpriseToEbitda":  _sf(info.get("enterpriseToEbitda")),
        "enterpriseToRevenue": _sf(info.get("enterpriseToRevenue")),
        "trailingEps":     _sf(info.get("trailingEps")),
        "forwardEps":      _sf(info.get("forwardEps")),
        "targetMeanPrice": _sf(info.get("targetMeanPrice")),
        "profitMargins":    _sf(info.get("profitMargins")),
        "operatingMargins": _sf(info.get("operatingMargins")),
        "grossMargins":     _sf(info.get("grossMargins")),
        "returnOnEquity":   _sf(info.get("returnOnEquity")),
        "returnOnAssets":   _sf(info.get("returnOnAssets")),
        "totalDebt":    _sf(info.get("totalDebt")),
        "totalCash":    _sf(info.get("totalCash")),
        "debtToEquity": _sf(info.get("debtToEquity")),
        "quickRatio":   _sf(info.get("quickRatio")),
        "currentRatio": _sf(info.get("currentRatio")),
        "bookValue":    _sf(info.get("bookValue")),
        "freeCashflow":      _sf(info.get("freeCashflow")),
        "operatingCashflow": _sf(info.get("operatingCashflow")),
        "totalRevenue":    _sf(info.get("totalRevenue")),
        "ebitda":          _sf(info.get("ebitda")),
        "netIncomeToCommon": _sf(info.get("netIncomeToCommon")),
        "revenuePerShare": _sf(info.get("revenuePerShare")),
        "revenueGrowth":   _sf(info.get("revenueGrowth")),
        "earningsGrowth":  _sf(info.get("earningsGrowth")),
        "quarterlyRevenueGrowth": _sf(info.get("revenueGrowth")),
        "sharesOutstanding": _sf(info.get("sharesOutstanding")),
        "_source": "Yahoo Finance (emergency fallback)",
    }


# ── Stock info — hybrid multi-source engine ────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_stock_info(ticker: str) -> dict:
    """
    Fetch full company fundamentals using the hybrid multi-source engine.

    Source priority for fundamentals:
      1. yahooquery  — primary (richer, reliable analyst EPS estimates)
      2. yfinance    — secondary (broad coverage, earnings_estimate +1y for fwd P/E)
      3. yahoo_fin   — tertiary sparse fallback (basic valuation ratios only)

    Forward P/E calculation (both yq and yf paths):
      price / earnings_estimate "+1y" avg  — matches Yahoo Finance exactly.
      info["forwardEps"] is intentionally NOT used (wrong year bias).

    FMP is used only for:
      - Gating call to confirm ticker validity (/profile)
      - Real-time price / volume / day range (/quote) — overrides stale yq/yf price
      - OHLCV history (get_stock_history)
    """
    ticker = ticker.upper().strip()

    # ── Step 1: FMP profile gating call ──────────────────────────────────────
    profile_data = _fmp_get(f"/profile/{ticker}", _ui_errors=True)

    if profile_data is _FMP_BLOCKED:
        # FMP fully blocked — use full hybrid stack
        print(f"[Hybrid] {ticker}: FMP blocked, using yq → yf → yfin")
        st.info(f"ℹ️ Using multi-source data engine for {ticker}", icon="ℹ️")
        yq   = _yq_fundamentals(ticker)
        yf_  = _yf_fundamentals(ticker)
        yfin = _yfin_fundamentals(ticker)
        merged = _merge_dicts(yq, yf_, yfin)
        if not merged.get("currentPrice"):
            st.error(f"❌ Could not fetch data for **{ticker}** from any source.")
            return {}
        return merged

    if not profile_data or not isinstance(profile_data, list):
        st.error(
            f"❌ Could not fetch profile for **{ticker}**. "
            "Verify the ticker symbol is correct and listed on a major exchange."
        )
        return {}
    p = profile_data[0]

    # ── Step 2: FMP real-time quote (freshest available price/volume) ─────────
    qt: dict = {}
    qt_data = _fmp_get(f"/quote/{ticker}")
    if qt_data and qt_data is not _FMP_BLOCKED and isinstance(qt_data, list):
        qt = qt_data[0]

    live_price = _sf(qt.get("price")) or _sf(p.get("price"))
    prev_close = _sf(qt.get("previousClose")) or live_price
    wk52_high  = _sf(qt.get("yearHigh"))
    wk52_low   = _sf(qt.get("yearLow"))
    if not wk52_high:
        raw_range = p.get("range", "") or ""
        if "-" in raw_range:
            parts = raw_range.split("-")
            try:
                wk52_low  = float(parts[0])
                wk52_high = float(parts[-1])
            except (ValueError, IndexError):
                pass

    # ── Step 3: Fundamentals from hybrid engine ───────────────────────────────
    # yahooquery wins on all shared fields; yfinance fills gaps; yahoo_fin patches rest
    yq   = _yq_fundamentals(ticker)
    yf_  = _yf_fundamentals(ticker)
    yfin = _yfin_fundamentals(ticker)
    hyb  = _merge_dicts(yq, yf_, yfin)

    # ── Step 4: Override price/market fields with fresh FMP quote data ────────
    # FMP /quote is real-time; fundamental sources cache at 3600s
    if live_price:
        hyb["currentPrice"]  = live_price
        hyb["previousClose"] = prev_close
        hyb["open"]    = _sf(qt.get("open"))    or live_price
        hyb["dayHigh"] = _sf(qt.get("dayHigh")) or hyb.get("dayHigh") or live_price
        hyb["dayLow"]  = _sf(qt.get("dayLow"))  or hyb.get("dayLow")  or live_price
        hyb["volume"]  = _sf(qt.get("volume"))  or hyb.get("volume")
        hyb["marketCap"] = _sf(qt.get("marketCap")) or hyb.get("marketCap")

    # ── Step 5: Fill profile-only fields if hybrid missed them ────────────────
    if not hyb.get("longName"):   hyb["longName"]   = p.get("companyName", "")
    if not hyb.get("sector"):     hyb["sector"]     = p.get("sector", "")
    if not hyb.get("industry"):   hyb["industry"]   = p.get("industry", "")
    if not hyb.get("country"):    hyb["country"]    = p.get("country", "")
    if not hyb.get("website"):    hyb["website"]    = p.get("website", "")
    if not hyb.get("beta"):       hyb["beta"]       = _sf(p.get("beta"))
    hyb["longBusinessSummary"] = (hyb.get("longBusinessSummary")
                                  or p.get("description", ""))
    if not hyb.get("fiftyTwoWeekHigh"): hyb["fiftyTwoWeekHigh"] = wk52_high
    if not hyb.get("fiftyTwoWeekLow"):  hyb["fiftyTwoWeekLow"]  = wk52_low

    hyb["_source"] = f"Hybrid (yq+yf+yfin, FMP quote)"
    return hyb
# ── OHLCV history ─────────────────────────────────────────────────────────────
def _yf_history(ticker: str, period: str, interval: str) -> "pd.DataFrame":
    """Fetch OHLCV from Yahoo Finance and normalise to the same shape as FMP."""
    empty = pd.DataFrame()
    try:
        # Map app period/interval codes → yfinance equivalents
        yf_period_map = {
            "1d":"1d","5d":"5d","1mo":"1mo","3mo":"3mo",
            "6mo":"6mo","1y":"1y","2y":"2y","5y":"5y",
        }
        yf_interval_map = {
            "5m":"5m","15m":"15m","30m":"30m","1h":"1h",
            "1d":"1d","1wk":"1wk",
        }
        yp = yf_period_map.get(period, "1y")
        yi = yf_interval_map.get(interval, "1d")
        df = yf.Ticker(ticker).history(period=yp, interval=yi)
        if df.empty:
            return empty
        # yfinance columns: Open High Low Close Volume
        df = df[["Open","High","Low","Close","Volume"]].copy()
        df.index = pd.to_datetime(df.index)
        # Strip timezone so Arrow serialisation never trips
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        df.index.name = "Date"
        return df.dropna()
    except Exception as exc:
        print(f"[yf history error] {ticker}: {exc}")
        return empty

@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_history(ticker: str, period: str, interval: str) -> "pd.DataFrame":
    """
    Fetch OHLCV. FMP is primary; yfinance is the automatic silent fallback
    when FMP returns a 403 or plan/legacy error.

    FMP paths:
      Intraday  → /historical-chart/{interval}/{ticker}
      Daily/wk  → /historical-price-full/{ticker}

    Yahoo Finance fallback:
      yf.Ticker(ticker).history(period, interval)
    """
    empty = pd.DataFrame()

    # ── Intraday ──────────────────────────────────────────────────────────────
    if interval in ("5m","15m","30m","1h"):
        data = _fmp_get(f"/historical-chart/{interval}/{ticker}")
        if data is _FMP_BLOCKED:
            print(f"[Fallback] history intraday {ticker} → Yahoo Finance")
            st.info(f"ℹ️ Using backup data source for {ticker}", icon="ℹ️")
            return _yf_history(ticker, period, interval)
        if not data or not isinstance(data, list):
            return empty
        df = (pd.DataFrame(data)
              .rename(columns={"date":"Date","open":"Open","high":"High",
                                "low":"Low","close":"Close","volume":"Volume"}))
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        cutoff = {"1d": 1, "5d": 5}.get(period, 1)
        df = df[df.index >= df.index[-1] - pd.Timedelta(days=cutoff)]
        return df[["Open","High","Low","Close","Volume"]].dropna()

    # ── Daily / weekly ────────────────────────────────────────────────────────
    period_days = {"1mo":31,"3mo":92,"6mo":183,"1y":365,"2y":730,"5y":1825}
    days = period_days.get(period, 365)
    from_date = (datetime.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")

    data = _fmp_get(f"/historical-price-full/{ticker}", {"from": from_date})
    if data is _FMP_BLOCKED:
        print(f"[Fallback] history daily {ticker} → Yahoo Finance")
        st.info(f"ℹ️ Using backup data source for {ticker}", icon="ℹ️")
        return _yf_history(ticker, period, interval)

    if not data or not isinstance(data, dict):
        return empty
    hist_list = data.get("historical", [])
    if not hist_list:
        return empty

    df = (pd.DataFrame(hist_list)
          .rename(columns={"date":"Date","open":"Open","high":"High",
                            "low":"Low","close":"Close","volume":"Volume"}))
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()

    if interval == "1wk":
        df = df.resample("W").agg(
            {"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}
        ).dropna()

    return df[["Open","High","Low","Close","Volume"]].dropna()
@st.cache_data(ttl=300, show_spinner=False)
def _fmp_quote_batch(tickers: tuple) -> dict[str, dict]:
    """
    Fetch real-time quotes for one or more tickers.
    FMP /quote/{symbols} is primary (single batch call).
    If FMP is blocked (403 / plan error), yfinance is used per-ticker silently.
    Returns {TICKER: quote_dict} where quote_dict contains at minimum
    "price" and "changesPercentage" keys.
    """
    if not tickers:
        return {}

    # ── Try FMP batch first ───────────────────────────────────────────────────
    if FMP_API_KEY:
        symbols = ",".join(tickers)
        data = _fmp_get(f"/quote/{symbols}")
        if data is not _FMP_BLOCKED and data and isinstance(data, list):
            return {item["symbol"]: item for item in data if "symbol" in item}
        if data is _FMP_BLOCKED:
            print(f"[Fallback] _fmp_quote_batch → Yahoo Finance for {tickers}")

    # ── Yahoo Finance fallback (per-ticker) ───────────────────────────────────
    result: dict[str, dict] = {}
    for sym in tickers:
        try:
            t = yf.Ticker(sym)
            info = t.fast_info          # fast_info avoids full .info round-trip
            price  = float(getattr(info, "last_price", None) or 0)
            prev   = float(getattr(info, "previous_close", None) or price or 1)
            chg_pct = ((price - prev) / prev * 100) if prev else 0.0
            result[sym] = {
                "symbol":            sym,
                "price":             price,
                "changesPercentage": chg_pct,
                "marketCap":         float(getattr(info, "market_cap", None) or 0),
                "_source":           "Yahoo Finance",
            }
        except Exception as exc:
            print(f"[yf quote error] {sym}: {exc}")
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def get_spy_benchmark(period: str = "1y") -> float:
    """Return SPY cumulative % return over the given period using FMP history."""
    try:
        hist = get_stock_history("SPY", period, "1d")
        if hist.empty or len(hist) < 2:
            return 0.0
        return ((hist["Close"].iloc[-1] / hist["Close"].iloc[0]) - 1) * 100
    except:
        return 0.0

@st.cache_data(ttl=1800, show_spinner=False)
def get_earnings_date(ticker: str, fmp_api_key: str = "") -> dict | None:
    """
    Fetch the next upcoming earnings date for `ticker` from FMP v3.

    Both strategies now route through _fmp_get so the "Error Message" guard
    is always active — no raw requests.get calls.

    Strategy 1: /earning_calendar?from=...&to=...
        Date-range calendar across all tickers; filter by symbol.
        Covers the next 90 days and is the most reliable source.

    Strategy 2: /earning_calendar/{ticker}
        Per-ticker endpoint (non-legacy v3). Used when strategy 1 returns
        nothing for this ticker (e.g. event just outside the 90-day window).
        Replaces the old /historical/earning_calendar/{ticker} which is
        legacy-blocked for accounts created after Aug 31 2025.

    Returns None if no upcoming event is found within 120 days.
    """
    if not FMP_API_KEY:
        return None
    today = datetime.now().date()

    def _parse(item: dict) -> dict | None:
        """Parse one earnings-calendar item; return result dict or None."""
        edate_str = item.get("date", "")
        if not edate_str:
            return None
        try:
            edate = datetime.strptime(edate_str[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
        days_away = (edate - today).days
        if days_away < 0:
            return None
        return {
            "date":        edate.strftime("%b %d, %Y"),
            "date_raw":    edate_str[:10],
            "days_away":   days_away,
            "is_soon":     days_away <= 14,
            "is_imminent": days_away <= 3,
            "eps_estimate": item.get("epsEstimated"),
            "time_of_day":  item.get("time", "Unknown") or "Unknown",
            "source": "FMP",
        }

    # ── Strategy 1: date-range earnings calendar ──────────────────────────────
    try:
        from_d = today.strftime("%Y-%m-%d")
        to_d   = (today + pd.Timedelta(days=90)).strftime("%Y-%m-%d")
        cal = _fmp_get("/earning_calendar", {"from": from_d, "to": to_d})
        if isinstance(cal, list):
            for item in cal:
                if str(item.get("symbol", "")).upper() == ticker.upper():
                    result = _parse(item)
                    if result:
                        return result
    except Exception:
        pass

    # ── Strategy 2: per-ticker earnings calendar  ─────────────────────────────
    # /earning_calendar/{ticker} — confirmed non-legacy v3 endpoint.
    # Replaces deprecated /historical/earning_calendar/{ticker}.
    try:
        per_ticker = _fmp_get(f"/earning_calendar/{ticker}")
        if isinstance(per_ticker, list):
            for item in sorted(per_ticker, key=lambda x: x.get("date", "")):
                result = _parse(item)
                if result and result["days_away"] <= 120:
                    return result
    except Exception:
        pass

    return None

# ── Formatting ────────────────────────────────────────────────────────────────
def fmt(val, t="number"):
    if val is None: return "N/A"
    try:
        if pd.isna(val): return "N/A"
    except: pass
    try:
        if t=="percent": return f"{float(val)*100:.2f}%"
        if t=="money":
            v = abs(float(val))
            if v>=1e12: return f"${float(val)/1e12:.2f}T"
            if v>=1e9:  return f"${float(val)/1e9:.2f}B"
            if v>=1e6:  return f"${float(val)/1e6:.2f}M"
            return f"${float(val):,.2f}"
        return f"{float(val):.2f}"
    except: return "N/A"

# ── Technical indicators ──────────────────────────────────────────────────────
def calc_rsi_macd_bb(hist):
    """
    Technical indicators.  RSI uses Wilder's Smoothing (EWM alpha=1/14) which
    matches Yahoo Finance and TradingView exactly.  Requires at least 200 rows
    of history for the warm-up period — always pass a 1-year (or longer) frame.
    """
    try:
        c = hist["Close"]
        # ── RSI — Wilder's Smoothing (alpha = 1/14, adjust=False) ────────────
        # This is the correct formula; simple rolling(14).mean() diverges when
        # fewer than ~100 bars are available and gives wrong values (e.g. 53 vs 41).
        d    = c.diff()
        gain = d.where(d > 0, 0.0)
        loss = (-d.where(d < 0, 0.0))
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs  = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))
        # ── MACD ─────────────────────────────────────────────────────────────
        e1   = c.ewm(span=12, adjust=False).mean()
        e2   = c.ewm(span=26, adjust=False).mean()
        macd = e1 - e2
        sig  = macd.ewm(span=9, adjust=False).mean()
        # ── Bollinger Bands ───────────────────────────────────────────────────
        s20   = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        return {
            "rsi":       rsi.iloc[-1],
            "macd":      macd.iloc[-1],
            "signal":    sig.iloc[-1],
            "bb_upper":  (s20 + std20 * 2).iloc[-1],
            "bb_lower":  (s20 - std20 * 2).iloc[-1],
            "sma_20":    s20.iloc[-1],
            "sma_50":    c.rolling(50).mean().iloc[-1],
            "sma_200":   c.rolling(200).mean().iloc[-1],
        }
    except:
        return None

def calc_atr(hist, period=14):
    try:
        h=hist["High"]; l=hist["Low"]; c=hist["Close"].shift(1)
        tr=pd.concat([h-l,(h-c).abs(),(l-c).abs()],axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])
    except: return None

def calc_pos_size(account, risk_pct, atr, price, mult=2.0):
    try:
        rd=account*risk_pct; sd=atr*mult
        return max(1,int(rd/sd)), price-sd, sd
    except: return None,None,None

def quality_score(roe, margin):
    if roe is None or margin is None: return 0,"N/A","⚪"
    r=float(roe)*100; m=float(margin)*100
    s=(5 if r>25 else 4 if r>15 else 3 if r>10 else 1)+(5 if m>20 else 3 if m>10 else 1)
    if s>=8: return s,f"Exceptional (ROE:{r:.1f}%, Margin:{m:.1f}%)","🟢"
    if s>=6: return s,f"Strong (ROE:{r:.1f}%, Margin:{m:.1f}%)","🟡"
    return s,f"Weak (ROE:{r:.1f}%, Margin:{m:.1f}%)","🔴"

def calc_fair_value(info, hist, dg=0.20, dw=0.10):
    """
    Conservative fair-value model v8.
    Key guardrails:
      • DCF terminal growth rate capped at 4% (was uncapped)
      • P/E multiple capped: mega-caps ($1T+) Bull ≤ 35x, others ≤ 40x
      • Analyst consensus guardrail: if model deviates >20% from analyst
        target, the blend is pulled 50% toward analyst target
      • Bull/Bear cases are anchored to P/E ranges, not uncapped growth
      • Returns 'method' metadata for UI transparency caption
    """
    try:
        cp   = float(hist["Close"].iloc[-1])
        eps  = float(info.get("forwardEps") or info.get("trailingEps") or 1.0)
        rg   = float(info.get("revenueGrowth")  or 0.12)
        eg   = float(info.get("earningsGrowth") or rg)
        pm   = float(info.get("profitMargins")  or 0.10)
        roe  = float(info.get("returnOnEquity") or 0.15)
        mc   = float(info.get("marketCap")      or cp * 1e9)
        fcf  = info.get("freeCashflow")
        shr  = info.get("sharesOutstanding")
        at   = float(info.get("targetMeanPrice") or 0) or None   # None if missing
        r40  = (rg * 100) + (pm * 100)

        # ── 1. P/E MODEL — capped multiples ──────────────────────────────────
        is_megacap = mc >= 1e12
        # Base multiple: use sector-adjusted PEG heuristic, but hard-cap it
        raw_mult   = max(10.0, min(eg * 100 * 1.5, 80.0))
        pe_cap     = 35.0 if is_megacap else 40.0
        pe_mult    = min(raw_mult, pe_cap)
        m_pe       = eps * pe_mult                              # P/E-anchored value

        # ── 2. FCF YIELD MODEL ────────────────────────────────────────────────
        if fcf and mc > 0 and float(fcf) > 0:
            fcf_yield = float(fcf) / mc                        # FCF/market cap
            # Implied fair value: FCF / (required_yield); req_yield = WACC - growth
            req_yield  = max(0.03, dw - rg * 0.25)
            m_fcf      = (float(fcf) / req_yield) / (mc / cp)  # per-share
        else:
            m_fcf = m_pe

        # ── 3. CONSERVATIVE DCF — terminal growth CAPPED at 4% ───────────────
        tg_cap = 0.04                                           # hard cap
        tg     = min(max(0.02, rg * 0.3), tg_cap)
        gr_5y  = min(dg, 0.30)                                  # cap 5-yr growth at 30%
        dcfv   = None
        if fcf and shr and float(fcf) > 0 and float(shr) > 0:
            try:
                cfs  = [float(fcf) * (1 + gr_5y) ** i for i in range(1, 6)]
                pv   = sum(cf / (1 + dw) ** i for i, cf in enumerate(cfs, 1))
                wacc_tg = dw - tg
                if wacc_tg > 0.001:
                    tv   = cfs[-1] * (1 + tg) / wacc_tg
                    dcfv = (pv + tv / (1 + dw) ** 5) / float(shr)
            except: pass

        # ── 4. DCF SANITY CHECK ───────────────────────────────────────────────
        # If the DCF intrinsic value is more than 70% below the current market
        # price it is almost certainly an artefact of negative/tiny FCF
        # (e.g. Amazon heavy-capex years, high-growth names with minimal FCF).
        # In such cases we treat DCF as an outlier and exclude it from the
        # blend entirely, using only the P/E model and analyst target instead.
        dcf_outlier = False
        if dcfv and cp > 0:
            dcf_discount = (cp - dcfv) / cp   # positive = DCF below market
            if dcf_discount > 0.70:           # DCF is >70% below market price
                dcf_outlier = True
                dcfv_blend  = None            # excluded from blend
                print(f"[fair_value] DCF outlier detected: dcfv={dcfv:.2f}, "
                      f"cp={cp:.2f}, discount={dcf_discount:.1%} — excluded from blend")
            else:
                dcfv_blend = dcfv
        else:
            dcfv_blend = dcfv

        # ── 5. BLEND ──────────────────────────────────────────────────────────
        if dcfv_blend:
            raw_fv = m_pe * 0.35 + m_fcf * 0.25 + dcfv_blend * 0.25 + (at or m_pe) * 0.15
        else:
            # DCF absent or outlier → weight entirely on P/E and analyst target
            raw_fv = m_pe * 0.45 + m_fcf * 0.25 + (at or m_pe) * 0.30

        # Quality premium: modest, capped at 8%
        qm     = 1.08 if roe > 0.40 else 1.04 if roe > 0.25 else 1.0
        raw_fv = raw_fv * qm

        # ── 6. ANALYST GUARDRAIL ─────────────────────────────────────────────
        analyst_adj = False
        if at and at > 0:
            dev = (raw_fv - at) / at          # positive = model higher than analyst
            if abs(dev) > 0.20:
                # Pull 50% toward analyst consensus
                raw_fv      = raw_fv * 0.50 + at * 0.50
                analyst_adj = True

        fv = raw_fv

        # ── 7. BULL / BEAR — P/E anchored, capped ────────────────────────────
        # Bull: apply a modest multiple expansion (max +15% above fair value, or analyst target)
        bull_pe_mult  = min(pe_mult * 1.15, pe_cap * 1.10)     # max 10% above cap
        bull_case     = max(eps * bull_pe_mult, fv * 1.10)
        bull_case     = min(bull_case, cp * 1.35)               # hard cap: +35% from price

        # Bear: mean-reversion to lower P/E or 200-SMA
        try:
            sma200    = float(hist["Close"].rolling(200).mean().iloc[-1])
        except:
            sma200    = None
        bear_pe_mult  = max(pe_mult * 0.75, 12.0)              # at least 12x
        bear_pe_val   = eps * bear_pe_mult
        bear_case     = bear_pe_val
        if sma200 and not pd.isna(sma200):
            bear_case = max(bear_pe_val, sma200 * 0.95)        # don't go below SMA200 * 0.95
        bear_case     = max(bear_case, cp * 0.75)              # floor: -25% from price
        bear_case     = min(bear_case, cp * 0.95)              # ceiling: at most -5%

        # ── 8. UPSIDE — relative to current price ────────────────────────────
        upside = ((fv / cp) - 1) * 100

        # ── 9. TRANSPARENCY METADATA ─────────────────────────────────────────
        method_parts = [
            f"{pe_mult:.0f}x Fwd P/E",
            f"{tg*100:.1f}% terminal growth",
        ]
        if analyst_adj:
            method_parts.append("analyst-adjusted (>20% deviation)")
        if is_megacap:
            method_parts.append("mega-cap P/E cap applied")
        if dcf_outlier:
            method_parts.append("DCF excluded (>70% below market — outlier)")
        method_str = " · ".join(method_parts)

        return {
            "fair_value":     fv,
            "peg_model":      m_pe,
            "fcf_model":      m_fcf,
            "dcf_model":      dcfv,      # raw DCF (may be outlier — check dcf_outlier flag)
            "dcf_outlier":    dcf_outlier,
            "analyst_target": at or 0.0,
            "upside":         upside,
            "bull_case":      bull_case,
            "bear_case":      bear_case,
            "rule_of_40":     r40,
            "pe_multiple":    pe_mult,
            "terminal_growth":tg * 100,
            "analyst_adj":    analyst_adj,
            "is_megacap":     is_megacap,
            "method":         method_str,
        }
    except: return None

# ── News ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)   # 15-min cache (was 30-min)
def get_news_sentiment(ticker: str, company_name: str = "") -> list[dict]:
    """
    Fetch news + AI sentiment scoring.
    v8: prioritises last 24-48 hours; flags articles < 12h old as 'breaking'.
    TTL=15 min so fresh news surfaces quickly.
    """
    arts: list[dict] = []
    now_utc = datetime.utcnow()

    if NEWS_API_KEY:
        try:
            q = f"{ticker} stock" if not company_name else f"{ticker} OR \"{company_name}\""
            # Ask for the very latest — sortBy publishedAt, from=48h ago
            from_ts = (now_utc - pd.Timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S")
            r = requests.get("https://newsapi.org/v2/everything",
                params={"q": q, "language": "en", "sortBy": "publishedAt",
                        "pageSize": 12, "from": from_ts,
                        "apiKey": NEWS_API_KEY}, timeout=8).json()
            if r.get("status") == "ok":
                for a in r.get("articles", [])[:10]:
                    pub_raw = a.get("publishedAt", "")
                    # Compute hours_ago for breaking flag
                    hours_ago = None
                    try:
                        pub_dt = datetime.strptime(pub_raw[:19], "%Y-%m-%dT%H:%M:%S")
                        hours_ago = (now_utc - pub_dt).total_seconds() / 3600
                    except: pass
                    arts.append({
                        "title":       a.get("title", ""),
                        "publisher":   a.get("source", {}).get("name", ""),
                        "link":        a.get("url", ""),
                        "published":   pub_raw[:10],
                        "hours_ago":   hours_ago,
                        "breaking":    hours_ago is not None and hours_ago < 12,
                    })
        except: pass

    # Fallback: FMP stock news (replaces yfinance.news — no rate-limit risk)
    if not arts:
        try:
            news_data = _fmp_get("/stock_news", {"tickers": ticker, "limit": 10})
            if news_data and isinstance(news_data, list):
                for item in news_data[:10]:
                    pub_raw   = item.get("publishedDate", "")
                    hours_ago = None
                    try:
                        pub_dt    = datetime.strptime(pub_raw[:19], "%Y-%m-%dT%H:%M:%S")
                        hours_ago = (now_utc - pub_dt).total_seconds() / 3600
                    except:
                        pass
                    arts.append({
                        "title":     item.get("title", "Market Update"),
                        "publisher": item.get("site", ""),
                        "link":      item.get("url", ""),
                        "published": pub_raw[:10],
                        "hours_ago": hours_ago,
                        "breaking":  hours_ago is not None and hours_ago < 12,
                    })
        except:
            pass

    # AI sentiment scoring
    enriched: list[dict] = []
    for a in arts:
        if llm is None:
            a["sentiment"] = "Neutral"; a["score"] = 0.5; a["reason"] = "AI unavailable (no GROQ_API_KEY)"
        else:
            try:
                _p = ('Return ONLY valid JSON (no markdown, no backticks): '
                      '{"sentiment":"Bullish|Bearish|Neutral","score":0.0-1.0,"reason":"one sentence"} '
                      'Headline: ' + repr(a.get("title","")))
                raw = llm.invoke(_p).content.strip().replace("```json","").replace("```","").strip()
                d = json.loads(raw); s = d.get("sentiment","Neutral")
                a["sentiment"] = s if s in ("Bullish","Bearish","Neutral") else "Neutral"
                a["score"]     = float(d.get("score",0.5))
                a["reason"]    = d.get("reason","")
            except:
                a["sentiment"] = "Neutral"; a["score"] = 0.5; a["reason"] = ""
        enriched.append(a)

    # Sort: breaking first, then by conviction
    enriched.sort(key=lambda x: (not x.get("breaking",False), -abs(x.get("score",0.5)-0.5)))
    return enriched

# ── Beta / correlation ────────────────────────────────────────────────────────
def compute_rolling_beta(hist, window=90):
    try:
        spy_hist = get_stock_history("SPY", "1y", "1d")
        if spy_hist.empty:
            return None
        spy = spy_hist["Close"].pct_change()
        stk = hist["Close"].pct_change()
        al  = pd.concat([stk.rename("s"), spy.rename("spy")], axis=1).dropna()
        if len(al) < window:
            return None
        return (al["s"].rolling(window).cov(al["spy"]) / al["spy"].rolling(window).var()).dropna()
    except:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def compute_peer_corr(ticker, peers, period="1y"):
    try:
        prices = {}
        for t in (ticker,) + tuple(peers):
            h = get_stock_history(t, period, "1d")
            if not h.empty:
                prices[t] = h["Close"]
        if len(prices) < 2:
            return None
        return pd.DataFrame(prices).pct_change().dropna().corr()
    except:
        return None

# =============================================================================
# AI AGENT — v8: Realistic Valuations + Breaking News + Earnings Context
# =============================================================================
AGENT_PROMPT = """You are a Senior Institutional Research Analyst. Today is {date}.

You have FOUR data sources. Synthesise ALL of them:

SOURCE 1 — LIVE FINANCIAL DATA (JSON):
{financial_data}

SOURCE 2 — RECENT NEWS (sorted: breaking first, then by conviction):
{news_data}

SOURCE 3 — EARNINGS CONTEXT:
{earnings_data}

SOURCE 4 — PREDICTION MARKETS (if available):
{prediction_data}

═══════════════════════════════════════════════════════
STRICT RULES — FOLLOW ALL OR THE ANALYSIS IS INVALID:
═══════════════════════════════════════════════════════

RULE 1 — SHOW YOUR MATH ON PRICE TARGETS:
  Every Bull and Bear price target MUST include its derivation formula inline.
  Required formats (pick the most appropriate):
    • "Bull: $XXX (Forward P/E of Yx on $Z EPS estimate)"
    • "Bull: $XXX (20% premium to DCF fair value of $Y)"
    • "Bear: $XXX (mean reversion to 200-day SMA of $Y, –Z%)"
    • "Bear: $XXX (P/E compression to sector average of Yx = $Z)"

RULE 2 — CONSERVATIVE CONSTRAINT:
  • If currentPrice / fiftyTwoWeekHigh > 0.95 (near all-time high):
      – Bull case MUST NOT exceed +25% from current price
      – Bear case MUST focus on mean reversion or multiple compression
  • Bull case max: +40% from current price (HARD CAP, no exceptions)
  • Bear case min: –10% from current price (minimum downside to show)
  • If you cannot justify a Bull case within these bounds using the data, say so explicitly.

RULE 3 — BREAKING NEWS PRIORITY:
  • If any headline has "breaking: true" in the news JSON, it MUST be called out
    as a "🚨 Breaking Factor" at the very top of Key Event Context.
  • The breaking headline's specific impact on Bull/Bear cases must be named.

RULE 4 — EARNINGS URGENCY:
  • If days_away <= 14: open with a ⚡ HIGH-VOLATILITY WARNING and state the date.
  • If days_away <= 3: open with a 🔴 IMMINENT EARNINGS ALERT.
  • State the expected move range (±ATR-based or ±implied from beta/vol).
  • Mention what the market is specifically watching (EPS estimate vs history).

RULE 5 — SYNTHESISED VERDICT:
  The final "Strategic Takeaway" must be ONE sentence combining:
  current price + earnings timing + most impactful news event + your net rating.

═══════════════════════════
OUTPUT FORMAT (markdown):
═══════════════════════════

## 🎯 Investment Rating: [STRONG BUY / BUY / HOLD / SELL / STRONG SELL]

## 📰 Key Event Context
[If breaking news exists: 🚨 Breaking: <headline summary — <X hours ago>]
[1-2 sentences on the primary catalyst. If none: "Thesis is fundamentals-driven."]

## ⚡ Earnings Alert  *(omit section entirely if no earnings within 90 days)*
[Flag: IMMINENT (≤3d) or HIGH-VOLATILITY (≤14d) or UPCOMING (≤90d)]
Next report: <date> (<X days away>, <time of day if known>)
EPS Estimate: <value or "not available">
What to watch: <1 sentence on the key metric the market is focused on>
Expected move: ±<X>% based on <ATR / beta / historical earnings moves>

## 🟢 Bull Case — Target: $XXX (<derivation formula>)
- **Catalyst 1:** [specific, data/news-grounded, no vague generics]
- **Catalyst 2:** [specific]
- **Catalyst 3:** [specific]

## 🔴 Bear Case — Target: $XXX (<derivation formula>)
- **Risk 1:** [specific, data/news-grounded]
- **Risk 2:** [specific]
- **Risk 3:** [specific]

## 📊 Valuation Snapshot
[2-3 sentences. Cite exact numbers: P/E, PEG, Fair Value, Upside % from JSON.]

## 📈 Technical Read
[RSI signal, SMA200 trend, MACD bias. Max 2 sentences.]

## ⚡ Strategic Takeaway
[One sentence: price + earnings timing + key catalyst + net verdict.]"""


def run_ai_agent(
    ticker: str,
    info: dict,
    hist,
    news: list[dict],
    indicators: dict | None,
    fv: dict | None,
    earnings: dict | None = None,
    dcf_g: float = 0.20,
    dcf_w: float = 0.10,
) -> str:
    """
    Four-source AI synthesis v8:
    1. Financial metrics (FMP/yfinance)
    2. Ultra-fresh news with breaking flags
    3. Earnings proximity context
    4. Polymarket prediction odds
    """
    from whale_terminal_modules import fetch_polymarket_markets

    cp  = float(hist["Close"].iloc[-1])
    h52 = info.get("fiftyTwoWeekHigh")
    l52 = info.get("fiftyTwoWeekLow")

    # ── Source 1: financial data ──────────────────────────────────────────────
    rsi_v  = indicators.get("rsi","N/A") if indicators else "N/A"
    sma200 = indicators.get("sma_200")   if indicators else None
    atr    = calc_atr(hist)

    near_ath = False
    if h52:
        try: near_ath = (cp / float(h52)) > 0.95
        except: pass

    # Minimal financial_data — only fields the prompt actively uses.
    # Compact (no indent) to save ~30% of prompt tokens.
    financial_data = {
        "tk": ticker,
        "px": round(cp, 2),
        "52H": fmt(h52),  "52L": fmt(l52),  "ATH": near_ath,
        "atr": f"${atr:.2f}" if atr else "N/A",
        "mcap": fmt(info.get("marketCap"), "money"),
        "fwdPE": fmt(info.get("forwardPE")),
        "ttmPE": fmt(info.get("trailingPE")),
        "peg":   fmt(info.get("pegRatio")),
        "fwdEps": fmt(info.get("forwardEps")),
        "ttmEps": fmt(info.get("trailingEps")),
        "revGr":  fmt(info.get("revenueGrowth"),  "percent"),
        "epsGr":  fmt(info.get("earningsGrowth"), "percent"),
        "pm":     fmt(info.get("profitMargins"),   "percent"),
        "om":     fmt(info.get("operatingMargins"),"percent"),
        "roe":    fmt(info.get("returnOnEquity"),  "percent"),
        "fcf":    fmt(info.get("freeCashflow"),    "money"),
        "d2e":    fmt(info.get("debtToEquity")),
        "beta":   fmt(info.get("beta")),
        "rsi":    f"{rsi_v:.2f}" if isinstance(rsi_v, float) else "N/A",
        "macd":   ("Bull" if indicators and indicators["macd"]>indicators["signal"] else "Bear") if indicators else "N/A",
        "sma200": ("Above" if cp > sma200 else "Below") if sma200 else "N/A",
        "tgt":    fmt(info.get("targetMeanPrice")),
        "fv":     f"${fv['fair_value']:.2f}" if fv else "N/A",
        "fvUp":   f"{fv['upside']:.1f}%" if fv else "N/A",
        "dcf":    (f"${fv['dcf_model']:.2f}" if fv and fv.get("dcf_model") and not fv.get("dcf_outlier") else "excl") if fv else "N/A",
        "bull":   f"${fv['bull_case']:.2f}" if fv else "N/A",
        "bear":   f"${fv['bear_case']:.2f}" if fv else "N/A",
        "peM":    f"{fv['pe_multiple']:.0f}x" if fv else "N/A",
        "sect":   info.get("sector","N/A"),
        "ind":    info.get("industry","N/A"),
    }

    # ── Source 2: news — top 5 only to save tokens ───────────────────────────
    news_summary = []
    for n in news[:5]:                          # hard cap: 5 headlines max
        entry = {
            "h":  n.get("title","")[:120],      # truncate long headlines
            "s":  n.get("sentiment","Neutral")[0],  # B/N/Be (1 char)
            "sc": round(n.get("score",0.5),2),
        }
        if n.get("breaking"):
            entry["brk"] = True
        if n.get("hours_ago") is not None:
            entry["age"] = f"{n['hours_ago']:.0f}h"
        news_summary.append(entry)

    bull_n         = sum(1 for n in news if n.get("sentiment")=="Bullish")
    bear_n         = sum(1 for n in news if n.get("sentiment")=="Bearish")
    breaking_count = sum(1 for n in news if n.get("breaking"))
    news_summary_obj = {
        "top5":    news_summary,
        "sent":    f"{bull_n}B/{bear_n}Be/{len(news)-bull_n-bear_n}N",
        "brk":     breaking_count,
    }

    # ── Source 3: earnings context ────────────────────────────────────────────
    if earnings:
        eps_est = earnings.get("eps_estimate")
        eps_str = f"${eps_est:.2f}" if eps_est is not None else "not available"
        # Estimate expected move: ±(beta * ATR / price * sqrt(14)) rough proxy
        try:
            beta = float(info.get("beta") or 1.0)
            atr_pct = (atr / cp * 100) if atr else 3.0
            expected_move_pct = round(atr_pct * beta * 1.5, 1)
        except:
            expected_move_pct = None

        earnings_data = {
            "next_earnings_date": earnings["date"],
            "days_away":          earnings["days_away"],
            "time_of_day":        earnings.get("time_of_day","Unknown"),
            "is_imminent":        earnings["is_imminent"],
            "is_soon":            earnings["is_soon"],
            "eps_estimate":       eps_str,
            "expected_move_pct":  f"±{expected_move_pct}%" if expected_move_pct else "unknown",
            "volatility_flag":    ("🔴 IMMINENT" if earnings["is_imminent"]
                                   else "⚡ HIGH-VOLATILITY EVENT" if earnings["is_soon"]
                                   else "UPCOMING"),
        }
    else:
        earnings_data = {"status": "No earnings announcement found within 90 days."}

    # ── Source 4: Polymarket ──────────────────────────────────────────────────
    try:
        poly_markets = fetch_polymarket_markets(ticker, limit=3)
        prediction_data = [
            {
                "question": m["question"],
                "yes_prob": f"{m['yes_price']*100:.1f}%",
                "no_prob":  f"{m['no_price']*100:.1f}%",
                "volume":   f"${m['volume']:,.0f}",
            }
            for m in poly_markets
        ] if poly_markets else "No active prediction markets found."
    except:
        prediction_data = "Polymarket unavailable."

    # ── Invoke LLM ────────────────────────────────────────────────────────────
    if llm is None:
        return (
            "## ⚠️ AI Analysis Unavailable\n\n"
            "**GROQ_API_KEY** is not configured.  \n"
            "Add it to `.streamlit/secrets.toml` or your Streamlit Cloud Secrets panel "
            "to enable the AI agent."
        )
    # Compact JSON serialisation — no indent, no extra whitespace.
    # Saves ~25-35% prompt tokens vs indent=2 on large dicts.
    prompt = AGENT_PROMPT.format(
        date=datetime.now().strftime("%B %d, %Y"),
        financial_data=json.dumps(financial_data, separators=(",", ":")),
        news_data=json.dumps(news_summary_obj, separators=(",", ":")),
        earnings_data=json.dumps(earnings_data, separators=(",", ":")),
        prediction_data=json.dumps(prediction_data, separators=(",", ":")),
    )
    verdict = llm.invoke(prompt).content
    return verdict


# =============================================================================
# PAGE: HOME
# =============================================================================
def page_home():
    st.markdown(
        '''<div class="page-title">🏠 Market Dashboard</div>
        <p style="color:#8b949e;margin-bottom:24px;">Your institutional command centre.</p>''',
        unsafe_allow_html=True,
    )
    col_s, col_b = st.columns([4,1])
    with col_s:
        search = st.text_input("Search", placeholder="🔍  Search ticker — e.g. AAPL, TSLA, NVDA…",
                               label_visibility="collapsed", key="home_search")
    with col_b:
        if st.button("Analyse →", type="primary", use_container_width=True, key="home_go"):
            if search.strip():
                st.session_state["analysis_ticker"] = search.strip().upper()
                st.session_state["active_page"]     = "🔍 Stock Analysis"
                st.session_state["analysis_loaded"] = False
                st.rerun()
    st.markdown("---")

    TRENDING = ["NVDA","AAPL","MSFT","TSLA","META"]
    st.markdown("### 🔥 Trending Stocks")
    # Fetch all 5 quotes in a single FMP batch request
    trending_quotes = _fmp_quote_batch(tuple(TRENDING))
    cols = st.columns(len(TRENDING))
    for col, sym in zip(cols, TRENDING):
        with col:
            try:
                q     = trending_quotes.get(sym, {})
                price = float(q.get("price", 0) or 0)
                chg   = float(q.get("changesPercentage", 0) or 0)
                cc    = "#26a69a" if chg >= 0 else "#ef5350"
                cs    = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
                st.markdown(f"""<div class="info-card" style="text-align:center;">
                  <div style="font-family:'JetBrains Mono',monospace;font-size:1.1rem;
                       font-weight:800;color:#f0f6fc;">{sym}</div>
                  <div style="font-size:1.3rem;font-weight:700;color:#f0f6fc;margin:4px 0;">${price:,.2f}</div>
                  <div style="color:{cc};font-weight:700;font-size:0.9rem;">{cs}</div>
                </div>""", unsafe_allow_html=True)
                if st.button(f"▶ {sym}", key=f"ht_{sym}", use_container_width=True):
                    st.session_state["analysis_ticker"] = sym
                    st.session_state["active_page"]     = "🔍 Stock Analysis"
                    st.session_state["analysis_loaded"] = False
                    st.rerun()
            except:
                st.markdown(f"**{sym}** — Loading…")

    st.markdown("---")
    st.markdown("### 🌡️ Sector Heatmap (1-Day Return)")
    SECTOR_ETFS = {
        "Technology":"XLK","Healthcare":"XLV","Financials":"XLF",
        "Energy":"XLE","Industrials":"XLI","Consumer Disc.":"XLY",
        "Comm. Svcs":"XLC","Utilities":"XLU","Materials":"XLB",
    }
    returns = {}
    with st.spinner("Loading sector data…"):
        etf_quotes = _fmp_quote_batch(tuple(SECTOR_ETFS.values()))
        for name, etf in SECTOR_ETFS.items():
            try:
                q = etf_quotes.get(etf, {})
                chg_pct = q.get("changesPercentage")
                if chg_pct is not None:
                    returns[name] = float(chg_pct)
            except:
                pass
    if returns:
        rets   = list(returns.values())
        names  = list(returns.keys())
        colors = ["#26a69a" if r>=0 else "#ef5350" for r in rets]
        fig = go.Figure(go.Bar(x=names, y=rets, marker_color=colors,
            text=[f"{r:+.2f}%" for r in rets], textposition="outside",
            hovertemplate="<b>%{x}</b><br>%{y:+.2f}%<extra></extra>"))
        fig.update_layout(template="plotly_dark", height=300,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis_title="1-Day Return (%)", font=dict(color="#f0f6fc"),
            margin=dict(t=20,b=10))
        fig.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.2)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🚀 Quick Access")
    qc1,qc2,qc3,qc4 = st.columns(4)
    with qc1:
        if st.button("👀 My Watchlist", use_container_width=True, key="q_wl"):
            st.session_state["active_page"]="👀 Watchlist"; st.rerun()
    with qc2:
        if st.button("💼 My Portfolio", use_container_width=True, key="q_pt"):
            st.session_state["active_page"]="💼 Portfolio"; st.rerun()
    with qc3:
        if st.button("📰 Global News", use_container_width=True, key="q_news"):
            st.session_state["active_page"]="📰 Global News"; st.rerun()
    with qc4:
        if st.button("⚙️ Settings", use_container_width=True, key="q_set"):
            st.session_state["active_page"]="⚙️ Settings"; st.rerun()


# =============================================================================
# PAGE: STOCK ANALYSIS  (auto-peer group + AI Agent + Polymarket tab)
# =============================================================================
def page_analysis(run_analysis: bool) -> None:
    ticker    = st.session_state["analysis_ticker"]
    timeframe = st.session_state["analysis_timeframe"]
    show_adv  = st.session_state["show_advanced"]
    show_ai   = st.session_state["show_ai_verdict"]
    dcf_g     = st.session_state["dcf_growth"]
    dcf_w     = st.session_state["dcf_wacc"]
    acc       = st.session_state["account_size"]
    risk      = st.session_state["risk_pct"]
    atr_m     = st.session_state["atr_mult"]

    st.markdown(
        f'''<div class="page-title">🔍 Stock Analysis</div>
        <span class="ticker-chip">{ticker}</span>
        <span style="color:#8b949e;margin-left:10px;font-size:0.9rem;">
        Configure in sidebar → click RUN ANALYSIS</span>''',
        unsafe_allow_html=True,
    )
    st.markdown("")

    if not run_analysis and not st.session_state.get("analysis_loaded"):
        st.info("👈 Enter a ticker in the sidebar and click **🚀 RUN ANALYSIS** to begin.")
        return

    # Cache-bust when ticker changes
    if ticker != st.session_state.get("last_ticker",""):
        st.cache_data.clear()
        st.session_state["last_ticker"]    = ticker
        st.session_state["auto_peers"]     = []
        st.session_state["analysis_loaded"]= False

    with st.spinner(f"Fetching {ticker} market data…"):
        try:
            info = get_stock_info(ticker)
            hist = get_stock_history(ticker,
                       RANGE_MAP[timeframe]["period"],
                       RANGE_MAP[timeframe]["interval"])
            if hist.empty:
                st.error("❌ No price data found. Verify the ticker symbol."); return
            st.session_state["analysis_loaded"] = True

            cp   = float(hist["Close"].iloc[-1])
            prev = float(info.get("previousClose") or
                         (hist["Close"].iloc[-2] if len(hist)>1 else cp))
            chg  = cp-prev; chgp=(chg/prev*100) if prev else 0
            src  = info.get("_source","yfinance")
            sector   = info.get("sector","")
            industry = info.get("industry","")

            # ── Fetch earnings date ────────────────────────────────────────────
            earnings = get_earnings_date(ticker, FMP_API_KEY)

            # ── Build earnings badge for header ───────────────────────────────
            if earnings:
                if earnings["is_imminent"]:
                    earn_badge = (
                        f"<span style='background:#ef5350;color:#fff;font-weight:700;"
                        f"border-radius:6px;padding:3px 10px;font-size:0.82rem;margin-left:12px;'>"
                        f"🔴 EARNINGS IN {earnings['days_away']}d — {earnings['date']}</span>"
                    )
                elif earnings["is_soon"]:
                    earn_badge = (
                        f"<span style='background:rgba(227,179,65,0.2);color:#e3b341;font-weight:700;"
                        f"border:1px solid #e3b341;border-radius:6px;padding:3px 10px;"
                        f"font-size:0.82rem;margin-left:12px;'>"
                        f"⚡ Earnings in {earnings['days_away']}d — {earnings['date']}</span>"
                    )
                else:
                    earn_badge = (
                        f"<span style='background:rgba(88,166,255,0.1);color:#58a6ff;"
                        f"border:1px solid rgba(88,166,255,0.3);border-radius:6px;padding:3px 10px;"
                        f"font-size:0.82rem;margin-left:12px;'>"
                        f"📅 Next Earnings: {earnings['date']}</span>"
                    )
            else:
                earn_badge = ""

            st.markdown(
                f'<div style="margin-bottom:12px;">'
                f'<span class="ticker-chip" style="font-size:1rem;">{ticker}</span>'
                f'{earn_badge}</div>',
                unsafe_allow_html=True,
            )


            # ── Auto peer group ────────────────────────────────────────────────
            if not st.session_state["auto_peers"]:
                with st.spinner("Detecting peer group…"):
                    st.session_state["auto_peers"] = get_auto_peers(
                        ticker, sector, industry, FMP_API_KEY)
            peers = st.session_state["auto_peers"]
            render_peer_group_info(peers, source="auto")

            # ── Market snapshot ────────────────────────────────────────────────
            st.markdown("## 📈 Market Snapshot")
            c1,c2,c3,c4,c5 = st.columns(5)
            with c1: st.metric("Price", f"${cp:.2f}", f"{chg:+.2f} ({chgp:+.2f}%)",
                                help="Current price vs previous close")
            with c2: st.metric("Market Cap", fmt(info.get("marketCap"),"money"),
                                help="Total market capitalisation")
            with c3: st.metric("Volume", f"{hist['Volume'].iloc[-1]:,.0f}",
                                help="Shares traded in latest period")
            with c4:
                hw = info.get("fiftyTwoWeekHigh")
                st.metric("52W High", f"${float(hw):.2f}" if hw else "N/A",
                           help="Highest price in last 52 weeks")
            with c5:
                lw = info.get("fiftyTwoWeekLow")
                st.metric("52W Low",  f"${float(lw):.2f}" if lw else "N/A",
                           help="Lowest price in last 52 weeks")
            st.caption(f"Source: **{src}** · Sector: **{sector}** · Industry: **{industry}** "
                       f"· {datetime.now():%Y-%m-%d %H:%M:%S}")

            # ── Valuation metrics ──────────────────────────────────────────────
            st.markdown("## 💰 Valuation Metrics")
            c1,c2,c3,c4 = st.columns(4)
            with c1: st.metric("Forward P/E",  fmt(info.get("forwardPE")),
                                help="Price ÷ next-year EPS estimate")
            with c2: st.metric("P/E (TTM)",    fmt(info.get("trailingPE")),
                                help="Price ÷ trailing 12-month EPS")
            with c3: st.metric("PEG Ratio",    fmt(info.get("pegRatio")),
                                help="P/E ÷ earnings growth rate. <1 = undervalued")
            with c4: st.metric("Price / Sales",fmt(info.get("priceToSalesTrailing12Months")),
                                help="Market cap ÷ annual revenue")

            # ── Quality score ──────────────────────────────────────────────────
            sc, desc, emoji = quality_score(info.get("returnOnEquity"), info.get("profitMargins"))
            st.markdown("## 🎯 Quality Assessment")
            c1,c2,c3 = st.columns([2,2,1])
            with c1: st.metric("Quality Score", f"{sc}/10 {emoji}",
                                help="Composite: ROE + profit margin (max 10)")
            with c2: st.info(f"**{desc}**")
            with c3: st.metric("Beta", fmt(info.get("beta")),
                                help="Price sensitivity vs S&P 500. >1 = more volatile")

            # ── Technical Analysis — TradingView-style multi-panel chart ────────
            # ONE make_subplots figure: panels share the X-axis so zooming /
            # panning on any panel moves all panels together.
            # Each panel has its own independent Y-axis (Price $, Volume, RSI 0-100, MACD).
            # Overlap fix: pixel-level domain calculations replace fractional row_heights.
            st.markdown("## 📊 Technical Analysis")

            # Fetch 2 years of daily candles so users can scroll far back.
            # Keep a separate 1-year series for RSI Wilder warm-up accuracy.
            _rsi_hist = get_stock_history(ticker, "1y", "1d")
            _disp_hist = get_stock_history(ticker, "2y", "1d")
            if _disp_hist.empty:
                _disp_hist = hist
            _chart_src = _rsi_hist if not _rsi_hist.empty else _disp_hist
            indicators = calc_rsi_macd_bb(_chart_src)

            # Controls
            _cc1, _cc2, _cc3 = st.columns([2, 4, 2])
            with _cc1:
                _chart_type = st.selectbox(
                    "📈 Chart Type",
                    ["Candlestick", "Line", "OHLC / Bars"],
                    key="chart_type_sel",
                )
            ind_defaults = st.session_state.get("chart_indicators", ["SMA 50","SMA 200"])
            with _cc2:
                chosen_inds = st.multiselect(
                    "📐 Overlay Indicators",
                    options=["SMA 20","SMA 50","SMA 200","Bollinger Bands","VWAP"],
                    default=ind_defaults,
                    key="chart_indicators",
                    help="Select indicators to overlay on the price chart",
                )
            with _cc3:
                show_studies = st.checkbox(
                    "RSI + MACD panels",
                    value=st.session_state.get("chart_show_studies", True),
                    key="chart_show_studies",
                    help="Show RSI and MACD below the price chart",
                )

            # ── Pixel-accurate domain calculation ────────────────────────────
            # Assign each panel a target pixel height.  Convert to [0,1] domain
            # fractions AFTER reserving space for gaps.  This guarantees panels
            # never overlap regardless of total figure height.
            _PX_PRICE  = 420   # candle panel
            _PX_VOL    = 100   # volume panel
            _PX_RSI    = 130   # RSI panel
            _PX_MACD   = 140   # MACD panel
            _PX_GAP    = 18    # gap between panels (pixels)
            _PX_TOP    = 44    # top margin
            _PX_BOTTOM = 36    # bottom margin (date labels)

            if show_studies:
                _panels_px = [_PX_PRICE, _PX_VOL, _PX_RSI, _PX_MACD]
                _n_gaps    = 3
                _total_h   = _PX_PRICE + _PX_VOL + _PX_RSI + _PX_MACD + _n_gaps*_PX_GAP + _PX_TOP + _PX_BOTTOM
            else:
                _panels_px = [_PX_PRICE, _PX_VOL]
                _n_gaps    = 1
                _total_h   = _PX_PRICE + _PX_VOL + _n_gaps*_PX_GAP + _PX_TOP + _PX_BOTTOM

            # Convert gap pixels to fraction of the plottable area
            _plot_h  = _total_h - _PX_TOP - _PX_BOTTOM
            _gap_frac = _PX_GAP / _plot_h

            # Build bottom-up domain list [bottom, top] in [0,1] normalised coords
            # Plotly domain goes from 0 (bottom) to 1 (top)
            _panel_fracs = [p / _plot_h for p in _panels_px]
            _domains = []
            _cursor  = 0.0
            for _frac in reversed(_panel_fracs):
                _domains.insert(0, [_cursor, _cursor + _frac])
                _cursor += _frac + _gap_frac

            # Build make_subplots with precomputed row_heights (just the ratios)
            _n_rows = len(_panels_px)
            fig = make_subplots(
                rows=_n_rows, cols=1,
                row_heights=_panel_fracs,
                vertical_spacing=_gap_frac,
                shared_xaxes=True,
                subplot_titles=None,
            )

            # ── Shared styling ────────────────────────────────────────────────
            _GRID_COL  = "rgba(30,42,69,0.6)"
            _GRID_COL2 = "rgba(30,42,69,0.35)"
            _AXIS_CFG  = dict(
                showgrid=True, gridcolor=_GRID_COL,
                zeroline=False, linecolor="#1e2a45",
                tickfont=dict(size=10, color="#8b949e"),
                # Force English locale for month names
                tickformatstops=[
                    dict(dtickrange=[None, 86400000],       value="%b %d"),
                    dict(dtickrange=[86400000, 604800000],  value="%b %d"),
                    dict(dtickrange=[604800000, None],      value="%b %Y"),
                ],
            )

            # ── ROW 1: Price panel ────────────────────────────────────────────
            if _chart_type == "Line":
                fig.add_trace(go.Scatter(
                    x=_disp_hist.index, y=_disp_hist["Close"], name=ticker,
                    line=dict(color="#58a6ff", width=2),
                    hovertemplate=f"{ticker}: $%{{y:.2f}}<extra></extra>",
                ), row=1, col=1)
            elif _chart_type == "OHLC / Bars":
                fig.add_trace(go.Ohlc(
                    x=_disp_hist.index,
                    open=_disp_hist["Open"], high=_disp_hist["High"],
                    low=_disp_hist["Low"],   close=_disp_hist["Close"],
                    name="OHLC",
                    increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
                ), row=1, col=1)
            else:  # Candlestick
                fig.add_trace(go.Candlestick(
                    x=_disp_hist.index,
                    open=_disp_hist["Open"], high=_disp_hist["High"],
                    low=_disp_hist["Low"],   close=_disp_hist["Close"],
                    name="OHLC",
                    increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
                    increasing_fillcolor="#26a69a",   decreasing_fillcolor="#ef5350",
                ), row=1, col=1)

            # SMA / BB / VWAP overlays
            if indicators:
                _sma_map = {
                    "SMA 20":  (20,  "#58a6ff", "dot",   1.4),
                    "SMA 50":  (50,  "#f78166", "solid", 1.7),
                    "SMA 200": (200, "#e3b341", "dash",  1.9),
                }
                for _lbl, (_win, _col, _dsh, _wid) in _sma_map.items():
                    if _lbl in chosen_inds:
                        _sma = _disp_hist["Close"].rolling(_win).mean()
                        if not pd.isna(_sma.iloc[-1]):
                            fig.add_trace(go.Scatter(
                                x=_disp_hist.index, y=_sma, name=_lbl,
                                line=dict(color=_col, width=_wid, dash=_dsh),
                                hovertemplate=f"{_lbl}: $%{{y:.2f}}<extra></extra>",
                            ), row=1, col=1)
                if "Bollinger Bands" in chosen_inds:
                    _s20  = _disp_hist["Close"].rolling(20).mean()
                    _std  = _disp_hist["Close"].rolling(20).std()
                    _bbu  = _s20 + _std * 2
                    _bbl  = _s20 - _std * 2
                    fig.add_trace(go.Scatter(
                        x=_disp_hist.index, y=_bbu, name="BB Upper",
                        line=dict(color="rgba(163,113,247,0.7)", width=1, dash="dot"),
                        hovertemplate="BB Upper: $%{y:.2f}<extra></extra>",
                    ), row=1, col=1)
                    fig.add_trace(go.Scatter(
                        x=_disp_hist.index, y=_bbl, name="BB Lower",
                        line=dict(color="rgba(163,113,247,0.7)", width=1, dash="dot"),
                        fill="tonexty", fillcolor="rgba(163,113,247,0.05)",
                        hovertemplate="BB Lower: $%{y:.2f}<extra></extra>",
                    ), row=1, col=1)
                if "VWAP" in chosen_inds and "Volume" in _disp_hist.columns:
                    try:
                        _tp  = (_disp_hist["High"] + _disp_hist["Low"] + _disp_hist["Close"]) / 3
                        _vw  = (_tp * _disp_hist["Volume"]).cumsum() / _disp_hist["Volume"].cumsum()
                        fig.add_trace(go.Scatter(
                            x=_disp_hist.index, y=_vw, name="VWAP",
                            line=dict(color="#a371f7", width=2),
                            hovertemplate="VWAP: $%{y:.2f}<extra></extra>",
                        ), row=1, col=1)
                    except: pass

            if earnings:
                try:
                    _ed = pd.Timestamp(earnings["date_raw"])
                    if _disp_hist.index[0] <= _ed <= _disp_hist.index[-1]:
                        fig.add_vline(
                            x=_ed, line_dash="dot", line_color="#e3b341", line_width=1.5,
                            annotation_text="📅 Earnings", annotation_font_color="#e3b341",
                        )
                except: pass

            # ── ROW 2: Volume panel ───────────────────────────────────────────
            _vcols = ["#26a69a" if _disp_hist["Close"].iloc[_i] >= _disp_hist["Open"].iloc[_i]
                      else "#ef5350" for _i in range(len(_disp_hist))]
            fig.add_trace(go.Bar(
                x=_disp_hist.index, y=_disp_hist["Volume"],
                marker_color=_vcols, opacity=0.75,
                name="Volume", showlegend=False,
                hovertemplate="Vol: %{y:,.0f}<extra></extra>",
            ), row=2, col=1)

            # ── ROWS 3 & 4: RSI + MACD (only when show_studies) ──────────────
            if show_studies and indicators:
                _c   = _disp_hist["Close"]
                _d   = _c.diff()
                _ag  = _d.where(_d > 0, 0.0).ewm(alpha=1/14, adjust=False).mean()
                _al  = (-_d.where(_d < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
                _rsi = 100 - (100 / (1 + _ag / _al.replace(0, float("nan"))))

                fig.add_trace(go.Scatter(
                    x=_disp_hist.index, y=_rsi, name="RSI(14)",
                    line=dict(color="#e3b341", width=1.8),
                    hovertemplate="RSI: %{y:.1f}<extra></extra>",
                ), row=3, col=1)
                fig.add_hrect(y0=70, y1=100, fillcolor="rgba(239,83,80,0.07)",   line_width=0, row=3, col=1)
                fig.add_hrect(y0=0,  y1=30,  fillcolor="rgba(38,166,154,0.07)",  line_width=0, row=3, col=1)
                fig.add_hline(y=70, line_dash="dot", line_color="rgba(239,83,80,0.55)",  line_width=1, row=3, col=1)
                fig.add_hline(y=50, line_dash="dot", line_color="rgba(139,148,158,0.25)",line_width=1, row=3, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="rgba(38,166,154,0.55)", line_width=1, row=3, col=1)

                _e12   = _c.ewm(span=12, adjust=False).mean()
                _e26   = _c.ewm(span=26, adjust=False).mean()
                _macd  = _e12 - _e26
                _msig  = _macd.ewm(span=9, adjust=False).mean()
                _mhist = _macd - _msig
                _mhcol = ["#26a69a" if v >= 0 else "#ef5350" for v in _mhist]

                fig.add_trace(go.Bar(
                    x=_disp_hist.index, y=_mhist,
                    marker_color=_mhcol, opacity=0.8,
                    name="Histogram", showlegend=False,
                    hovertemplate="Hist: %{y:.4f}<extra></extra>",
                ), row=4, col=1)
                fig.add_trace(go.Scatter(
                    x=_disp_hist.index, y=_macd, name="MACD",
                    line=dict(color="#58a6ff", width=1.6),
                    hovertemplate="MACD: %{y:.4f}<extra></extra>",
                ), row=4, col=1)
                fig.add_trace(go.Scatter(
                    x=_disp_hist.index, y=_msig, name="Signal",
                    line=dict(color="#f78166", width=1.4),
                    hovertemplate="Signal: %{y:.4f}<extra></extra>",
                ), row=4, col=1)

            # ── Layout ────────────────────────────────────────────────────────
            fig.update_layout(
                template="plotly_dark",
                height=_total_h,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(13,17,40,0.55)",
                font=dict(family="Space Grotesk", color="#c9d1d9", size=11),
                margin=dict(t=_PX_TOP, b=_PX_BOTTOM, l=8, r=72),
                hovermode="x unified",
                dragmode="pan",
                # TradingView-style crosshair cursor
                newshape=dict(line_color="#58a6ff"),
                modebar_add=["drawline","drawopenpath","eraseshape"],
                modebar_remove=["lasso2d","select2d"],
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.015,
                    bgcolor="rgba(13,17,40,0.85)", bordercolor="#1e2a45", borderwidth=1,
                    font=dict(size=11),
                ),
                # Crosshair spike lines — vertical line spanning all panels
                xaxis=dict(
                    **_AXIS_CFG,
                    rangeslider_visible=False,
                    showspikes=True,
                    spikemode="across+toaxis",
                    spikesnap="cursor",
                    spikecolor="#58a6ff",
                    spikethickness=1,
                    spikedash="solid",
                ),
            )

            # Y-axis: price panel (row 1) — right side, dollar prefix
            fig.update_yaxes(
                row=1, col=1,
                **_AXIS_CFG,
                tickprefix="$",
                side="right",
                showspikes=True, spikecolor="#58a6ff", spikethickness=1,
            )
            # Y-axis: volume panel (row 2)
            fig.update_yaxes(
                row=2, col=1,
                **_AXIS_CFG,
                tickformat=".2s",
                side="right",
                title_text="Vol",
                title_font=dict(size=10, color="#8b949e"),
            )
            # Y-axis: RSI panel (row 3)
            if show_studies:
                fig.update_yaxes(
                    row=3, col=1,
                    **_AXIS_CFG,
                    range=[0, 100],
                    tickvals=[0, 30, 50, 70, 100],
                    side="right",
                    title_text="RSI",
                    title_font=dict(size=10, color="#8b949e"),
                )
                # Y-axis: MACD panel (row 4)
                fig.update_yaxes(
                    row=4, col=1,
                    **_AXIS_CFG,
                    side="right",
                    title_text="MACD",
                    title_font=dict(size=10, color="#8b949e"),
                )

            # X-axes: hide date labels on all rows EXCEPT the bottom row.
            # The bottom row is whichever is last (studies → row 4; no studies → row 2).
            _bottom_row = _n_rows
            for _r in range(1, _n_rows + 1):
                _show_labels = (_r == _bottom_row)
                fig.update_xaxes(
                    row=_r, col=1,
                    **_AXIS_CFG,
                    rangeslider_visible=False,
                    showticklabels=_show_labels,
                    showspikes=True,
                    spikemode="across+toaxis",
                    spikesnap="cursor",
                    spikecolor="#58a6ff",
                    spikethickness=1,
                    spikedash="solid",
                )

            # Label each panel with a small annotation in the plot margin
            _panel_labels = {1: f"<b>{ticker}</b>", 2: "Volume"}
            if show_studies:
                _panel_labels[3] = "RSI (14)"
                _panel_labels[4] = "MACD (12,26,9)"
            for _r, _lbl in _panel_labels.items():
                fig.add_annotation(
                    xref=f"x{_r} domain" if _r > 1 else "x domain",
                    yref=f"y{_r} domain" if _r > 1 else "y domain",
                    x=0.0, y=1.04,
                    text=_lbl,
                    showarrow=False,
                    font=dict(size=11, color="#8b949e"),
                    xanchor="left",
                )

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "scrollZoom": True,
                    "displayModeBar": True,
                    "modeBarButtonsToAdd": ["pan2d","zoomIn2d","zoomOut2d","resetScale2d","toImage"],
                    "toImageButtonOptions": {"format":"png","filename":f"{ticker}_chart"},
                    "displaylogo": False,
                    "locale": "en",   # force English month names
                },
            )
            st.caption("💡 Scroll to zoom · Drag to pan · Double-click to reset · 2-year history loaded")

            # ── Technical indicator strip ──────────────────────────────────────
            if indicators:
                rsi_v = indicators["rsi"]
                rsi_c = "#26a69a" if rsi_v<30 else "#ef5350" if rsi_v>70 else "#e3b341"
                rsi_l = "Oversold 🟢" if rsi_v<30 else "Overbought 🔴" if rsi_v>70 else "Neutral 🟡"
                macd_bias = "Bullish" if indicators["macd"]>indicators["signal"] else "Bearish"
                bb_pos = ((cp - indicators["bb_lower"]) /
                          max(0.01, indicators["bb_upper"]-indicators["bb_lower"]))*100
                trend  = "✅ Above SMA200 (Bullish)" if cp>indicators["sma_200"] else "⚠️ Below SMA200 (Bearish)"
                ti1,ti2,ti3,ti4 = st.columns(4)
                with ti1: st.metric("RSI (14)", f"{rsi_v:.1f}", rsi_l,
                                    help="Relative Strength Index. <30=oversold, >70=overbought")
                with ti2: st.metric("MACD Bias", macd_bias,
                                    f"MACD:{indicators['macd']:+.3f}",
                                    help="MACD vs Signal line crossover direction")
                with ti3: st.metric("BB Position", f"{bb_pos:.0f}%",
                                    help="Where price sits within Bollinger Bands (0%=lower, 100%=upper)")
                with ti4: st.metric("200 SMA Trend", trend.split(" ")[0],
                                    help="Price relative to 200-day Simple Moving Average")
                st.caption(f"SMA 20: ${indicators['sma_20']:.2f}  ·  "
                           f"SMA 50: ${indicators['sma_50']:.2f}  ·  "
                           f"SMA 200: ${indicators['sma_200']:.2f}  ·  "
                           f"Trend: {trend}")

            # ── Risk Management (clean, simplified) ────────────────────────────
            st.markdown("## ⚖️ Position Sizing & Risk")
            st.markdown(
                f"<div class='risk-card'>"
                f"<span style='color:#e3b341;font-weight:700;'>Formula: </span>"
                f"Shares = (Account × Risk%) ÷ (ATR × Stop Multiplier) &nbsp;|&nbsp; "
                f"Account: <b>${acc:,.0f}</b> · Risk: <b>{risk*100:.1f}%</b> · "
                f"ATR Mult: <b>{atr_m}×</b></div>",
                unsafe_allow_html=True,
            )
            atr = calc_atr(hist)
            if atr and atr>0:
                sh, sp, sd = calc_pos_size(acc, risk, atr, cp, atr_m)
                if sh:
                    c1,c2,c3,c4,c5 = st.columns(5)
                    with c1: st.metric("ATR (14d)", f"${atr:.2f}",
                                       help="Average True Range: avg daily price swing over 14 days")
                    with c2: st.metric("Rec. Shares", str(sh), f"for ${acc:,.0f}",
                                       help="Recommended position size based on your risk params")
                    with c3: st.metric("Stop-Loss", f"${sp:.2f}", f"−${sd:.2f}",
                                       help="Entry minus ATR×multiplier — where to cut the loss")
                    with c4: st.metric("Max Risk $", f"${sh*sd:,.0f}", f"{risk*100:.1f}% of acct",
                                       help="Worst-case dollar loss if stop is hit")
                    with c5: st.metric("Position $", f"${sh*cp:,.0f}", f"{sh*cp/acc*100:.1f}% of acct",
                                       help="Total notional value of this position")
                    st.success(
                        f"📐 **{sh} shares** at ${cp:.2f} · Stop: **${sp:.2f}** · "
                        f"Risk: **${sh*sd:,.0f}** ({risk*100:.1f}%) · "
                        f"Position: **${sh*cp:,.0f}** ({sh*cp/acc*100:.1f}%)"
                    )
            else:
                st.warning("Need ≥14 trading days of history to compute ATR.")

            # ── Deep Dive Tabs ─────────────────────────────────────────────────
            st.markdown("## 📑 Financial Deep Dive")
            t1,t2,t3,t4,t5,t6,t7,t8,t9,t10 = st.tabs([
                "💼 Profitability","💵 Balance Sheet","📊 Growth","⚖️ Valuation",
                "📈 Backtest","🔗 Correlation","💎 DCF","📉 Rel. Strength",
                "🧪 Adv. Backtest","🔮 Prediction Market",
            ])

            # ── helper: build a clean ["Metric","Value"] frame with all-str columns ──
            def _kv(pairs: list[tuple]) -> pd.DataFrame:
                """
                Accepts a list of (label, value) tuples and returns a two-column
                DataFrame where BOTH columns are explicitly cast to str.
                This prevents the ArrowTypeError that occurs when a 'Value' column
                is inferred as object-dtype and contains mixed Python types.
                """
                return pd.DataFrame(
                    {"Metric": [str(k) for k, _ in pairs],
                     "Value":  [str(v) for _, v in pairs]}
                )

            with t1:
                ca,cb = st.columns(2)
                with ca:
                    st.table(_kv([
                        ("Profit Margin",   fmt(info.get("profitMargins"),   "percent")),
                        ("Operating Margin",fmt(info.get("operatingMargins"),"percent")),
                        ("Gross Margin",    fmt(info.get("grossMargins"),    "percent")),
                        ("ROE",             fmt(info.get("returnOnEquity"),  "percent")),
                        ("ROA",             fmt(info.get("returnOnAssets"),  "percent")),
                    ]))
                with cb:
                    st.table(_kv([
                        ("Revenue (TTM)", fmt(info.get("totalRevenue"),      "money")),
                        ("Net Income",    fmt(info.get("netIncomeToCommon"), "money")),
                        ("EBITDA",        fmt(info.get("ebitda"),            "money")),
                        ("EPS (TTM)",     fmt(info.get("trailingEps"))),
                        ("EPS (Fwd)",     fmt(info.get("forwardEps"))),
                    ]))

            with t2:
                ca,cb = st.columns(2)
                with ca:
                    st.table(_kv([
                        ("Total Cash",    fmt(info.get("totalCash"),    "money")),
                        ("Total Debt",    fmt(info.get("totalDebt"),    "money")),
                        ("Quick Ratio",   fmt(info.get("quickRatio"))),
                        ("Current Ratio", fmt(info.get("currentRatio"))),
                    ]))
                with cb:
                    st.table(_kv([
                        ("Debt/Equity",   fmt(info.get("debtToEquity"))),
                        ("Free Cash Flow",fmt(info.get("freeCashflow"),      "money")),
                        ("Op. Cash Flow", fmt(info.get("operatingCashflow"), "money")),
                        ("Book Value/Sh", fmt(info.get("bookValue"))),
                    ]))

            with t3:
                ca,cb = st.columns(2)
                with ca:
                    st.table(_kv([
                        ("Rev Growth",       fmt(info.get("revenueGrowth"),          "percent")),
                        ("EPS Growth",       fmt(info.get("earningsGrowth"),          "percent")),
                        ("Rev/Share",        fmt(info.get("revenuePerShare"))),
                        ("Qtrly Rev Growth", fmt(info.get("quarterlyRevenueGrowth"), "percent")),
                    ]))
                with cb:
                    st.info(f"**Sector:** {sector or 'N/A'}\n\n"
                            f"**Industry:** {industry or 'N/A'}\n\n"
                            f"**Source:** {src}")

            with t4:
                st.table(_kv([
                    ("P/E (TTM)",  fmt(info.get("trailingPE"))),
                    ("P/E (Fwd)",  fmt(info.get("forwardPE"))),
                    ("PEG Ratio",  fmt(info.get("pegRatio"))),
                    ("P/S",        fmt(info.get("priceToSalesTrailing12Months"))),
                    ("P/B",        fmt(info.get("priceToBook"))),
                    ("EV/EBITDA",  fmt(info.get("enterpriseToEbitda"))),
                    ("EV/Revenue", fmt(info.get("enterpriseToRevenue"))),
                    ("1Y Target",  fmt(info.get("targetMeanPrice"))),
                ]))

            with t5:
                st.markdown("### RSI Oversold + 200 SMA Basic Backtest")
                bth = get_stock_history(ticker,"2y","1d")
                def _simple_bt(h):
                    if len(h)<252: return None
                    cl=h["Close"].copy(); d=cl.diff()
                    g=d.where(d>0,0).rolling(14).mean(); l=(-d.where(d<0,0)).rolling(14).mean()
                    rsi=100-(100/(1+g/l)); sma=cl.rolling(200).mean()
                    trades=[]; in_t=False; epx=0; eidx=0
                    for i in range(200,len(cl)):
                        if not in_t:
                            if rsi.iloc[i]<30 and cl.iloc[i]>sma.iloc[i]:
                                in_t=True; epx=cl.iloc[i]; eidx=i
                        else:
                            hd=i-eidx
                            if rsi.iloc[i]>70 or hd>=20:
                                r=(cl.iloc[i]-epx)/epx*100
                                trades.append({"e":h.index[eidx],"x":h.index[i],
                                    "ep":epx,"xp":cl.iloc[i],"r":r,"hd":hd})
                                in_t=False
                    if not trades: return None
                    df2=pd.DataFrame(trades); eq=[100.0]
                    for r in df2["r"]: eq.append(eq[-1]*(1+r/100))
                    return {"trades":df2,"total":df2["r"].sum(),
                            "win":(df2["r"]>0).mean()*100,"n":len(df2),"eq":pd.Series(eq)}
                btr = _simple_bt(bth)
                spy_ret = get_spy_benchmark("2y")
                if btr:
                    alp=btr["total"]-spy_ret
                    c1,c2,c3,c4=st.columns(4)
                    with c1: st.metric("Strategy Return",f"{btr['total']:+.1f}%",f"vs SPY {spy_ret:+.1f}%")
                    with c2: st.metric("Alpha vs SPY",f"{alp:+.1f}%",
                                       help="Excess return above S&P 500 benchmark")
                    with c3: st.metric("Win Rate",f"{btr['win']:.1f}%",
                                       help="% of trades that closed profitably")
                    with c4: st.metric("# Trades",btr["n"])
                    feq=go.Figure()
                    feq.add_trace(go.Scatter(y=btr["eq"].values,name="Strategy",
                        line=dict(color="#58a6ff",width=2),fill="tozeroy",
                        fillcolor="rgba(88,166,255,0.1)"))
                    feq.update_layout(template="plotly_dark",height=280,
                        paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                        title="Equity Curve",yaxis_title="Value",xaxis_title="Trade #")
                    st.plotly_chart(feq,use_container_width=True)
                    dt = btr["trades"].copy()
                    # Format every column to str before display.
                    # Without this, "ep"/"xp" are float64, "hd" is int64, and "r"
                    # is a formatted string — Arrow cannot serialise the mixed-type frame.
                    dt["e"]  = dt["e"].dt.strftime("%Y-%m-%d")
                    dt["x"]  = dt["x"].dt.strftime("%Y-%m-%d")
                    dt["ep"] = dt["ep"].apply(lambda v: f"${v:,.2f}")
                    dt["xp"] = dt["xp"].apply(lambda v: f"${v:,.2f}")
                    dt["r"]  = dt["r"].apply(lambda v: f"{v:+.2f}%")
                    dt["hd"] = dt["hd"].astype(str)
                    st.dataframe(
                        dt.rename(columns={"e":"Entry","x":"Exit","ep":"Entry $",
                                           "xp":"Exit $","r":"Return","hd":"Days"}),
                        use_container_width=True, hide_index=True,
                    )
                else: st.info("Insufficient data (need ≥252 trading days for backtest).")

            with t6:
                st.markdown("### 🔥 Correlation Heatmap")
                cl2, cr2 = st.columns(2)
                with cl2:
                    cdf=compute_peer_corr(ticker,tuple(peers),"1y")
                    if cdf is not None:
                        fc=px.imshow(cdf,color_continuous_scale="RdBu_r",zmin=-1,zmax=1,
                                     text_auto=".2f",title=f"Return Correlation vs Auto-Peers (1Y)")
                        fc.update_layout(template="plotly_dark",height=350,
                                         paper_bgcolor="rgba(0,0,0,0)")
                        st.plotly_chart(fc,use_container_width=True)
                    else: st.info("Could not compute correlation. Checking data availability…")
                with cr2:
                    st.markdown("### 📉 Rolling 90-Day Beta vs SPY")
                    hist_1y = get_stock_history(ticker,"1y","1d")
                    rb=compute_rolling_beta(hist_1y)
                    if rb is not None:
                        fb=go.Figure()
                        fb.add_trace(go.Scatter(x=rb.index,y=rb.values,name="Beta",
                            line=dict(color="#e3b341",width=2)))
                        fb.add_hline(y=1.0,line_dash="dot",line_color="#888",
                                     annotation_text="Beta=1")
                        fb.update_layout(template="plotly_dark",height=350,
                            paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                            yaxis_title="Rolling Beta")
                        st.plotly_chart(fb,use_container_width=True)
                        st.caption(f"Current 90-day beta vs SPY: **{rb.iloc[-1]:.2f}**")
                    else: st.info("Need ≥90 days of price history for rolling beta.")

            with t7:  render_dcf_tab(ticker, fmp_api_key=FMP_API_KEY)
            with t8:  render_relative_strength_tab(ticker, sector=sector)
            with t9:  render_backtest_tab(ticker)
            with t10: render_polymarket_tab(ticker, sector=sector)

            # ── Fair value ─────────────────────────────────────────────────────
            if show_adv:
                st.markdown("## 🎯 Fair Value Analysis")
                fv = calc_fair_value(info, hist, dg=dcf_g, dw=dcf_w)
                if fv:
                    # Earnings proximity warning inside fair value
                    if earnings and earnings.get("days_away", 999) <= 7:
                        day_str = f"{earnings['days_away']} day{'s' if earnings['days_away']!=1 else ''}"
                        st.warning(
                            f"⚠️ **UPCOMING EARNINGS — {earnings['date']} ({day_str} away)**  "
                            f"Elevated volatility expected. Bear case includes earnings-miss risk. "
                            f"Price targets shown are pre-earnings estimates."
                        )

                    c1,c2,c3,c4 = st.columns(4)
                    with c1: st.metric("Fair Value (Blended)", f"${fv['fair_value']:.2f}",
                                       help="Weighted blend: P/E model + FCF yield + conservative DCF + analyst target")
                    with c2:
                        upside_v = fv['upside']
                        st.metric("Upside to Fair Value",
                                  f"{upside_v:.1f}% {'🟢' if upside_v>0 else '🔴'}",
                                  help="(Fair Value − Current Price) ÷ Current Price")
                    with c3: st.metric("Bull Case", f"${fv['bull_case']:.2f}",
                                       help=f"Based on {fv['pe_multiple']:.0f}x × 1.15 Fwd P/E (capped)")
                    with c4: st.metric("Bear Case", f"${fv['bear_case']:.2f}",
                                       help="Based on compressed P/E multiple or 200-SMA reversion")

                    r40   = fv["rule_of_40"]
                    r40c  = "🟢" if r40>=40 else "🟡" if r40>=20 else "🔴"
                    _dcfs = f"${fv['dcf_model']:.2f}" if fv["dcf_model"] else "N/A"

                    # Transparency caption
                    adj_note = " ⚠️ *Analyst-adjusted* (model deviated >20% from consensus)" if fv.get("analyst_adj") else ""
                    cap_note = "🏔️ Mega-cap P/E cap (35x) applied" if fv.get("is_megacap") else ""
                    st.caption(
                        f"📐 **Calculated using:** {fv['method']}"
                        + (f"  ·  {adj_note}" if adj_note else "")
                        + (f"  ·  {cap_note}" if cap_note else "")
                    )
                    at_str = f"${fv['analyst_target']:.2f}" if fv['analyst_target'] else "N/A"
                    st.info(
                        f"**Rule of 40: {r40:.1f}%** {r40c}  |  "
                        f"P/E Model: ${fv['peg_model']:.2f}  |  "
                        f"FCF Model: ${fv['fcf_model']:.2f}  |  "
                        f"DCF (capped): {_dcfs}  |  "
                        f"Analyst Target: {at_str}"
                    )
                else:
                    fv = None

            # ── Competitive landscape ──────────────────────────────────────────
            st.markdown("## 🏁 Competitive Landscape")
            st.caption(f"Auto-detected peers: {', '.join(peers)}")
            crows = []
            for pt in [ticker]+peers:
                try:
                    pi = get_stock_info(pt)
                    crows.append({"Ticker":pt,"Price":f"${float(pi.get('currentPrice',0)):.2f}",
                        "Mkt Cap":fmt(pi.get("marketCap"),"money"),
                        "Fwd P/E":fmt(pi.get("forwardPE")),
                        "ROE":fmt(pi.get("returnOnEquity"),"percent"),
                        "Profit Margin":fmt(pi.get("profitMargins"),"percent"),
                        "Rev Growth":fmt(pi.get("revenueGrowth"),"percent"),
                        "Beta":fmt(pi.get("beta"))})
                except: continue
            if crows: st.dataframe(pd.DataFrame(crows),use_container_width=True,hide_index=True)

            st.markdown("---")

            # ── News sentiment ─────────────────────────────────────────────────
            st.markdown("## 📰 Market Intelligence")
            with st.spinner("Fetching news and AI sentiment…"):
                cname = info.get("longName","")
                news  = get_news_sentiment(ticker, cname)

            bull_n=sum(1 for n in news if n["sentiment"]=="Bullish")
            bear_n=sum(1 for n in news if n["sentiment"]=="Bearish")
            neut_n=sum(1 for n in news if n["sentiment"]=="Neutral")
            breaking_n = sum(1 for n in news if n.get("breaking"))

            if news:
                scores = [n["score"] for n in news]
                avg = sum(s if news[i]["sentiment"]=="Bullish" else
                          (1-s) if news[i]["sentiment"]=="Bearish" else 0.5
                          for i,s in enumerate(scores)) / len(scores)
                c1,c2,c3,c4,c5 = st.columns(5)
                with c1: st.metric("🟢 Bullish", bull_n,
                                   help="Headlines scored as bullish by AI")
                with c2: st.metric("🔴 Bearish", bear_n,
                                   help="Headlines scored as bearish by AI")
                with c3: st.metric("🟡 Neutral", neut_n,
                                   help="Headlines scored as neutral by AI")
                with c4: st.metric("Sentiment", f"{avg:.0%}",
                                   help="Weighted average sentiment score")
                with c5: st.metric("🚨 Breaking", breaking_n,
                                   help="Headlines published in the last 12 hours")

                if breaking_n:
                    st.warning(f"🚨 **{breaking_n} breaking headline(s)** detected in the last 12 hours — included in AI analysis as priority signals.")

                for item in news:
                    icon={"Bullish":"🟢","Bearish":"🔴","Neutral":"🟡"}.get(item.get("sentiment"),"⚪")
                    breaking_tag = " 🚨 **BREAKING**" if item.get("breaking") else ""
                    hrs = item.get("hours_ago")
                    time_tag = f" · {hrs:.0f}h ago" if hrs is not None and hrs < 48 else f" · {item.get('published','N/A')}"
                    with st.expander(f"{icon}{breaking_tag} {item.get('title','No Title')}"):
                        ca2,cb2 = st.columns([3,1])
                        with ca2:
                            st.markdown(f"**Source:** {item.get('publisher','N/A')}{time_tag}")
                            if item.get("reason"):
                                st.markdown(f"**AI Assessment:** {item['reason']}")
                        with cb2:
                            st.markdown(f"**{icon} {item.get('sentiment','?')}")
                            st.progress(float(item.get("score",0.5)),
                                        text=f"Conviction: {item.get('score',0.5):.0%}")
                        st.markdown(f"[🔗 Read Article]({item.get('link','#')})")
            else:
                news = []; st.warning("No recent news found.")

            st.markdown("---")

            # ── AI Agent Verdict (four-source synthesis) ──────────────────────
            if show_ai:
                st.markdown("## 🤖 AI Agent — Institutional Verdict")
                st.caption(
                    "Synthesises: (1) live financial data, "
                    "(2) ultra-fresh news with breaking alerts, "
                    "(3) earnings proximity & volatility context, "
                    "(4) Polymarket prediction odds."
                )
                with st.spinner("AI agent reasoning across all four sources…"):
                    try:
                        fv2 = calc_fair_value(info, hist, dg=dcf_g, dw=dcf_w)
                        verdict = run_ai_agent(
                            ticker=ticker, info=info, hist=hist,
                            news=news, indicators=indicators,
                            fv=fv2, earnings=earnings,
                            dcf_g=dcf_g, dcf_w=dcf_w,
                        )
                        st.markdown(
                            f'''<div class="agent-verdict">{verdict}</div>''',
                            unsafe_allow_html=True,
                        )
                        cs1, cs2 = st.columns(2)
                        with cs1:
                            if st.button("💾 Save to Watchlist", key="sv_wl"):
                                wm.add(USER_ID, ticker)
                                st.success(f"✅ {ticker} added to watchlist!")
                        with cs2:
                            if st.button("📝 Add to Portfolio", key="sv_pt"):
                                st.session_state["active_page"] = "💼 Portfolio"
                                st.rerun()
                    except Exception as e:
                        st.error(f"AI agent unavailable: {e}")

            st.markdown("---")
            st.caption(f"Analysis completed {datetime.now():%Y-%m-%d %H:%M:%S} · Whale Terminal Elite v7.0")

        except Exception as e:
            st.error(f"Analysis error: {e}")
            import traceback; st.code(traceback.format_exc())
            st.info("Verify ticker symbol and internet connection.")


# =============================================================================
# PAGE: GLOBAL NEWS
# =============================================================================
def page_news():
    st.markdown(
        '''<div class="page-title">📰 Global Financial News</div>
        <p style="color:#8b949e;margin-bottom:24px;">
        Top market-moving headlines with AI-powered sentiment analysis.</p>''',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns([4,1])
    with c1:
        query_input = st.text_input("Search topic",
            value="stock market finance economy Fed interest rates",
            placeholder="e.g. Fed rate cut, tech earnings, oil market",
            help="Keywords to search. Try specific topics like 'NVDA AI chips'")
    with c2:
        fetch_btn = st.button("🔄 Fetch", type="primary",
                              use_container_width=True, key="news_fetch")

    if not fetch_btn and not st.session_state.get("news_fetched"):
        st.info("Click **🔄 Fetch** to load the latest financial headlines.")
        return

    st.session_state["news_fetched"] = True

    arts: list[dict] = []
    if NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/everything",
                params={"q":query_input,"language":"en","sortBy":"publishedAt",
                        "pageSize":12,"apiKey":NEWS_API_KEY},
                timeout=8).json()
            if r.get("status")=="ok":
                arts = r.get("articles",[])[:12]
        except: pass
    if not arts:
        st.warning(
            "⚠️ No articles returned. Ensure **NEWS_API_KEY** is set in your secrets.  \n"
            "Add it to `.streamlit/secrets.toml`:\n```toml\nNEWS_API_KEY = \"your_key\"\n```"
        )
        return

    # AI scoring
    enriched: list[dict] = []
    with st.spinner(f"Scoring {len(arts)} headlines with AI…"):
        for a in arts:
            if llm is None:
                a["sentiment"]="Neutral"; a["score"]=0.5
                a["reason"]="AI unavailable — configure GROQ_API_KEY in secrets"
            else:
                try:
                    raw = llm.invoke(
                        'Return ONLY valid JSON (no backticks): {"sentiment":"Bullish|Bearish|Neutral",'
                        '"score":0.0-1.0,"reason":"one sentence"} Headline: ' + repr(a.get('title',''))
                    ).content.strip().replace("```json","").replace("```","").strip()
                    d = json.loads(raw); s = d.get("sentiment","Neutral")
                    a["sentiment"] = s if s in ("Bullish","Bearish","Neutral") else "Neutral"
                    a["score"]     = float(d.get("score",0.5)); a["reason"] = d.get("reason","")
                except:
                    a["sentiment"]="Neutral"; a["score"]=0.5; a["reason"]=""
            enriched.append(a)

    bc  = sum(1 for x in enriched if x["sentiment"]=="Bullish")
    nc  = sum(1 for x in enriched if x["sentiment"]=="Neutral")
    brc = sum(1 for x in enriched if x["sentiment"]=="Bearish")
    c1,c2,c3 = st.columns(3)
    with c1: st.metric("🟢 Bullish", bc,  help="Positive market headlines")
    with c2: st.metric("🟡 Neutral", nc,  help="Neutral market headlines")
    with c3: st.metric("🔴 Bearish", brc, help="Negative market headlines")
    st.markdown("---")

    for item in enriched:
        icon = {"Bullish":"🟢","Bearish":"🔴","Neutral":"🟡"}.get(item.get("sentiment"),"⚪")
        pub  = (item.get("publishedAt","")[:10] or item.get("published",""))
        src  = (item.get("source",{}).get("name","") or item.get("publisher",""))
        url  = item.get("url","") or item.get("link","#")
        with st.container():
            st.markdown(f"""<div class="info-card gold-accent">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <span style="font-size:1.0rem;font-weight:700;color:#f0f6fc;">
                  {icon} {item.get('title','')}
                </span>
                <span style="color:#8b949e;font-size:0.78rem;white-space:nowrap;margin-left:16px;min-width:140px;text-align:right;">
                  {src} · {pub}
                </span>
              </div>
              <div style="color:#8b949e;margin-top:6px;font-size:0.87rem;">{item.get('reason','')}</div>
              <a href="{url}" target="_blank"
                 style="color:#58a6ff;text-decoration:none;font-size:0.83rem;">🔗 Read full article</a>
            </div>""", unsafe_allow_html=True)


# =============================================================================
# PAGE: SETTINGS
# =============================================================================
def page_settings():
    st.markdown('''<div class="page-title">⚙️ Settings</div>''', unsafe_allow_html=True)

    with st.expander("👤 User Profile", expanded=True):
        st.markdown(f"**Email:** `{USER_EMAIL}`")
        st.markdown(f"**User ID:** `{USER_ID}`")
        st.markdown(f"**Auth mode:** {'☁️ Supabase' if auth.is_connected else '💾 Demo / session-only'}")
        if st.button("🚪 Sign Out", key="settings_signout"):
            auth.sign_out(); st.rerun()

    with st.expander("🔑 API Keys Status", expanded=True):
        st.caption(
            "Secrets are loaded from `st.secrets` (Streamlit Cloud or "
            "`.streamlit/secrets.toml` locally). "
            "Never commit keys to Git."
        )
        key_rows = [
            ("Groq LLM (AI analysis)",       "GROQ_API_KEY",    GROQ_API_KEY,   True),
            ("Financial Modeling Prep",      "FMP_API_KEY",     FMP_API_KEY,    True),
            ("NewsAPI",                      "NEWS_API_KEY",    NEWS_API_KEY,   True),
            ("Supabase URL",                 "SUPABASE_URL",    SUPABASE_URL,   True),
            ("Supabase Anon Key",            "SUPABASE_ANON_KEY", SUPABASE_KEY, True),
            ("Alpaca Key (paper trading)",   "ALPACA_KEY",      ALPACA_KEY,     False),
            ("Alpaca Secret (paper trading)","ALPACA_SECRET",   ALPACA_SECRET,  False),
        ]
        for label, key, val, required in key_rows:
            if val:
                st.success(f"✅ **{label}** — configured", icon="🔐")
            elif required:
                st.error(
                    f"❌ **{label}** — missing  \n"
                    f"Add `{key} = \"...\"` to your secrets.",
                    icon="⚠️",
                )
            else:
                st.info(f"➖ **{label}** — not set (optional feature disabled)", icon="ℹ️")

        st.markdown("---")
        st.markdown("**How to configure secrets:**")
        st.code("""\
# .streamlit/secrets.toml  (local dev)
GROQ_API_KEY       = "gsk_..."
FMP_API_KEY        = "your_fmp_key"
NEWS_API_KEY       = "your_newsapi_key"
SUPABASE_URL       = "https://xxxx.supabase.co"
SUPABASE_ANON_KEY  = "eyJ..."
ALPACA_KEY         = ""   # optional
ALPACA_SECRET      = ""   # optional
""", language="toml")
        st.caption(
            "On Streamlit Cloud: go to **App → Settings → Secrets** "
            "and paste the same key=value pairs."
        )

    with st.expander("🗄️ Supabase Database Setup"):
        st.markdown("Run these once in your Supabase SQL editor:")
        st.code("""
CREATE TABLE IF NOT EXISTS watchlists (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    ticker      TEXT        NOT NULL,
    note        TEXT        DEFAULT '',
    alert_price NUMERIC,
    added_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, ticker)
);
CREATE TABLE IF NOT EXISTS portfolios (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    ticker      TEXT        NOT NULL,
    buy_price   NUMERIC     NOT NULL,
    quantity    NUMERIC     NOT NULL,
    sector      TEXT        DEFAULT '',
    added_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, ticker)
);
ALTER TABLE watchlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;
        """, language="sql")

    with st.expander("🔮 Polymarket Integration Info"):
        st.markdown("""
**How it works:** The Prediction Market tab uses Polymarket's public Gamma API
(`gamma-api.polymarket.com/markets`). No API key required.

**Rate limits:** ~30 req/min. Results are cached for 5 minutes.

**Data shown:**
- **YES probability**: crowd-implied chance the event occurs
- **NO probability**: implied chance it does NOT occur
- **Volume**: total $USDC traded (proxy for confidence)

[Browse Polymarket →](https://polymarket.com)
        """)

    with st.expander("🎨 Display Preferences"):
        st.info("Preferences reset on page reload. Persistent storage requires Supabase.")
        adv_default = st.session_state.get("show_advanced",True)
        ai_default  = st.session_state.get("show_ai_verdict",True)
        if st.toggle("Show Advanced Analytics",value=adv_default,key="pref_adv"):
            st.session_state["show_advanced"]=True
        else:
            st.session_state["show_advanced"]=False
        if st.toggle("Show AI Agent Verdict",value=ai_default,key="pref_ai"):
            st.session_state["show_ai_verdict"]=True
        else:
            st.session_state["show_ai_verdict"]=False

    st.markdown("---")
    st.caption(
        "Whale Terminal Elite v8.0 | Built with Streamlit · Plotly · FMP · "
        "Groq LLaMA 3.3 · Supabase · Polymarket"
    )


# =============================================================================
# MAIN ROUTER
# =============================================================================
active = st.session_state["active_page"]

if   active == "🏠 Home":            page_home()
elif active == "🔍 Stock Analysis":  page_analysis(run_analysis)
elif active == "👀 Watchlist":       render_watchlist_page(wm, USER_ID)
elif active == "💼 Portfolio":       portmgr.render_page(USER_ID, fmp_api_key=FMP_API_KEY)
elif active == "📰 Global News":     page_news()
elif active == "⚙️ Settings":        page_settings()
