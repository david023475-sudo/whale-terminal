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

# ===================== CONFIG — secrets via st.secrets =======================
# Helper: st.secrets first, os.environ second, empty string default
def _secret(key: str, default: str = "") -> str:
    """
    Priority:
      1. st.secrets[key]   — Streamlit Cloud / .streamlit/secrets.toml
      2. os.environ[key]   — Docker / local env vars
      3. default           — empty string (feature degrades gracefully)
    Never raises; missing secrets disable features without crashing.
    """
    try:
        return str(st.secrets[key])
    except (KeyError, FileNotFoundError):
        pass
    return os.environ.get(key, default)

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
        llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0)
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
    if st.button("🚪 Sign Out",use_container_width=True,key="so_btn"):
        auth.sign_out(); st.rerun()
    st.markdown(
        "<div style='text-align:center;color:#3d4a5c;font-size:0.72rem;margin-top:16px;'>"
        "Whale Terminal Elite v7.0<br>Institutional Intelligence</div>",
        unsafe_allow_html=True,
    )

# =============================================================================
# SHARED DATA HELPERS — FMP only, yfinance fully removed
# =============================================================================
RANGE_MAP = {
    "1D":{"period":"1d","interval":"5m"},  "5D":{"period":"5d","interval":"15m"},
    "1M":{"period":"1mo","interval":"1d"}, "3M":{"period":"3mo","interval":"1d"},
    "6M":{"period":"6mo","interval":"1d"}, "1Y":{"period":"1y","interval":"1d"},
    "2Y":{"period":"2y","interval":"1wk"}, "5Y":{"period":"5y","interval":"1wk"},
}
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"

def _fmp_get(path: str, params: dict | None = None) -> list | dict | None:
    """Central FMP request helper — injects API key, returns parsed JSON or None."""
    if not FMP_API_KEY:
        return None
    try:
        p = {"apikey": FMP_API_KEY}
        if params:
            p.update(params)
        r = requests.get(f"{FMP_BASE_URL}{path}", params=p, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

# ── Stock info ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_stock_info(ticker: str) -> dict:
    """
    Fetch company profile + key metrics from FMP.
    Merges /profile, /key-metrics-ttm, and /financial-growth
    into a yfinance-compatible key dict so the rest of the UI needs no changes.
    No yfinance fallback — FMP is the sole source.
    """
    if not FMP_API_KEY:
        st.warning("⚠️ **FMP_API_KEY** not configured — stock data unavailable.")
        return {}

    profile_data = _fmp_get(f"/profile/{ticker}")
    if not profile_data or not isinstance(profile_data, list):
        st.error(f"❌ Could not fetch profile for **{ticker}**. Check the ticker symbol.")
        return {}
    p = profile_data[0]

    # Key-metrics TTM gives richer ratios (P/E, P/B, EV/EBITDA, etc.)
    km: dict = {}
    km_data = _fmp_get(f"/key-metrics-ttm/{ticker}")
    if km_data and isinstance(km_data, list) and km_data:
        km = km_data[0]

    # Financial-growth gives revenue/earnings growth rates
    gr: dict = {}
    gr_data = _fmp_get(f"/financial-growth/{ticker}", {"limit": 1})
    if gr_data and isinstance(gr_data, list) and gr_data:
        gr = gr_data[0]

    # Parse "low-high" range string safely
    wk52_high = wk52_low = None
    for raw_range in [p.get("range", "") or ""]:
        if "-" in raw_range:
            parts = raw_range.split("-")
            try:
                wk52_low  = float(parts[0])
                wk52_high = float(parts[-1])
            except (ValueError, IndexError):
                pass

    def _f(v):
        """Safe float or None."""
        try: return float(v) if v is not None else None
        except: return None

    def _pct(v):
        """FMP stores some margins as 0-100; convert to 0-1 decimals (yfinance convention)."""
        try: return float(v) / 100 if v is not None else None
        except: return None

    return {
        # ── Identity
        "symbol":   p.get("symbol"),
        "longName": p.get("companyName"),
        "sector":   p.get("sector"),
        "industry": p.get("industry"),
        "longBusinessSummary": p.get("description", ""),
        "website":  p.get("website", ""),
        "country":  p.get("country", ""),
        "fullTimeEmployees": _f(p.get("fullTimeEmployees")),
        # ── Price
        "currentPrice":  _f(p.get("price")),
        "previousClose": _f(p.get("price")),   # FMP profile has no separate prev-close
        "open":          _f(p.get("price")),
        "volume":        _f(p.get("volAvg")),
        "marketCap":     _f(p.get("mktCap")),
        "beta":          _f(p.get("beta")),
        "fiftyTwoWeekHigh": wk52_high,
        "fiftyTwoWeekLow":  wk52_low,
        # ── Valuation — key-metrics-ttm preferred over profile
        "trailingPE":  _f(km.get("peRatioTTM")              or p.get("pe")),
        "forwardPE":   _f(km.get("peRatioTTM")              or p.get("pe")),
        "pegRatio":    _f(km.get("pegRatioTTM")             or p.get("peg")),
        "priceToSalesTrailing12Months": _f(km.get("priceToSalesRatioTTM") or p.get("priceToSalesRatio")),
        "priceToBook": _f(km.get("pbRatioTTM")              or p.get("ptb")),
        "enterpriseToEbitda":  _f(km.get("enterpriseValueOverEBITDATTM")),
        "enterpriseToRevenue": _f(km.get("evToSalesRatioTTM")),
        # ── Earnings
        "trailingEps":     _f(p.get("eps")),
        "forwardEps":      _f(p.get("eps")),
        "targetMeanPrice": _f(p.get("dcf")),   # FMP DCF fair value used as analyst target proxy
        # ── Profitability (0-1 decimals, matching yfinance convention)
        "profitMargins":    _pct(p.get("netProfitMargin")),
        "operatingMargins": _pct(p.get("operatingProfitMargin")),
        "grossMargins":     _f(p.get("grossProfitRatio")),   # already 0-1 in FMP
        "returnOnEquity":   _pct(p.get("roe")),
        "returnOnAssets":   _pct(p.get("roa")),
        # ── Balance sheet
        "totalDebt":    _f(p.get("totalDebt")),
        "totalCash":    _f(p.get("cash")),
        "debtToEquity": _f(p.get("debtToEquity")),
        "quickRatio":   _f(km.get("quickRatioTTM")),
        "currentRatio": _f(km.get("currentRatioTTM")),
        "bookValue":    _f(km.get("bookValuePerShareTTM")),
        # ── Cash flow
        "freeCashflow": (
            float(p.get("freeCashFlowPerShare") or 0) *
            float(p.get("sharesOutstanding")    or 1)
        ) if p.get("freeCashFlowPerShare") else None,
        "operatingCashflow": None,  # not in profile; DCF tab fetches via statement endpoint
        # ── Revenue / growth
        "totalRevenue":    _f(p.get("revenue")),
        "revenuePerShare": _f(km.get("revenuePerShareTTM")),
        "revenueGrowth":   _f(gr.get("revenueGrowth")),   # already 0-1 decimal
        "earningsGrowth":  _f(gr.get("netIncomeGrowth")),
        "quarterlyRevenueGrowth": _f(gr.get("revenueGrowth")),
        # ── Income (not in profile — populated by statement endpoints elsewhere)
        "ebitda":            None,
        "netIncomeToCommon": None,
        # ── Shares
        "sharesOutstanding": _f(p.get("sharesOutstanding")),
        "_source": "FMP",
    }


# ── OHLCV history ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_history(ticker: str, period: str, interval: str) -> "pd.DataFrame":
    """
    Fetch OHLCV from FMP — no yfinance.
    Intraday (5m/15m) → /historical-chart/{interval}/{ticker}
    Daily/weekly      → /historical-price-full/{ticker}
    Returns a tz-naive DataFrame with columns Open, High, Low, Close, Volume.
    """
    empty = pd.DataFrame()
    if not FMP_API_KEY:
        return empty

    # ── Intraday ──────────────────────────────────────────────────────────────
    if interval in ("5m","15m","30m","1h"):
        data = _fmp_get(f"/historical-chart/{interval}/{ticker}")
        if not data or not isinstance(data, list):
            return empty
        df = (pd.DataFrame(data)
              .rename(columns={"date":"Date","open":"Open","high":"High",
                                "low":"Low","close":"Close","volume":"Volume"}))
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        # Trim to the look-back window
        cutoff = {"1d": 1, "5d": 5}.get(period, 1)
        df = df[df.index >= df.index[-1] - pd.Timedelta(days=cutoff)]
        return df[["Open","High","Low","Close","Volume"]].dropna()

    # ── Daily / weekly ────────────────────────────────────────────────────────
    period_days = {"1mo":31,"3mo":92,"6mo":183,"1y":365,"2y":730,"5y":1825}
    days = period_days.get(period, 365)
    from_date = (datetime.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")

    data = _fmp_get(f"/historical-price-full/{ticker}", {"from": from_date})
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
    Fetch real-time quote for one or more tickers via FMP /quote/{symbols}.
    Returns {TICKER: quote_dict}. Uses tuple arg so it is hashable for cache.
    """
    if not FMP_API_KEY or not tickers:
        return {}
    symbols = ",".join(tickers)
    data = _fmp_get(f"/quote/{symbols}")
    if not data or not isinstance(data, list):
        return {}
    return {item["symbol"]: item for item in data if "symbol" in item}


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
    Fetch the next earnings announcement date from FMP (preferred) or yfinance.
    Returns dict with keys: date (str YYYY-MM-DD), days_away (int), is_soon (bool),
    expected_move_pct (float | None), time_of_day (str).
    Returns None if no upcoming earnings found.
    """
    today = datetime.now().date()

    # ── Strategy 1: FMP earnings calendar ────────────────────────────────────
    if fmp_api_key:
        try:
            from_d = today.strftime("%Y-%m-%d")
            to_d   = (today + pd.Timedelta(days=90)).strftime("%Y-%m-%d")
            r = requests.get(
                f"https://financialmodelingprep.com/api/v3/earning_calendar",
                params={"from": from_d, "to": to_d, "apikey": fmp_api_key},
                timeout=8,
            ).json()
            if isinstance(r, list):
                for item in r:
                    if str(item.get("symbol","")).upper() == ticker.upper():
                        edate_str = item.get("date","")
                        if edate_str:
                            edate = datetime.strptime(edate_str[:10], "%Y-%m-%d").date()
                            days_away = (edate - today).days
                            if days_away >= 0:
                                eps_est = item.get("epsEstimated")
                                time_str = item.get("time","") or "Unknown"
                                return {
                                    "date": edate.strftime("%b %d, %Y"),
                                    "date_raw": edate_str[:10],
                                    "days_away": days_away,
                                    "is_soon": days_away <= 14,
                                    "is_imminent": days_away <= 3,
                                    "eps_estimate": eps_est,
                                    "time_of_day": time_str,
                                    "source": "FMP",
                                }
        except: pass

    # ── Strategy 2: FMP historical earnings calendar (wider look-ahead) ──────
    # The /earning_calendar endpoint uses a date range. If it returned nothing
    # (e.g. ticker not found in that window), try the per-ticker history list.
    if fmp_api_key:
        try:
            data = _fmp_get(f"/historical/earning_calendar/{ticker}")
            if isinstance(data, list):
                for item in data:
                    edate_str = item.get("date", "")
                    if not edate_str:
                        continue
                    edate     = datetime.strptime(edate_str[:10], "%Y-%m-%d").date()
                    days_away = (edate - today).days
                    if 0 <= days_away <= 120:
                        return {
                            "date":        edate.strftime("%b %d, %Y"),
                            "date_raw":    edate_str[:10],
                            "days_away":   days_away,
                            "is_soon":     days_away <= 14,
                            "is_imminent": days_away <= 3,
                            "eps_estimate":item.get("epsEstimated"),
                            "time_of_day": item.get("time", "Unknown") or "Unknown",
                            "source": "FMP-history",
                        }
        except:
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
    try:
        c=hist["Close"]; d=c.diff()
        g=d.where(d>0,0).rolling(14).mean(); l=(-d.where(d<0,0)).rolling(14).mean()
        rsi=100-(100/(1+g/l))
        e1=c.ewm(span=12,adjust=False).mean(); e2=c.ewm(span=26,adjust=False).mean()
        macd=e1-e2; sig=macd.ewm(span=9,adjust=False).mean()
        s20=c.rolling(20).mean(); std20=c.rolling(20).std()
        return {"rsi":rsi.iloc[-1],"macd":macd.iloc[-1],"signal":sig.iloc[-1],
                "bb_upper":(s20+std20*2).iloc[-1],"bb_lower":(s20-std20*2).iloc[-1],
                "sma_20":s20.iloc[-1],"sma_50":c.rolling(50).mean().iloc[-1],
                "sma_200":c.rolling(200).mean().iloc[-1]}
    except: return None

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

        # ── 4. BLEND ──────────────────────────────────────────────────────────
        if dcfv:
            raw_fv = m_pe * 0.35 + m_fcf * 0.25 + dcfv * 0.25 + (at or m_pe) * 0.15
        else:
            raw_fv = m_pe * 0.45 + m_fcf * 0.25 + (at or m_pe) * 0.30

        # Quality premium: modest, capped at 8%
        qm     = 1.08 if roe > 0.40 else 1.04 if roe > 0.25 else 1.0
        raw_fv = raw_fv * qm

        # ── 5. ANALYST GUARDRAIL ─────────────────────────────────────────────
        analyst_adj = False
        if at and at > 0:
            dev = (raw_fv - at) / at          # positive = model higher than analyst
            if abs(dev) > 0.20:
                # Pull 50% toward analyst consensus
                raw_fv      = raw_fv * 0.50 + at * 0.50
                analyst_adj = True

        fv = raw_fv

        # ── 6. BULL / BEAR — P/E anchored, capped ────────────────────────────
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

        # ── 7. UPSIDE — relative to current price ────────────────────────────
        upside = ((fv / cp) - 1) * 100

        # ── 8. TRANSPARENCY METADATA ─────────────────────────────────────────
        method_parts = [
            f"{pe_mult:.0f}x Fwd P/E",
            f"{tg*100:.1f}% terminal growth",
        ]
        if analyst_adj:
            method_parts.append("analyst-adjusted (>20% deviation)")
        if is_megacap:
            method_parts.append("mega-cap P/E cap applied")
        method_str = " · ".join(method_parts)

        return {
            "fair_value":     fv,
            "peg_model":      m_pe,
            "fcf_model":      m_fcf,
            "dcf_model":      dcfv,
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

    financial_data = {
        "ticker":           ticker,
        "currentPrice":     round(cp, 2),
        "fiftyTwoWeekHigh": fmt(h52),
        "fiftyTwoWeekLow":  fmt(l52),
        "nearAllTimeHigh":  near_ath,
        "ATR_14d":          f"${atr:.2f}" if atr else "N/A",
        "marketCap":        fmt(info.get("marketCap"), "money"),
        "forwardPE":        fmt(info.get("forwardPE")),
        "trailingPE":       fmt(info.get("trailingPE")),
        "pegRatio":         fmt(info.get("pegRatio")),
        "forwardEps":       fmt(info.get("forwardEps")),
        "trailingEps":      fmt(info.get("trailingEps")),
        "revenueGrowth":    fmt(info.get("revenueGrowth"),   "percent"),
        "earningsGrowth":   fmt(info.get("earningsGrowth"),  "percent"),
        "profitMargins":    fmt(info.get("profitMargins"),   "percent"),
        "operatingMargins": fmt(info.get("operatingMargins"),"percent"),
        "returnOnEquity":   fmt(info.get("returnOnEquity"),  "percent"),
        "freeCashflow":     fmt(info.get("freeCashflow"),    "money"),
        "debtToEquity":     fmt(info.get("debtToEquity")),
        "beta":             fmt(info.get("beta")),
        "RSI_14":           f"{rsi_v:.2f}" if isinstance(rsi_v,float) else "N/A",
        "MACD_bias":        ("Bullish" if indicators and indicators["macd"]>indicators["signal"] else "Bearish") if indicators else "N/A",
        "trend_200SMA":     ("Above" if cp>sma200 else "Below") if sma200 else "N/A",
        "SMA_200":          f"${sma200:.2f}" if sma200 else "N/A",
        "analystTarget":    fmt(info.get("targetMeanPrice")),
        "blendedFairValue": f"${fv['fair_value']:.2f}" if fv else "N/A",
        "fairValueUpside":  f"{fv['upside']:.1f}%" if fv else "N/A",
        "DCF_value":        f"${fv['dcf_model']:.2f}" if fv and fv.get("dcf_model") else "N/A",
        "bullCase":         f"${fv['bull_case']:.2f}" if fv else "N/A",
        "bearCase":         f"${fv['bear_case']:.2f}" if fv else "N/A",
        "peMultiple":       f"{fv['pe_multiple']:.0f}x" if fv else "N/A",
        "terminalGrowth":   f"{fv['terminal_growth']:.1f}%" if fv else "N/A",
        "analystAdjusted":  fv.get("analyst_adj", False) if fv else False,
        "isMegaCap":        fv.get("is_megacap", False) if fv else False,
        "sector":           info.get("sector","N/A"),
        "industry":         info.get("industry","N/A"),
    }

    # ── Source 2: news (include breaking flag) ────────────────────────────────
    news_summary = []
    for n in news[:8]:
        entry = {
            "headline":  n.get("title",""),
            "sentiment": n.get("sentiment","Neutral"),
            "score":     round(n.get("score",0.5),2),
            "reason":    n.get("reason",""),
            "date":      n.get("published",""),
            "breaking":  n.get("breaking",False),
        }
        if n.get("hours_ago") is not None:
            entry["hours_ago"] = f"{n['hours_ago']:.1f}h ago"
        news_summary.append(entry)

    bull_n = sum(1 for n in news if n.get("sentiment")=="Bullish")
    bear_n = sum(1 for n in news if n.get("sentiment")=="Bearish")
    breaking_count = sum(1 for n in news if n.get("breaking"))
    news_summary_obj = {
        "headlines":       news_summary,
        "summary":         f"{bull_n} Bullish / {bear_n} Bearish / {len(news)-bull_n-bear_n} Neutral",
        "breaking_alerts": breaking_count,
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
    prompt = AGENT_PROMPT.format(
        date=datetime.now().strftime("%B %d, %Y"),
        financial_data=json.dumps(financial_data, indent=2),
        news_data=json.dumps(news_summary_obj, indent=2),
        earnings_data=json.dumps(earnings_data, indent=2),
        prediction_data=json.dumps(prediction_data, indent=2),
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
        search = st.text_input("", placeholder="🔍  Search ticker — e.g. AAPL, TSLA, NVDA…",
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

            # ── Candlestick chart — interactive with toggleable indicators ──────
            st.markdown("## 📊 Technical Analysis")
            indicators = calc_rsi_macd_bb(hist)

            # Indicator toggle controls — stored in session_state so they survive reruns
            ind_defaults = st.session_state.get("chart_indicators", ["SMA 50","SMA 200"])
            ind_col1, ind_col2 = st.columns([3, 1])
            with ind_col1:
                chosen_inds = st.multiselect(
                    "📐 Overlay Indicators",
                    options=["SMA 20","SMA 50","SMA 200","Bollinger Bands","VWAP"],
                    default=ind_defaults,
                    key="chart_indicators",
                    help="Select indicators to overlay on the price chart",
                )
            with ind_col2:
                show_studies = st.checkbox(
                    "RSI + MACD panels",
                    value=st.session_state.get("chart_show_studies", True),
                    key="chart_show_studies",
                    help="Show RSI and MACD charts below the price chart",
                )

            # Build subplot layout dynamically
            n_rows   = 2 + (2 if show_studies else 0)   # price, volume, [rsi, macd]
            row_h    = [0.52, 0.13]
            if show_studies:
                row_h += [0.18, 0.17]
            titles   = [f"{ticker} — Price & Volume", ""]
            if show_studies:
                titles += ["RSI (14)", "MACD"]

            fig = make_subplots(
                rows=n_rows, cols=1,
                row_heights=row_h,
                vertical_spacing=0.03,
                subplot_titles=titles,
                shared_xaxes=True,
            )

            # ── Row 1: Candlesticks ────────────────────────────────────────────
            fig.add_trace(go.Candlestick(
                x=hist.index, open=hist["Open"], high=hist["High"],
                low=hist["Low"], close=hist["Close"], name="OHLC",
                increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
                increasing_fillcolor="#26a69a", decreasing_fillcolor="#ef5350",
            ), row=1, col=1)

            # ── Overlay indicators ────────────────────────────────────────────
            if indicators:
                sma_specs = {
                    "SMA 20":  (20,  "#58a6ff", "dot",   1.5),
                    "SMA 50":  (50,  "#f78166", "solid", 1.8),
                    "SMA 200": (200, "#e3b341", "dash",  2.0),
                }
                for label, (window, color, dash, width) in sma_specs.items():
                    if label in chosen_inds:
                        sma = hist["Close"].rolling(window).mean()
                        if not pd.isna(sma.iloc[-1]):
                            fig.add_trace(go.Scatter(
                                x=hist.index, y=sma, name=label,
                                line=dict(color=color, width=width, dash=dash),
                                hovertemplate=f"{label}: $%{{y:.2f}}<extra></extra>",
                            ), row=1, col=1)

                if "Bollinger Bands" in chosen_inds:
                    s20   = hist["Close"].rolling(20).mean()
                    std20 = hist["Close"].rolling(20).std()
                    bb_u  = s20 + std20 * 2
                    bb_l  = s20 - std20 * 2
                    fig.add_trace(go.Scatter(
                        x=hist.index, y=bb_u, name="BB Upper",
                        line=dict(color="rgba(168,168,255,0.6)", width=1, dash="dot"),
                        hovertemplate="BB Upper: $%{y:.2f}<extra></extra>",
                    ), row=1, col=1)
                    fig.add_trace(go.Scatter(
                        x=hist.index, y=bb_l, name="BB Lower",
                        line=dict(color="rgba(168,168,255,0.6)", width=1, dash="dot"),
                        fill="tonexty", fillcolor="rgba(168,168,255,0.04)",
                        hovertemplate="BB Lower: $%{y:.2f}<extra></extra>",
                    ), row=1, col=1)

                if "VWAP" in chosen_inds and "Volume" in hist.columns:
                    try:
                        tp   = (hist["High"] + hist["Low"] + hist["Close"]) / 3
                        vwap = (tp * hist["Volume"]).cumsum() / hist["Volume"].cumsum()
                        fig.add_trace(go.Scatter(
                            x=hist.index, y=vwap, name="VWAP",
                            line=dict(color="#a371f7", width=2),
                            hovertemplate="VWAP: $%{y:.2f}<extra></extra>",
                        ), row=1, col=1)
                    except: pass

            # Earnings date line on chart
            if earnings:
                try:
                    ed = pd.Timestamp(earnings["date_raw"])
                    if hist.index[0] <= ed <= hist.index[-1]:
                        fig.add_vline(
                            x=ed, line_dash="dot", line_color="#e3b341", line_width=1.5,
                            annotation_text=f"📅 Earnings", annotation_font_color="#e3b341",
                            row=1, col=1,
                        )
                except: pass

            # ── Row 2: Volume bars ────────────────────────────────────────────
            vcol = ["#26a69a" if hist["Close"].iloc[i] >= hist["Open"].iloc[i]
                    else "#ef5350" for i in range(len(hist))]
            fig.add_trace(go.Bar(
                x=hist.index, y=hist["Volume"], name="Volume",
                marker_color=vcol, opacity=0.65, showlegend=False,
                hovertemplate="Vol: %{y:,.0f}<extra></extra>",
            ), row=2, col=1)

            # ── Rows 3 & 4: RSI + MACD ────────────────────────────────────────
            if show_studies and indicators:
                close   = hist["Close"]
                delta   = close.diff()
                gain    = delta.where(delta > 0, 0).rolling(14).mean()
                loss    = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rsi_ser = 100 - (100 / (1 + gain / loss))

                # RSI
                rsi_colors = []
                for v in rsi_ser:
                    if pd.isna(v):      rsi_colors.append("rgba(0,0,0,0)")
                    elif v > 70:        rsi_colors.append("#ef5350")
                    elif v < 30:        rsi_colors.append("#26a69a")
                    else:               rsi_colors.append("#e3b341")

                fig.add_trace(go.Scatter(
                    x=hist.index, y=rsi_ser, name="RSI (14)",
                    line=dict(color="#e3b341", width=1.8),
                    hovertemplate="RSI: %{y:.1f}<extra></extra>",
                ), row=3, col=1)
                fig.add_hrect(y0=70, y1=100, fillcolor="rgba(239,83,80,0.07)",
                              line_width=0, row=3, col=1)
                fig.add_hrect(y0=0,  y1=30,  fillcolor="rgba(38,166,154,0.07)",
                              line_width=0, row=3, col=1)
                fig.add_hline(y=70, line_dash="dot", line_color="rgba(239,83,80,0.5)",
                              line_width=1, row=3, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="rgba(38,166,154,0.5)",
                              line_width=1, row=3, col=1)

                # MACD
                ema12    = close.ewm(span=12, adjust=False).mean()
                ema26    = close.ewm(span=26, adjust=False).mean()
                macd_l   = ema12 - ema26
                signal_l = macd_l.ewm(span=9, adjust=False).mean()
                hist_l   = macd_l - signal_l
                hist_col = ["#26a69a" if v >= 0 else "#ef5350" for v in hist_l]

                fig.add_trace(go.Bar(
                    x=hist.index, y=hist_l, name="MACD Hist",
                    marker_color=hist_col, opacity=0.7, showlegend=False,
                    hovertemplate="Hist: %{y:.4f}<extra></extra>",
                ), row=4, col=1)
                fig.add_trace(go.Scatter(
                    x=hist.index, y=macd_l, name="MACD",
                    line=dict(color="#58a6ff", width=1.5),
                    hovertemplate="MACD: %{y:.4f}<extra></extra>",
                ), row=4, col=1)
                fig.add_trace(go.Scatter(
                    x=hist.index, y=signal_l, name="Signal",
                    line=dict(color="#f78166", width=1.5),
                    hovertemplate="Signal: %{y:.4f}<extra></extra>",
                ), row=4, col=1)

            # ── Layout ────────────────────────────────────────────────────────
            chart_h = 750 if not show_studies else 1000
            fig.update_layout(
                template="plotly_dark",
                height=chart_h,
                showlegend=True,
                xaxis_rangeslider_visible=False,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Space Grotesk", color="#f0f6fc"),
                legend=dict(orientation="h", yanchor="bottom", y=1.01,
                            bgcolor="rgba(13,17,40,0.8)", bordercolor="#1e2a45",
                            borderwidth=1),
                margin=dict(t=40, b=10, l=10, r=10),
                hovermode="x unified",
                dragmode="pan",
                modebar_add=["drawline","drawopenpath","eraseshape"],
                modebar_remove=["lasso2d","select2d"],
            )
            # Y-axis labels
            fig.update_yaxes(title_text="Price ($)",  row=1, col=1,
                             tickprefix="$", gridcolor="rgba(30,42,69,0.6)")
            fig.update_yaxes(title_text="Volume",     row=2, col=1,
                             gridcolor="rgba(30,42,69,0.4)")
            if show_studies:
                fig.update_yaxes(title_text="RSI",    row=3, col=1, range=[0,100],
                                 gridcolor="rgba(30,42,69,0.4)")
                fig.update_yaxes(title_text="MACD",   row=4, col=1,
                                 gridcolor="rgba(30,42,69,0.4)")
            # X-axis config — only show on bottom row
            for r in range(1, n_rows):
                fig.update_xaxes(showticklabels=False, row=r, col=1,
                                 gridcolor="rgba(30,42,69,0.3)")
            fig.update_xaxes(showticklabels=True, row=n_rows, col=1,
                             gridcolor="rgba(30,42,69,0.3)")

            st.plotly_chart(fig, use_container_width=True,
                            config={"scrollZoom": True, "displayModeBar": True,
                                    "modeBarButtonsToAdd": ["pan2d","zoomIn2d","zoomOut2d",
                                                            "resetScale2d","toImage"],
                                    "toImageButtonOptions": {"format":"png","filename":f"{ticker}_chart"},
                                    "displaylogo": False})
            st.caption("💡 Scroll to zoom · Drag to pan · Double-click to reset · Use modebar for more tools")

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
