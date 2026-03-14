# =============================================================================
# WHALE TERMINAL ELITE — whale_terminal_modules.py  v7.0
# Modules: AuthManager, PortfolioManager, WatchlistManager,
#          DCF Valuation, Relative Strength, RSI Backtest,
#          Polymarket Integration  [NEW], Auto Peer Group  [NEW]
# =============================================================================
from __future__ import annotations
import os, json, math, requests
try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# ─── Shared constants ─────────────────────────────────────────────────────────
SECTOR_ETF_MAP = {
    "Technology":"XLK","Healthcare":"XLV","Financials":"XLF",
    "Consumer Cyclical":"XLY","Consumer Defensive":"XLP","Industrials":"XLI",
    "Energy":"XLE","Utilities":"XLU","Real Estate":"XLRE",
    "Basic Materials":"XLB","Communication Services":"XLC",
}
SECTOR_COLORS = {
    "Technology":"#58a6ff","Healthcare":"#3fb950","Financials":"#e3b341",
    "Energy":"#f85149","Consumer Cyclical":"#a371f7","Industrials":"#79c0ff",
    "Consumer Defensive":"#56d364","Utilities":"#ffa657","Real Estate":"#ff7b72",
    "Basic Materials":"#d2a8ff","Communication Services":"#63e6be",
}
# Sentinel: FMP returned a plan/legacy block (not an empty/missing result).
# _fmp_get returns this object; callers test `result is _FMP_BLOCKED`.
# SINGLE SOURCE OF TRUTH — app.py must import this, not redefine its own.
# Two separate singletons in two modules compare unequal under `is`, which
# silently breaks every blocked-response guard in get_stock_info.
class _Blocked:
    _inst = None
    def __new__(cls):
        if cls._inst is None: cls._inst = super().__new__(cls)
        return cls._inst
    def __repr__(self): return "<FMP_BLOCKED>"
_FMP_BLOCKED = _Blocked()   # ← canonical instance; imported by app.py

FMP_BASE = "https://financialmodelingprep.com/api/v3"

def _fmp_get(path: str, params: dict | None = None, api_key: str = ""):
    """
    Central FMP v3 helper for this module. Returns one of:
      - Parsed data (list or dict)   on success
      - _FMP_BLOCKED sentinel        on 403 or plan/legacy "Error Message"
      - None                         on empty result, timeout, network error

    Callers test `result is _FMP_BLOCKED` to trigger yfinance fallback.
    """
    key = api_key or ""
    if not key:
        try:
            key = str(st.secrets.get("FMP_API_KEY", ""))
        except Exception:
            key = ""
    if not key:
        print("[FMP modules] no API key — using _FMP_BLOCKED signal")
        return _FMP_BLOCKED
    try:
        p = {"apikey": key}
        if params:
            p.update(params)
        r = requests.get(f"{FMP_BASE}{path}", params=p, timeout=10)
        if r.status_code == 403:
            print(f"[FMP 403] {path} — will fall back to Yahoo Finance")
            return _FMP_BLOCKED
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "Error Message" in data:
            print(f"[FMP blocked] {path}: {data['Error Message'][:120]}")
            return _FMP_BLOCKED
        return data
    except requests.exceptions.HTTPError as exc:
        if exc.response.status_code == 403:
            return _FMP_BLOCKED
        print(f"[FMP HTTP error] {path}: {exc}")
        return None
    except Exception as exc:
        print(f"[FMP error] {path}: {exc}")
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _fmp_price(ticker: str, api_key: str = "") -> tuple[float | None, float]:
    """
    Return (current_price, change_pct) for a single ticker.
    FMP /quote is primary; yfinance fast_info is the silent fallback on 403.
    """
    data = _fmp_get(f"/quote/{ticker}", api_key=api_key)
    if data is _FMP_BLOCKED:
        # Silent yfinance fallback
        try:
            info = yf.Ticker(ticker).fast_info
            price = float(getattr(info, "last_price", None) or 0) or None
            prev  = float(getattr(info, "previous_close", None) or price or 1)
            chg   = ((price - prev) / prev * 100) if (price and prev) else 0.0
            print(f"[Fallback] _fmp_price({ticker}) → Yahoo Finance: {price}")
            return price, chg
        except Exception as exc:
            print(f"[yf price error] {ticker}: {exc}")
            return None, 0.0
    if data and isinstance(data, list) and data:
        q = data[0]
        price = q.get("price")
        chg   = q.get("changesPercentage", 0.0)
        return (float(price) if price is not None else None,
                float(chg)   if chg   is not None else 0.0)
    return None, 0.0


def _yf_ohlcv(ticker: str, period: str, interval: str) -> "pd.DataFrame":
    """Yahoo Finance OHLCV helper used as fallback inside _fmp_history."""
    empty = pd.DataFrame()
    try:
        yf_period_map = {
            "2d":"2d","1mo":"1mo","3mo":"3mo","6mo":"6mo",
            "1y":"1y","2y":"2y","5y":"5y",
        }
        yf_interval_map = {"5m":"5m","15m":"15m","30m":"30m","1h":"1h","1d":"1d","1wk":"1wk"}
        yp = yf_period_map.get(period, "1y")
        yi = yf_interval_map.get(interval, "1d")
        df = yf.Ticker(ticker).history(period=yp, interval=yi)
        if df.empty:
            return empty
        df = df[["Open","High","Low","Close","Volume"]].copy()
        df.index = pd.to_datetime(df.index)
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        df.index.name = "Date"
        return df.dropna()
    except Exception as exc:
        print(f"[yf ohlcv error] {ticker}: {exc}")
        return empty

@st.cache_data(ttl=3600, show_spinner=False)
def _fmp_history(ticker: str, period: str = "1y", interval: str = "1d",
                 api_key: str = "") -> "pd.DataFrame":
    """
    Fetch OHLCV history. FMP primary; yfinance silent fallback on 403.
    Used by portfolio benchmark and relative-strength calculations.
    """
    empty = pd.DataFrame()
    if interval in ("5m","15m","30m","1h"):
        data = _fmp_get(f"/historical-chart/{interval}/{ticker}", api_key=api_key)
        if data is _FMP_BLOCKED:
            print(f"[Fallback] _fmp_history intraday {ticker} → Yahoo Finance")
            return _yf_ohlcv(ticker, period, interval)
        if not data or not isinstance(data, list):
            return empty
        df = (pd.DataFrame(data)
              .rename(columns={"date":"Date","open":"Open","high":"High",
                                "low":"Low","close":"Close","volume":"Volume"}))
        df["Date"] = pd.to_datetime(df["Date"])
        return df.set_index("Date").sort_index()[["Open","High","Low","Close","Volume"]].dropna()

    period_days = {"2d":2,"1mo":31,"3mo":92,"6mo":183,"1y":365,"2y":730,"5y":1825}
    days = period_days.get(period, 365)
    from_date = (datetime.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    data = _fmp_get(f"/historical-price-full/{ticker}", {"from": from_date}, api_key=api_key)
    if data is _FMP_BLOCKED:
        print(f"[Fallback] _fmp_history daily {ticker} → Yahoo Finance")
        return _yf_ohlcv(ticker, period, interval)
    if not data or not isinstance(data, dict):
        return empty
    hist = data.get("historical", [])
    if not hist:
        return empty
    df = (pd.DataFrame(hist)
          .rename(columns={"date":"Date","open":"Open","high":"High",
                            "low":"Low","close":"Close","volume":"Volume"}))
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    if interval == "1wk":
        df = df.resample("W").agg(
            {"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}
        ).dropna()
    return df[["Open","High","Low","Close","Volume"]].dropna()

# Industry → known large-cap peer tickers (fallback when FMP unavailable)
INDUSTRY_PEERS: dict[str, list[str]] = {
    "Semiconductors": ["NVDA","AMD","INTC","AVGO","TSM","QCOM","MU","AMAT"],
    "Software—Infrastructure": ["MSFT","ORCL","IBM","SAP","NOW","SNOW","DDOG"],
    "Software—Application": ["ADBE","CRM","INTU","WDAY","HUBS","VEEV","ZM"],
    "Consumer Electronics": ["AAPL","SONY","DELL","HPQ","LOGI"],
    "Internet Content & Information": ["GOOGL","META","SNAP","PINS","RDDT"],
    "Auto Manufacturers": ["TSLA","TM","GM","F","RIVN","NIO","STLA"],
    "Biotechnology": ["AMGN","GILD","BIIB","REGN","VRTX","MRNA","BNTX"],
    "Drug Manufacturers": ["PFE","MRK","ABBV","LLY","JNJ","BMY","RHHBY"],
    "Banks—Diversified": ["JPM","BAC","WFC","C","GS","MS","USB"],
    "Insurance": ["BRK-B","MET","PRU","AIG","TRV","ALL","PGR"],
    "Oil & Gas E&P": ["XOM","CVX","COP","OXY","EOG","PXD","DVN"],
    "Airlines": ["DAL","UAL","AAL","LUV","JBLU","ALK"],
    "Retail": ["AMZN","WMT","TGT","COST","HD","LOW","TJX"],
    "Restaurants": ["MCD","SBUX","CMG","YUM","QSR","DPZ","WEN"],
}

def _strip_tz(df):
    if df is None or df.empty: return df
    if hasattr(df.index,"tz") and df.index.tz is not None:
        df=df.copy(); df.index=df.index.tz_convert("UTC").tz_localize(None)
    return df

def _strip_tz_s(s):
    if s is None or s.empty: return s
    if hasattr(s.index,"tz") and s.index.tz is not None:
        s=s.copy(); s.index=s.index.tz_convert("UTC").tz_localize(None)
    return s

# =============================================================================
# MODULE — AUTH MANAGER
# =============================================================================
class AuthManager:
    """Supabase email/password auth with session-only demo fallback."""
    def __init__(self, url="", key=""):
        self._url = url
        self._key = key
        self._client = None
        if self._url and self._key:
            try:
                from supabase import create_client
                self._client = create_client(self._url, self._key)
            except Exception: pass

    @property
    def is_connected(self): return self._client is not None
    @staticmethod
    def is_logged_in(): return st.session_state.get("wt_authed", False)
    @staticmethod
    def current_user(): return st.session_state.get("wt_user")
    @staticmethod
    def user_id():
        u = st.session_state.get("wt_user"); return u["id"] if u else "anonymous"
    @staticmethod
    def user_email():
        u = st.session_state.get("wt_user"); return u.get("email","") if u else ""

    def sign_up(self, email, password):
        if not self.is_connected: return self._demo_login(email)
        try:
            res = self._client.auth.sign_up({"email":email,"password":password})
            if res.user: self._set_session(res.user, res.session); return True, f"Welcome {email}! Check inbox."
            return False, "Sign-up failed."
        except Exception as e: return False, str(e)

    def sign_in(self, email, password):
        if not self.is_connected: return self._demo_login(email)
        try:
            res = self._client.auth.sign_in_with_password({"email":email,"password":password})
            if res.user: self._set_session(res.user, res.session); return True, f"Welcome back, {email}!"
            return False, "Invalid credentials."
        except Exception as e: return False, str(e)

    def sign_out(self):
        if self.is_connected:
            try: self._client.auth.sign_out()
            except: pass
        st.session_state["wt_user"] = None
        st.session_state["wt_authed"] = False

    def _set_session(self, user, session):
        st.session_state["wt_user"] = {
            "id": user.id, "email": user.email,
            "access_token":  getattr(session,"access_token","") if session else "",
            "refresh_token": getattr(session,"refresh_token","") if session else "",
        }
        st.session_state["wt_authed"] = True

    def _demo_login(self, email):
        import uuid
        # uuid5 with a fixed namespace gives a deterministic, collision-resistant
        # session ID from the email string — no cryptographic security claim,
        # purely a stable identifier for session-only demo mode.
        fid = str(uuid.uuid5(uuid.NAMESPACE_X500, email))
        st.session_state["wt_user"] = {"id":fid,"email":email,"access_token":"","refresh_token":""}
        st.session_state["wt_authed"] = True
        return True, f"Demo mode: signed in as {email} (session-only)."

    def render_auth_page(self):
        st.markdown("""
        <div style='text-align:center;padding:60px 0 30px;'>
            <span style='font-size:4rem;'>🐳</span>
            <h1 style='background:linear-gradient(90deg,#58a6ff,#e3b341);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                font-size:2.8rem;font-weight:900;margin:0;'>WHALE TERMINAL ELITE</h1>
            <p style='color:#8b949e;font-size:1.1rem;margin-top:8px;'>
                Institutional-Grade Stock Intelligence Platform v7.0</p>
        </div>""", unsafe_allow_html=True)
        col = st.columns([1,1.8,1])[1]
        with col:
            tab_in, tab_up = st.tabs(["🔐 Sign In","✨ Sign Up"])
            with tab_in:
                st.markdown("#### Welcome back")
                email = st.text_input("Email", key="li_em", placeholder="you@example.com")
                pwd   = st.text_input("Password", type="password", key="li_pw", placeholder="••••••••")
                if st.button("Sign In →", use_container_width=True, type="primary", key="btn_li"):
                    if email and pwd:
                        ok, msg = self.sign_in(email, pwd)
                        if ok: st.success(msg); st.rerun()
                        else:  st.error(msg)
                    else: st.warning("Enter email and password.")
                st.caption("No Supabase? Any email/password works in demo mode.")
            with tab_up:
                st.markdown("#### Create account")
                em  = st.text_input("Email",    key="su_em",  placeholder="you@example.com")
                pw  = st.text_input("Password", type="password", key="su_pw",  placeholder="min 6 chars")
                pw2 = st.text_input("Confirm",  type="password", key="su_pw2", placeholder="same again")
                if st.button("Create Account →", use_container_width=True, type="primary", key="btn_su"):
                    if pw != pw2:      st.error("Passwords do not match.")
                    elif len(pw) < 6:  st.error("Password must be >= 6 characters.")
                    elif em:
                        ok, msg = self.sign_up(em, pw)
                        if ok: st.success(msg); st.rerun()
                        else:  st.error(msg)
                    else: st.warning("Enter email.")


# =============================================================================
# MODULE — WATCHLIST MANAGER  (persistence fixed v8)
# =============================================================================
class WatchlistManager:
    """
    Supabase-backed watchlist with robust session-state fallback.
    Fix v8: injects the user's JWT token before every Supabase call so that
    Row Level Security allows reads and writes. Falls back to session state
    if Supabase is unavailable or the token is missing.
    """
    def __init__(self, url="", key=""):
        self._url = url
        self._key = key
        self._client = None
        self._ok = False
        self._try_connect()

    def _try_connect(self):
        if not (self._url and self._key): return
        try:
            from supabase import create_client
            self._client = create_client(self._url, self._key)
            self._ok = True
        except Exception as e:
            st.warning(f"Watchlist: Supabase unavailable ({e}). Using session storage.")

    @property
    def is_connected(self): return self._ok and self._client is not None

    def _inject_token(self):
        """Set the user's JWT so RLS policies allow access. Returns True if token found."""
        user = st.session_state.get("wt_user", {})
        token = user.get("access_token", "")
        refresh = user.get("refresh_token", "")
        if not token:
            return False
        try:
            self._client.auth.set_session(token, refresh)
        except Exception:
            pass
        return True

    def add(self, user_id, ticker, note="", alert_price=None):
        ticker = ticker.upper().strip()
        self._sess_upsert(user_id, ticker, note, alert_price)
        if not self.is_connected: return True
        if not self._inject_token():
            st.warning("Watchlist: not saved to cloud (no auth token). Data lives in session only.")
            return True
        try:
            self._client.table("watchlists").upsert(
                {"user_id":user_id,"ticker":ticker,"note":note,"alert_price":alert_price},
                on_conflict="user_id,ticker"
            ).execute()
        except Exception as e:
            st.warning(f"Watchlist cloud sync failed: {e}")
        return True

    def remove(self, user_id, ticker):
        ticker = ticker.upper().strip()
        self._sess_remove(user_id, ticker)
        if not self.is_connected: return True
        if not self._inject_token(): return True
        try:
            self._client.table("watchlists").delete().eq("user_id",user_id).eq("ticker",ticker).execute()
        except Exception as e:
            st.warning(f"Watchlist cloud delete failed: {e}")
        return True

    def get(self, user_id):
        if self.is_connected and self._inject_token():
            try:
                res = self._client.table("watchlists").select(
                    "ticker,note,alert_price,added_at"
                ).eq("user_id",user_id).order("added_at",desc=True).execute()
                items = res.data or []
                st.session_state[f"wl_{user_id}"] = items
                return items
            except Exception as e:
                st.warning(f"Watchlist cloud read failed: {e}")
        return st.session_state.get(f"wl_{user_id}", [])

    def _sess_upsert(self, uid, ticker, note, alert):
        k = f"wl_{uid}"
        items = [i for i in st.session_state.get(k,[]) if i["ticker"] != ticker]
        items.insert(0,{"ticker":ticker,"note":note,"alert_price":alert,
                        "added_at":datetime.utcnow().isoformat()})
        st.session_state[k] = items

    def _sess_remove(self, uid, ticker):
        k = f"wl_{uid}"
        st.session_state[k] = [i for i in st.session_state.get(k,[]) if i["ticker"]!=ticker]


def render_watchlist_sidebar(wm, user_id, current_ticker=""):
    """Compact sidebar watchlist. Analyse button navigates to Stock Analysis page."""
    st.markdown("**📋 My Watchlist**")
    st.caption("☁️ Supabase" if wm.is_connected else "💾 Session-only")
    if current_ticker:
        note  = st.text_input("Note", key=f"wl_n_{current_ticker}", placeholder="optional note")
        alert = st.number_input("Alert $", 0.0, value=0.0, step=1.0, key=f"wl_a_{current_ticker}",
                                 help="Notify when price reaches this level")
        if st.button(f"➕ Add {current_ticker}", use_container_width=True, key=f"wl_add_{current_ticker}"):
            wm.add(user_id, current_ticker, note=note, alert_price=float(alert) if alert>0 else None)
            st.success(f"✅ {current_ticker} added!"); st.rerun()
    items = wm.get(user_id)
    if items:
        st.markdown("---")
        for item in items[:15]:
            sym = item["ticker"]
            ci, cb, cd = st.columns([3,2,1])
            with ci:
                lbl = f"**{sym}**"
                if item.get("note"): lbl += f"  _{item['note']}_"
                if item.get("alert_price"): lbl += f"  🔔${float(item['alert_price']):,.2f}"
                st.markdown(lbl)
            with cb:
                # ── KEY FIX: set both active_page AND analysis_ticker then rerun ──
                if st.button("▶ Analyse", key=f"wl_an_{sym}"):
                    st.session_state["active_page"]     = "🔍 Stock Analysis"
                    st.session_state["analysis_ticker"] = sym
                    st.session_state["analysis_loaded"] = False  # force reload
                    st.rerun()
            with cd:
                if st.button("✕", key=f"wl_del_{sym}"):
                    wm.remove(user_id, sym); st.rerun()
    else:
        st.caption("Watchlist is empty.")


def render_watchlist_page(wm, user_id):
    """Full-page watchlist with live prices and Analyse buttons."""
    st.markdown('''<div class="page-title">👀 My Watchlist</div>''', unsafe_allow_html=True)
    with st.expander("➕ Add Ticker", expanded=False):
        ca,cb,cc = st.columns([2,2,2])
        with ca: sym = st.text_input("Ticker",key="wlp_sym",placeholder="AAPL").upper().strip()
        with cb: note = st.text_input("Note",key="wlp_note",placeholder="e.g. AI play")
        with cc: alert = st.number_input("Price Alert ($)",0.0,value=0.0,step=1.0,key="wlp_alert")
        if st.button("Add to Watchlist",type="primary",key="wlp_add"):
            if sym:
                wm.add(user_id, sym, note=note, alert_price=float(alert) if alert>0 else None)
                st.success(f"✅ {sym} added!"); st.rerun()
            else: st.warning("Enter a ticker symbol.")

    items = wm.get(user_id)
    if not items:
        st.info("Watchlist is empty. Add tickers above."); return

    st.markdown(f"**{len(items)} tickers tracked**")
    st.markdown("---")
    for item in items:
        sym2 = item["ticker"]
        try:
            price, chg = _fmp_price(sym2)
        except:
            price = None; chg = 0.0
        alp = item.get("alert_price")
        c1,c2,c3,c4,c5 = st.columns([1.5,1.2,1.2,3,2])
        with c1: st.markdown(f"### {sym2}")
        with c2: st.metric("Price",f"${price:,.2f}" if price else "N/A")
        with c3: st.metric("Change",f"{chg:+.2f}%" if price else "N/A")
        with c4:
            nt = item.get("note","")
            if alp: nt += f"  🔔${float(alp):,.2f}"
            st.caption(nt or "No note")
        with c5:
            b1,b2 = st.columns(2)
            with b1:
                if st.button("📊 Analyse",key=f"wlpa_{sym2}",use_container_width=True):
                    st.session_state["active_page"]     = "🔍 Stock Analysis"
                    st.session_state["analysis_ticker"] = sym2
                    st.session_state["analysis_loaded"] = False
                    st.rerun()
            with b2:
                if st.button("✕",key=f"wlpd_{sym2}",use_container_width=True):
                    wm.remove(user_id, sym2); st.rerun()
        st.markdown("---")


# =============================================================================
# MODULE — PORTFOLIO MANAGER  (persistence fixed v7)
# =============================================================================
class PortfolioManager:
    """
    Supabase-backed portfolio with session-state fallback.
    Fix v8: injects the user's JWT token before every Supabase call so that
    Row Level Security allows reads and writes. Errors are surfaced visibly
    instead of being swallowed silently.
    """
    def __init__(self, url="", key=""):
        self._url = url
        self._key = key
        self._client = None; self._ok = False
        if self._url and self._key:
            try:
                from supabase import create_client
                self._client = create_client(self._url, self._key); self._ok = True
            except Exception as e:
                st.warning(f"Portfolio: Supabase unavailable ({e}). Using session storage.")

    @property
    def is_connected(self): return self._ok and self._client is not None

    def _inject_token(self):
        """Set the user's JWT so RLS policies allow access. Returns True if token found."""
        user = st.session_state.get("wt_user", {})
        token = user.get("access_token", "")
        refresh = user.get("refresh_token", "")
        if not token:
            return False
        try:
            self._client.auth.set_session(token, refresh)
        except Exception:
            pass
        return True

    def add_position(self, user_id, ticker, buy_price, quantity, sector=""):
        ticker = ticker.upper().strip()
        self._sess_upsert(user_id, ticker, buy_price, quantity, sector)
        if not self.is_connected: return True
        if not self._inject_token():
            st.warning("Portfolio: not saved to cloud (no auth token). Data lives in session only.")
            return True
        try:
            self._client.table("portfolios").upsert({
                "user_id":user_id,"ticker":ticker,"buy_price":buy_price,
                "quantity":quantity,"sector":sector
            }, on_conflict="user_id,ticker").execute()
        except Exception as e:
            st.warning(f"Portfolio cloud sync failed: {e}")
        return True

    def remove_position(self, user_id, ticker):
        ticker = ticker.upper().strip()
        self._sess_remove(user_id, ticker)
        if not self.is_connected: return True
        if not self._inject_token(): return True
        try:
            self._client.table("portfolios").delete().eq("user_id",user_id).eq("ticker",ticker).execute()
        except Exception as e:
            st.warning(f"Portfolio delete failed: {e}")
        return True

    def get_positions(self, user_id):
        if self.is_connected and self._inject_token():
            try:
                res = self._client.table("portfolios").select(
                    "ticker,buy_price,quantity,sector,added_at"
                ).eq("user_id",user_id).order("added_at",desc=True).execute()
                items = res.data or []
                st.session_state[f"port_{user_id}"] = items
                return items
            except Exception as e:
                st.warning(f"Portfolio cloud read failed: {e}")
        return st.session_state.get(f"port_{user_id}",[])

    def _sess_upsert(self, uid, ticker, bp, qty, sec):
        k = f"port_{uid}"
        items = [i for i in st.session_state.get(k,[]) if i["ticker"]!=ticker]
        items.insert(0,{"ticker":ticker,"buy_price":bp,"quantity":qty,"sector":sec,
                        "added_at":datetime.utcnow().isoformat()})
        st.session_state[k] = items

    def _sess_remove(self, uid, ticker):
        k = f"port_{uid}"
        st.session_state[k] = [i for i in st.session_state.get(k,[]) if i["ticker"]!=ticker]

    @staticmethod
    @st.cache_data(ttl=300, show_spinner=False)
    def _live(ticker):
        try:
            price, _ = _fmp_price(ticker)
            return price
        except:
            return None

    def enrich(self, positions):
        rows = []
        for p in positions:
            t=p["ticker"]; bp=float(p["buy_price"]); qty=float(p["quantity"])
            cur=self._live(t) or bp
            cost=bp*qty; mkt=cur*qty; pnl=mkt-cost
            rows.append({"Ticker":t,"Sector":p.get("sector","Unknown"),
                "Qty":qty,"Buy Price":bp,"Current Price":cur,
                "Cost Basis":cost,"Market Value":mkt,
                "P&L $":pnl,"P&L %":(pnl/cost*100) if cost else 0})
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    @staticmethod
    @st.cache_data(ttl=3600, show_spinner=False)
    def _hist_close(ticker, period="1y"):
        try:
            h = _fmp_history(ticker, period=period, interval="1d")
            return h["Close"] if not h.empty else None
        except:
            return None

    def benchmark_chart(self, positions, period="1y"):
        if not positions: return None
        try:
            spy = self._hist_close("SPY", period)
            if spy is None: return None
            # F-22 fix: weight by current market value (qty × live price), not cost basis.
            # Cost-basis weighting understates positions that have appreciated significantly,
            # producing an incorrect benchmark comparison for long-held positions.
            live_prices = {p["ticker"]: (self._live(p["ticker"]) or float(p["buy_price"]))
                           for p in positions}
            tc = sum(live_prices[p["ticker"]] * float(p["quantity"]) for p in positions)
            if tc <= 0: return None
            pr = pd.Series(0.0, index=spy.index)
            for p in positions:
                cl = self._hist_close(p["ticker"], period)
                if cl is None: continue
                # weight = current market value of this position / total portfolio value
                w = (live_prices[p["ticker"]] * float(p["quantity"])) / tc
                aligned = cl.reindex(spy.index, method="ffill")
                pr = pr.add((aligned/aligned.iloc[0]-1)*100*w, fill_value=0)
            sr = (spy/spy.iloc[0]-1)*100
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=pr.index,y=pr.values,name="My Portfolio",
                line=dict(color="#e3b341",width=2.5),fill="tozeroy",fillcolor="rgba(227,179,65,0.07)"))
            fig.add_trace(go.Scatter(x=sr.index,y=sr.values,name="S&P 500 (SPY)",
                line=dict(color="#58a6ff",width=2,dash="dot")))
            fig.add_hline(y=0,line_dash="dot",line_color="rgba(255,255,255,0.2)")
            fig.update_layout(template="plotly_dark",height=380,
                title="Portfolio vs S&P 500 — Cumulative Return",
                paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                hovermode="x unified",font=dict(color="#f0f6fc"),
                yaxis_title="Return (%)",legend=dict(orientation="h",yanchor="bottom",y=1.02))
            return fig
        except: return None

    def render_page(self, user_id, fmp_api_key=""):
        st.markdown('''<div class="page-title">💼 My Portfolio</div>''', unsafe_allow_html=True)
        with st.expander("➕ Add / Update Position",expanded=False):
            c1,c2,c3,c4 = st.columns(4)
            with c1: nt = st.text_input("Ticker",placeholder="AAPL",key="pt").upper().strip()
            with c2: np_ = st.number_input("Buy Price ($)",0.01,1e7,100.0,0.01,key="pp",help="Avg purchase cost")
            with c3: nq = st.number_input("Quantity",0.001,1e6,10.0,1.0,key="pq",help="Number of shares")
            with c4:
                choices = ["Unknown"]+sorted(SECTOR_ETF_MAP.keys())
                ns = st.selectbox("Sector",choices,key="ps")
            if st.button("Add / Update",type="primary",key="btn_padd"):
                if nt:
                    sector = ns
                    if sector == "Unknown" and fmp_api_key:
                        try:
                            pr = _fmp_get(f"/profile/{nt}", api_key=fmp_api_key)
                            if pr and isinstance(pr, list):
                                sector = pr[0].get("sector", "Unknown") or "Unknown"
                        except:
                            pass
                    self.add_position(user_id, nt, np_, nq, sector)
                    st.success(f"✅ {nt} saved."); st.rerun()
                else: st.warning("Enter a ticker.")

        positions = self.get_positions(user_id)
        if not positions:
            st.info("Portfolio empty. Add a position above."); return

        with st.spinner("Fetching live prices…"):
            df = self.enrich(positions)
        if df.empty:
            st.info("No data loaded."); return

        tc2 = df["Cost Basis"].sum(); tv = df["Market Value"].sum()
        tp = df["P&L $"].sum(); tpp = (tp/tc2*100) if tc2 else 0
        k1,k2,k3,k4 = st.columns(4)
        with k1: st.metric("Total Cost",f"${tc2:,.2f}",help="All positions at cost")
        with k2: st.metric("Market Value",f"${tv:,.2f}",help="Live total value")
        with k3: st.metric("Total P&L",f"${tp:+,.2f}",f"{tpp:+.2f}%",help="Unrealised gain/loss")
        with k4:
            best = df.loc[df["P&L %"].idxmax()]
            st.metric("Best Performer",best["Ticker"],f"{best['P&L %']:+.2f}%")
        st.markdown("---")

        l,r = st.columns(2)
        with l:
            st.markdown("### 🍩 Allocation")
            mode = st.radio("By",["Stock","Sector"],horizontal=True,key="palloc")
            if mode == "Sector":
                agg = df.groupby("Sector")["Market Value"].sum().reset_index()
                labels,vals = agg["Sector"].tolist(),agg["Market Value"].tolist()
                colors = [SECTOR_COLORS.get(s,"#58a6ff") for s in agg["Sector"]]
            else:
                labels,vals,colors = df["Ticker"].tolist(),df["Market Value"].tolist(),None
            fd = go.Figure(go.Pie(labels=labels,values=vals,hole=0.55,
                marker_colors=colors,textinfo="label+percent"))
            fd.update_layout(template="plotly_dark",height=360,paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,margin=dict(t=30,b=10,l=10,r=10),
                annotations=[dict(text=f"${tv/1e3:.1f}K",x=0.5,y=0.5,
                    font_size=18,showarrow=False,font_color="#f0f6fc")])
            st.plotly_chart(fd,use_container_width=True)

        with r:
            st.markdown("### 📊 P&L by Position")
            ds = df.sort_values("P&L %",ascending=True)
            bc = ["#26a69a" if v>=0 else "#ef5350" for v in ds["P&L %"]]
            fb = go.Figure(go.Bar(x=ds["P&L %"],y=ds["Ticker"],orientation="h",
                marker_color=bc,text=[f"{v:+.2f}%" for v in ds["P&L %"]],
                textposition="outside"))
            fb.update_layout(template="plotly_dark",height=360,
                paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                xaxis_title="P&L %",margin=dict(t=30,b=10,l=10,r=60))
            st.plotly_chart(fb,use_container_width=True)

        st.markdown("### 📈 Portfolio vs S&P 500")
        bp2 = st.radio("Period",["3mo","6mo","1y","2y"],index=2,horizontal=True,key="pbench")
        with st.spinner("Building benchmark…"):
            figb = self.benchmark_chart(positions,bp2)
        if figb: st.plotly_chart(figb,use_container_width=True)

        st.markdown("### 📋 Holdings")
        dd = df.copy()
        # Cast every display column to str so Arrow sees a uniform object-of-str
        # dtype rather than a frame mixing float64, int64, and str columns.
        dd["Qty"]           = dd["Qty"].apply(lambda v: f"{v:,.4g}")
        for col in ["Buy Price","Current Price","Cost Basis","Market Value"]:
            dd[col] = dd[col].apply(lambda v: f"${v:,.2f}")
        dd["P&L $"] = dd["P&L $"].apply(lambda v: f"${v:+,.2f}")
        dd["P&L %"] = dd["P&L %"].apply(lambda v: f"{v:+.2f}%")
        st.dataframe(dd, use_container_width=True, hide_index=True)

        with st.expander("🗑️ Remove Position"):
            tl = [p["ticker"] for p in positions]
            dt = st.selectbox("Select",tl,key="pdel")
            if st.button("Remove",type="secondary",key="btn_pdel"):
                self.remove_position(user_id,dt); st.success(f"✅ {dt} removed."); st.rerun()
        st.caption("⚠️ P&L is unrealised. No commissions, taxes, or dividends modelled.")


# =============================================================================
# MODULE — AUTO PEER GROUP  [NEW v7]
# =============================================================================
@st.cache_data(ttl=1800, show_spinner=False)
def get_auto_peers(ticker: str, sector: str, industry: str, fmp_api_key: str = "") -> list[str]:
    """
    Automatically find top 3-5 competitors by market cap in the same industry.
    Strategy:
      1. Try FMP /stock-screener API filtered by sector+exchange, rank by mktCap
      2. Fallback to curated INDUSTRY_PEERS lookup table
      3. Final fallback: same-sector ETF constituents via yfinance sector peers
    Returns list of ticker strings (excluding input ticker).
    """
    ticker = ticker.upper().strip()
    peers: list[str] = []

    # ── Strategy 1: FMP screener (through _fmp_get — error guard active) ──────
    if fmp_api_key and sector:
        try:
            resp = _fmp_get(
                "/stock-screener",
                {"sector": sector, "exchange": "NASDAQ,NYSE,AMEX", "limit": 20},
                api_key=fmp_api_key,
            )
            if isinstance(resp, list) and resp:
                sorted_stocks = sorted(
                    [s for s in resp if s.get("symbol","").upper() != ticker and s.get("mktCap")],
                    key=lambda x: float(x.get("mktCap", 0) or 0), reverse=True,
                )
                peers = [s["symbol"] for s in sorted_stocks[:5]]
        except:
            pass

    # ── Strategy 2: curated industry table ───────────────────────────────────
    if not peers:
        for key, tickers in INDUSTRY_PEERS.items():
            if key.lower() in (industry or "").lower() or (industry or "").lower() in key.lower():
                peers = [t for t in tickers if t != ticker][:5]
                break
        # If still empty, try sector-level match
        if not peers:
            sector_map = {
                "Technology":    ["AAPL","MSFT","GOOGL","META","NVDA","AMD","INTC","CRM","ORCL"],
                "Healthcare":    ["JNJ","PFE","MRK","ABBV","UNH","CVS","HUM","CI","AMGN"],
                "Financials":    ["JPM","BAC","WFC","GS","MS","BLK","AXP","V","MA"],
                "Energy":        ["XOM","CVX","COP","SLB","OXY","PSX","MPC","VLO"],
                "Consumer Cyclical": ["AMZN","TSLA","HD","MCD","NKE","LOW","TGT","BKNG"],
                "Industrials":   ["BA","CAT","GE","HON","UPS","FDX","RTX","LMT","NOC"],
                "Communication Services": ["GOOGL","META","DIS","NFLX","T","VZ","CHTR","CMCSA"],
            }
            raw = sector_map.get(sector or "", [])
            peers = [t for t in raw if t != ticker][:5]

    # ── Strategy 3: index ETF fallback ───────────────────────────────────────
    if not peers:
        peers = ["SPY","QQQ","IWM","DIA","VTI"][:4]

    return peers[:5]


def render_peer_group_info(peers: list[str], source: str = "auto") -> None:
    """Show a compact badge strip indicating auto-detected peers."""
    badge_html = " ".join(
        f'<span style="display:inline-block;background:rgba(88,166,255,0.12);'
        f'border:1px solid rgba(88,166,255,0.3);border-radius:5px;padding:2px 8px;'
        f'color:#58a6ff;font-family:JetBrains Mono,monospace;font-size:0.8rem;'
        f'margin:2px;">{p}</span>'
        for p in peers
    )
    st.markdown(
        f'<div style="margin-bottom:8px;">'
        f'<span style="color:#8b949e;font-size:0.82rem;">🤖 Auto peer group: </span>'
        f'{badge_html}</div>',
        unsafe_allow_html=True,
    )


# =============================================================================
# MODULE — POLYMARKET INTEGRATION  [NEW v7]
# =============================================================================
POLYMARKET_API = "https://clob.polymarket.com"
GAMMA_API      = "https://gamma-api.polymarket.com"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_polymarket_markets(query: str = "", limit: int = 8) -> list[dict]:
    """
    Fetch active Polymarket prediction markets via the Gamma (markets) API.
    Returns list of market dicts with: question, yes_price, no_price, volume, url.
    Falls back to empty list on any error (Polymarket has CORS and rate limits).
    """
    markets: list[dict] = []
    try:
        # Gamma API: public, no auth needed, returns enriched market data
        params: dict = {
            "active":   "true",
            "closed":   "false",
            "order":    "volume",
            "ascending":"false",
            "limit":    str(limit * 3),  # fetch extra to allow filtering
        }
        if query:
            params["tag_slug"] = ""  # reset; we'll filter client-side
        resp = requests.get(f"{GAMMA_API}/markets", params=params, timeout=10)
        resp.raise_for_status()
        raw: list[dict] = resp.json()
    except Exception:
        raw = []

    if not raw:
        # Second attempt: CLOB REST endpoint (lower volume data)
        try:
            resp2 = requests.get(
                f"{POLYMARKET_API}/markets",
                params={"active":"true","closed":"false","limit":str(limit*3)},
                timeout=10,
            )
            raw = resp2.json().get("data", []) if resp2.ok else []
        except: raw = []

    for m in raw:
        question = (m.get("question") or m.get("title") or "").strip()
        if not question: continue
        if query:
            q_lower = query.lower()
            if not any(token in question.lower() for token in q_lower.split()):
                continue

        # Price normalisation: Gamma returns outcomePrices as list, CLOB as tokens
        yes_price = no_price = 0.5
        op = m.get("outcomePrices")
        if op:
            try:
                prices = json.loads(op) if isinstance(op,str) else op
                if len(prices) >= 2:
                    yes_price = float(prices[0])
                    no_price  = float(prices[1])
            except: pass
        else:
            tokens = m.get("tokens", [])
            if len(tokens) >= 2:
                yes_price = float(tokens[0].get("price", 0.5))
                no_price  = float(tokens[1].get("price", 0.5))

        volume = float(m.get("volume","0") or m.get("volumeNum",0) or 0)
        markets.append({
            "question": question,
            "yes_price": yes_price,
            "no_price":  no_price,
            "volume":    volume,
            "url":       f"https://polymarket.com/event/{m.get('slug','')}" if m.get("slug") else "https://polymarket.com",
            "end_date":  (m.get("endDate","") or "")[:10],
        })
        if len(markets) >= limit: break

    return markets


def render_polymarket_tab(ticker: str, sector: str = "") -> None:
    """
    Full Polymarket prediction market tab for a given ticker/sector.
    Shows market odds as visual progress bars with colour-coded conviction.
    """
    st.markdown("### 🔮 Prediction Market Intelligence")
    st.caption(
        "Live crowd-sourced probability markets from [Polymarket](https://polymarket.com). "
        "Prices = implied probability (0 = 0%, 1 = 100%). "
        "Volume indicates market confidence."
    )

    # Search terms: ticker first, then sector keywords
    company_name = ticker  # used as fallback
    sector_keywords = {
        "Technology":    "tech AI semiconductor software",
        "Healthcare":    "FDA drug biotech healthcare",
        "Financials":    "Fed rate interest bank",
        "Energy":        "oil gas energy OPEC",
        "Consumer Cyclical": "retail consumer spending",
        "Communication Services": "media streaming social",
    }
    sector_hint = sector_keywords.get(sector, "stock market economy")

    col_q, col_r = st.columns([3,1])
    with col_q:
        search_q = st.text_input(
            "Search Polymarket",
            value=ticker,
            key=f"poly_q_{ticker}",
            help="Enter a keyword to search prediction markets (company, topic, macro event)",
        )
    with col_r:
        show_macro = st.toggle("Include Macro", value=True, key=f"poly_macro_{ticker}",
                               help="Also show Fed/economy/macro markets")

    # Fetch ticker-specific markets
    with st.spinner("Fetching prediction markets…"):
        ticker_markets = fetch_polymarket_markets(search_q, limit=6)
        macro_markets  = fetch_polymarket_markets("Fed rate economy inflation GDP", limit=4) if show_macro else []

    all_markets = ticker_markets + [m for m in macro_markets if m not in ticker_markets]

    if not all_markets:
        st.info(
            "No live markets found for this query. Polymarket may be rate-limiting or "
            "no active markets exist for this ticker. "
            f"[Browse Polymarket manually →](https://polymarket.com/search?q={ticker})"
        )
        return

    # Group: ticker-specific vs macro
    st.markdown(f"#### 📌 Markets matching **{search_q}**")
    if not ticker_markets:
        st.caption("No direct matches — showing related macro markets.")

    for m in all_markets:
        yes  = m["yes_price"]
        no   = m["no_price"]
        vol  = m["volume"]
        conv_color = "#26a69a" if yes > 0.6 else "#ef5350" if yes < 0.4 else "#e3b341"
        yes_pct = yes * 100
        no_pct  = no  * 100

        with st.container():
            st.markdown(
                f'<div class="info-card gold-accent" style="padding:14px 18px;margin-bottom:10px;">'
                f'<div style="font-weight:700;color:#f0f6fc;font-size:0.95rem;">{m["question"]}</div>'
                f'<div style="color:#8b949e;font-size:0.78rem;margin-top:2px;">'
                f'Volume: ${vol:,.0f} · Closes: {m["end_date"] or "Open-ended"}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            col_yes, col_no, col_link = st.columns([3, 3, 1])
            with col_yes:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;">'
                    f'<span style="color:#26a69a;font-weight:800;font-size:1.1rem;">YES</span>'
                    f'<span style="color:{conv_color};font-weight:900;font-size:1.4rem;">{yes_pct:.1f}%</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.progress(min(yes, 1.0))
            with col_no:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;">'
                    f'<span style="color:#ef5350;font-weight:800;font-size:1.1rem;">NO</span>'
                    f'<span style="color:#ef5350;font-weight:900;font-size:1.4rem;">{no_pct:.1f}%</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.progress(min(no, 1.0))
            with col_link:
                st.markdown(f'[🔗 Trade]({m["url"]})', unsafe_allow_html=True)
            st.markdown("")

    st.caption(
        "⚠️ Prediction markets reflect crowd sentiment, not financial advice. "
        "Prices can be illiquid and manipulable. Use as one signal among many."
    )

# =============================================================================
# MODULES — DCF VALUATION, RELATIVE STRENGTH, RSI BACKTEST
# =============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_fmp(endpoint: str, params: dict):
    """
    DCF-facing FMP helper. Delegates to _fmp_get (strips FMP_BASE prefix).
    Propagates _FMP_BLOCKED so calculate_dcf can fall back to yfinance.
    """
    try:
        path = endpoint
        if path.startswith(FMP_BASE):
            path = path[len(FMP_BASE):]
        p = dict(params) if params else {}
        key = p.pop("apikey", "")
        return _fmp_get(path, p or None, api_key=key)
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def calculate_dcf(
    ticker: str,
    wacc: float = 0.10,
    terminal_growth: float = 0.03,
    projection_years: int = 5,
    fmp_api_key: str = "",
) -> dict | None:
    """
    5-year DCF → Enterprise Value → Equity Value → Intrinsic Value per share.
    FMP primary, yfinance fallback.
    """
    try:
        fcf_history: list[float] = []
        current_price: float = 0.0
        shares_outstanding: float = 0.0
        total_debt: float = 0.0
        cash_and_equivalents: float = 0.0
        minority_interest: float = 0.0

        _fmp_blocked_flag = False

        if fmp_api_key:
            cf_data = _fetch_fmp(f"{FMP_BASE}/cash-flow-statement/{ticker}",
                                 {"apikey": fmp_api_key, "limit": 4})
            if cf_data is _FMP_BLOCKED:
                _fmp_blocked_flag = True
            elif cf_data and isinstance(cf_data, list):
                for yr in cf_data:
                    fcf = yr.get("freeCashFlow") or (
                        (yr.get("operatingCashFlow") or 0) -
                        (yr.get("capitalExpenditure") or 0)
                    )
                    if fcf:
                        fcf_history.append(float(fcf))

            if not _fmp_blocked_flag:
                bs_data = _fetch_fmp(f"{FMP_BASE}/balance-sheet-statement/{ticker}",
                                     {"apikey": fmp_api_key, "limit": 1})
                if bs_data is _FMP_BLOCKED:
                    _fmp_blocked_flag = True
                elif bs_data and isinstance(bs_data, list) and bs_data:
                    bs = bs_data[0]
                    total_debt           = float(bs.get("totalDebt", 0) or 0)
                    cash_and_equivalents = float(bs.get("cashAndCashEquivalents", 0) or 0)
                    minority_interest    = float(bs.get("minorityInterest", 0) or 0)

            if not _fmp_blocked_flag:
                profile = _fetch_fmp(f"{FMP_BASE}/profile/{ticker}", {"apikey": fmp_api_key})
                if profile is _FMP_BLOCKED:
                    _fmp_blocked_flag = True
                elif profile and isinstance(profile, list) and profile:
                    current_price      = float(profile[0].get("price", 0) or 0)
                    shares_outstanding = float(profile[0].get("sharesOutstanding", 0) or 0)

        # ── yfinance fallback for DCF inputs when FMP is blocked ──────────────
        if _fmp_blocked_flag or (not fcf_history and not current_price):
            print(f"[Fallback] calculate_dcf({ticker}) → Yahoo Finance")
            try:
                t   = yf.Ticker(ticker)
                cf  = t.cashflow
                if cf is not None and not cf.empty:
                    for col in cf.columns:
                        try:
                            op  = float(cf.loc["Operating Cash Flow", col] if "Operating Cash Flow" in cf.index else 0)
                            cap = abs(float(cf.loc["Capital Expenditure", col] if "Capital Expenditure" in cf.index else 0))
                            fcf_val = op - cap
                            if fcf_val:
                                fcf_history.append(fcf_val)
                        except Exception:
                            pass
                inf = t.info
                if not current_price:
                    current_price = float(inf.get("currentPrice") or inf.get("regularMarketPrice") or 0)
                if not shares_outstanding:
                    shares_outstanding = float(inf.get("sharesOutstanding") or 0)
                if not total_debt:
                    total_debt = float(inf.get("totalDebt") or 0)
                if not cash_and_equivalents:
                    cash_and_equivalents = float(inf.get("totalCash") or 0)
            except Exception as exc:
                print(f"[yf DCF fallback error] {ticker}: {exc}")

        if not fcf_history or not current_price or not shares_outstanding:
            # FMP supplemental — try income statement for any remaining missing fields
            if fmp_api_key and not _fmp_blocked_flag:
                try:
                    inc = _fetch_fmp(f"{FMP_BASE}/income-statement/{ticker}",
                                     {"apikey": fmp_api_key, "limit": 1})
                    if inc and inc is not _FMP_BLOCKED and isinstance(inc, list) and inc:
                        i0 = inc[0]
                        if not fcf_history:
                            op  = float(i0.get("operatingCashFlow") or 0)
                            cap = float(i0.get("capitalExpenditure") or 0)
                            if op:
                                fcf_history = [op - abs(cap)]
                        if not current_price:
                            q = _fmp_get(f"/quote/{ticker}", api_key=fmp_api_key)
                            if q and q is not _FMP_BLOCKED and isinstance(q, list) and q:
                                current_price = float(q[0].get("price") or 0)
                        if not shares_outstanding:
                            shares_outstanding = float(i0.get("weightedAverageShsOutDil") or 0)
                except:
                    pass

        if not fcf_history or not current_price or not shares_outstanding:
            return None

        # FCF growth rate derived from history
        if len(fcf_history) >= 2:
            pos = [f for f in fcf_history if f > 0]
            if len(pos) >= 2:
                cagr = (pos[0] / pos[-1]) ** (1 / (len(pos) - 1)) - 1
                fcf_growth_rate = float(np.clip(cagr, 0.0, 0.40))
            else:
                fcf_growth_rate = 0.08
        else:
            fcf_growth_rate = 0.12

        fcf_base = fcf_history[0]
        if fcf_base <= 0:
            positives = [f for f in fcf_history if f > 0]
            if not positives:
                return None
            fcf_base = positives[0]

        # Linearly decelerating growth projection
        fcf_growth_rates = np.linspace(fcf_growth_rate, terminal_growth + 0.01, projection_years)
        projected_fcfs: list[float] = []
        pv_fcfs: list[float] = []
        cf = fcf_base
        for i, g in enumerate(fcf_growth_rates, start=1):
            cf = cf * (1 + g)
            projected_fcfs.append(cf)
            pv_fcfs.append(cf / (1 + wacc) ** i)

        terminal_value   = projected_fcfs[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
        pv_terminal      = terminal_value / (1 + wacc) ** projection_years
        enterprise_value = sum(pv_fcfs) + pv_terminal
        net_debt         = total_debt - cash_and_equivalents
        equity_value     = enterprise_value - net_debt - minority_interest
        intrinsic_value  = equity_value / shares_outstanding if shares_outstanding else 0.0

        if intrinsic_value <= 0:
            return None

        margin_of_safety = (intrinsic_value - current_price) / current_price * 100

        projection_df = pd.DataFrame({
            "Year":          [f"Year {i}" for i in range(1, projection_years + 1)],
            "FCF Growth %":  [f"{g*100:.1f}%" for g in fcf_growth_rates],
            "Projected FCF": [f"${f/1e9:.2f}B" for f in projected_fcfs],
            "PV of FCF":     [f"${p/1e9:.2f}B" for p in pv_fcfs],
        })

        return {
            "intrinsic_value":  round(intrinsic_value, 2),
            "current_price":    round(current_price, 2),
            "margin_of_safety": round(margin_of_safety, 2),
            "enterprise_value": enterprise_value,
            "equity_value":     equity_value,
            "pv_fcfs":          pv_fcfs,
            "terminal_value":   terminal_value,
            "pv_terminal":      pv_terminal,
            "fcf_base":         fcf_base,
            "fcf_growth_rates": list(fcf_growth_rates),
            "projection_df":    projection_df,
            "assumptions": {
                "WACC":             f"{wacc*100:.1f}%",
                "Terminal Growth":  f"{terminal_growth*100:.1f}%",
                "Implied FCF CAGR": f"{fcf_growth_rate*100:.1f}%",
                "Projection Years": projection_years,
                "Net Debt":         f"${net_debt/1e9:.2f}B",
                "Shares Out":       f"{shares_outstanding/1e9:.3f}B",
            },
        }
    except Exception:
        return None


def render_dcf_tab(ticker: str, fmp_api_key: str = "") -> None:
    st.markdown("### 🧮 Discounted Cash Flow Valuation")
    st.caption(
        "Enterprise value from projected free cash flows, discounted at WACC. "
        "Margin of Safety = (Intrinsic − Market) ÷ Market."
    )

    col_w, col_g, col_y = st.columns(3)
    with col_w:
        wacc = st.slider(
            "WACC (%)", 6.0, 20.0, 10.0, 0.5,
            key=f"dcf_wacc_{ticker}",
            help="Weighted Average Cost of Capital — your required rate of return.",
        ) / 100
    with col_g:
        tg = st.slider(
            "Terminal Growth (%)", 1.0, 5.0, 3.0, 0.25,
            key=f"dcf_tg_{ticker}",
            help="Perpetual FCF growth after the projection window. Typically ~3% (GDP-level).",
        ) / 100
    with col_y:
        yrs = st.selectbox(
            "Projection Years", [3, 5, 7, 10], index=1,
            key=f"dcf_yrs_{ticker}",
            help="Number of years with explicit FCF projections before terminal value.",
        )

    with st.spinner("⚙️ Running DCF model…"):
        result = calculate_dcf(ticker, wacc=wacc, terminal_growth=tg,
                               projection_years=yrs, fmp_api_key=fmp_api_key)

    if not result:
        st.warning(
            "⚠️ Could not run DCF — the company may have negative FCF or insufficient data. "
            "DCF works best for profitable, cash-generating businesses."
        )
        return

    mos   = result["margin_of_safety"]
    mos_c = "🟢" if mos > 20 else "🟡" if mos > 0 else "🔴"
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("📍 Current Price", f"${result['current_price']:,.2f}",
                  help="Latest market price used as denominator for Margin of Safety.")
    with c2:
        st.metric("🎯 Intrinsic Value", f"${result['intrinsic_value']:,.2f}",
                  help="Per-share value derived from discounted free cash flows.")
    with c3:
        st.metric("🛡️ Margin of Safety", f"{mos:+.1f}% {mos_c}",
                  delta="Undervalued" if mos > 0 else "Overvalued",
                  help="(Intrinsic − Price) ÷ Price. >20% signals meaningful upside cushion.")
    with c4:
        ev_b = result["enterprise_value"] / 1e9
        st.metric("🏛️ Enterprise Value", f"${ev_b:,.1f}B",
                  help="Total firm value = sum of discounted FCFs + terminal value.")

    pv_sum   = sum(result["pv_fcfs"])
    pv_term  = result["pv_terminal"]
    net_debt = result["enterprise_value"] - result["equity_value"]

    fig_bridge = go.Figure(go.Waterfall(
        orientation="v",
        measure=["relative", "relative", "relative", "total"],
        x=["PV of FCFs", "PV Terminal Value", "Net Debt Adj.", "Equity Value"],
        y=[pv_sum / 1e9, pv_term / 1e9, -net_debt / 1e9, 0],
        connector={"line": {"color": "rgba(88,166,255,0.4)"}},
        increasing={"marker": {"color": "#26a69a"}},
        decreasing={"marker": {"color": "#ef5350"}},
        totals={"marker":    {"color": "#58a6ff"}},
        text=[f"${v/1e9:.1f}B" for v in [pv_sum, pv_term, -net_debt, result["equity_value"]]],
        textposition="outside",
    ))
    fig_bridge.update_layout(
        template="plotly_dark", height=380, title="DCF Value Bridge ($ Billions)",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#f0f6fc"), yaxis_title="$ Billions",
    )
    st.plotly_chart(fig_bridge, use_container_width=True)

    st.markdown("#### 📋 FCF Projection Schedule")
    st.dataframe(result["projection_df"], use_container_width=True, hide_index=True)

    st.markdown("#### 🔍 Sensitivity — Intrinsic Value per Share")
    wacc_range   = [w / 100 for w in range(7, 16)]
    tg_range     = [g / 100 for g in range(1, 6)]
    sense_matrix = []
    for w in wacc_range:
        row = []
        for g in tg_range:
            r = calculate_dcf(ticker, wacc=w, terminal_growth=g,
                              projection_years=yrs, fmp_api_key=fmp_api_key)
            row.append(round(r["intrinsic_value"], 2) if r else None)
        sense_matrix.append(row)

    sense_df = pd.DataFrame(
        sense_matrix,
        index=[f"{w*100:.0f}%" for w in wacc_range],
        columns=[f"{g*100:.0f}%" for g in tg_range],
    )
    fig_heat = go.Figure(go.Heatmap(
        z=sense_df.values.tolist(),
        x=[f"g={c}" for c in sense_df.columns],
        y=[f"WACC={r}" for r in sense_df.index],
        colorscale="RdYlGn",
        text=sense_df.values.tolist(),
        texttemplate="$%{text}",
        colorbar=dict(title="Intrinsic Value"),
    ))
    fig_heat.update_layout(
        template="plotly_dark", height=380,
        title=f"Sensitivity (Market Price: ${result['current_price']:,.2f})",
        paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#f0f6fc"),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    with st.expander("📐 Model Assumptions"):
        for k, v in result["assumptions"].items():
            st.caption(f"**{k}:** {v}")
        st.caption("⚠️ DCF is inherently sensitive to assumptions. Use as one input, not the sole driver.")



# =============================================================================
# MODULE 2 — RELATIVE STRENGTH CHART
# =============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_history_pct(ticker_symbol: str, period: str = "1y") -> "pd.Series | None":
    """Cumulative % return series via FMP — no yfinance."""
    try:
        df = _fmp_history(ticker_symbol, period=period, interval="1d")
        if df.empty:
            return None
        s = df["Close"].pct_change().fillna(0)
        return ((1 + s).cumprod() - 1) * 100
    except Exception:
        return None


def _max_drawdown(pct_series: pd.Series) -> float:
    try:
        cumulative  = 1 + pct_series / 100
        rolling_max = cumulative.cummax()
        dd = (cumulative - rolling_max) / rolling_max * 100
        return float(dd.min())
    except Exception:
        return 0.0


def plot_relative_strength(ticker: str, sector: str = "", period: str = "1y") -> go.Figure | None:
    sector_etf = SECTOR_ETF_MAP.get(sector, "")

    tickers_to_plot: list[tuple[str, str, str]] = [
        (ticker, ticker, "#58a6ff"),
        ("SPY", "S&P 500 (SPY)", "#f0f6fc"),
    ]
    if sector_etf:
        tickers_to_plot.append((sector_etf, f"{sector} ETF ({sector_etf})", "#e3b341"))

    series_map: dict[str, pd.Series] = {}
    for sym, _, _ in tickers_to_plot:
        s = _fetch_history_pct(sym, period)
        if s is not None:
            series_map[sym] = s

    if ticker not in series_map:
        return None

    aligned = pd.DataFrame(series_map).dropna(how="all")
    fig     = go.Figure()

    for sym, label, color in tickers_to_plot:
        if sym not in aligned.columns:
            continue
        s         = aligned[sym].dropna()
        final_ret = s.iloc[-1]
        sign      = "+" if final_ret >= 0 else ""
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values,
            name=f"{label}  ({sign}{final_ret:.1f}%)",
            line=dict(color=color, width=2.5),
            hovertemplate=f"<b>{label}</b><br>Date: %{{x|%b %d, %Y}}<br>Return: %{{y:.2f}}%<extra></extra>",
        ))

    fig.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.3)")

    if "SPY" in aligned.columns:
        spread = aligned[ticker] - aligned["SPY"]
        fig.add_trace(go.Scatter(
            x=aligned.index, y=spread.values,
            name=f"{ticker} vs SPY spread",
            fill="tozeroy", fillcolor="rgba(88,166,255,0.08)",
            line=dict(color="rgba(88,166,255,0.3)", width=1, dash="dot"),
            yaxis="y2",
            hovertemplate=f"<b>{ticker} vs SPY</b><br>%{{y:.2f}}%<extra></extra>",
        ))

    period_labels = {"3mo": "3 Months", "6mo": "6 Months", "1y": "1 Year", "2y": "2 Years"}
    fig.update_layout(
        template="plotly_dark", height=480,
        title=dict(
            text=f"📈 Relative Strength — {ticker} vs Market & Sector ({period_labels.get(period, period)})",
            font=dict(size=16, color="#f0f6fc"),
        ),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(title="Cumulative Return (%)", showgrid=True,
                   gridcolor="rgba(255,255,255,0.07)",
                   zeroline=True, zerolinecolor="rgba(255,255,255,0.25)"),
        yaxis2=dict(title="Alpha vs SPY (%)", overlaying="y", side="right",
                    showgrid=False, zeroline=False,
                    tickfont=dict(color="rgba(88,166,255,0.6)")),
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.07)"),
    )
    return fig


def render_relative_strength_tab(ticker: str, sector: str = "") -> None:
    st.markdown("### 📊 Relative Strength vs Market & Sector")
    st.caption("Cumulative total-return comparison. Outperforming lines trend upward relative to peers.")

    period = st.radio(
        "Lookback Period", options=["3mo", "6mo", "1y", "2y"], index=2,
        horizontal=True, key=f"rs_period_{ticker}",
        help="Select how far back to measure relative performance.",
    )

    with st.spinner("Fetching market data…"):
        fig = plot_relative_strength(ticker, sector=sector, period=period)

    if fig:
        st.plotly_chart(fig, use_container_width=True)

        sector_etf = SECTOR_ETF_MAP.get(sector, "")
        symbols    = [ticker, "SPY"] + ([sector_etf] if sector_etf else [])
        rows = []
        for sym in symbols:
            s = _fetch_history_pct(sym, period)
            if s is not None and not s.empty:
                ret    = s.iloc[-1]
                max_dd = _max_drawdown(s)
                vol    = s.diff().std() * (252 ** 0.5)
                rows.append({
                    "Symbol":          sym,
                    "Return":          f"{ret:+.2f}%",
                    "Max Drawdown":    f"{max_dd:.1f}%",
                    "Ann. Volatility": f"{vol:.1f}%",
                    "Sharpe (est.)":   f"{(ret / vol):.2f}" if vol else "N/A",
                })
        if rows:
            st.markdown("#### 📋 Performance Summary")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.warning("Could not load data for relative strength chart.")



# =============================================================================
# MODULE 3 — RSI MEAN-REVERSION BACKTEST ENGINE
# =============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def _load_backtest_data(ticker: str) -> "pd.DataFrame":
    """2-year daily OHLCV via FMP — no yfinance."""
    try:
        return _fmp_history(ticker, period="2y", interval="1d")
    except Exception:
        return pd.DataFrame()


def run_rsi_backtest(
    ticker: str,
    rsi_oversold: float   = 30.0,
    rsi_overbought: float = 70.0,
    rsi_period: int       = 14,
    max_hold_days: int    = 20,
    initial_capital: float = 10_000.0,
    use_sma_filter: bool  = True,
    sma_period: int       = 200,
) -> dict | None:
    hist = _load_backtest_data(ticker)
    if hist.empty or len(hist) < max(sma_period + 50, 252):
        return None

    close = hist["Close"].copy()
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(rsi_period).mean()
    loss  = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rsi   = 100 - (100 / (1 + gain / loss))
    sma   = close.rolling(sma_period).mean()

    in_trade  = False
    entry_px  = 0.0
    entry_idx = 0
    trades: list[dict] = []

    for i in range(sma_period, len(close)):
        trend_ok = (close.iloc[i] > sma.iloc[i]) if use_sma_filter else True

        if not in_trade:
            if rsi.iloc[i] < rsi_oversold and rsi.iloc[i - 1] >= rsi_oversold and trend_ok:
                in_trade  = True
                entry_px  = close.iloc[i]
                entry_idx = i
        else:
            hold_days   = i - entry_idx
            exit_signal = (
                (rsi.iloc[i] > rsi_overbought and rsi.iloc[i - 1] <= rsi_overbought)
                or hold_days >= max_hold_days
            )
            if exit_signal:
                exit_px = close.iloc[i]
                pnl_pct = (exit_px - entry_px) / entry_px * 100
                trades.append({
                    "Entry Date":  hist.index[entry_idx].date(),
                    "Exit Date":   hist.index[i].date(),
                    "Entry Price": round(entry_px, 2),
                    "Exit Price":  round(exit_px, 2),
                    "P&L %":       round(pnl_pct, 2),
                    "Hold (days)": hold_days,
                    "Exit Reason": "RSI Overbought" if rsi.iloc[i] > rsi_overbought else "Max Hold",
                    "Result":      "✅ Win" if pnl_pct > 0 else "❌ Loss",
                })
                in_trade = False

    if not trades:
        return None

    trades_df = pd.DataFrame(trades)

    equity = [initial_capital]
    for ret in trades_df["P&L %"]:
        equity.append(equity[-1] * (1 + ret / 100))
    strategy_equity = pd.Series(equity, name="Strategy")

    bh_start_price = close.iloc[sma_period]
    bh_equity      = close.iloc[sma_period:] / bh_start_price * initial_capital
    bh_equity.name = "Buy & Hold"

    # Daily mark-to-market — index is tz-naive (stripped above), dates are tz-naive
    daily_equity = pd.Series(initial_capital, index=hist.index)
    capital_now  = initial_capital
    for trade in trades:
        # pd.Timestamp from a date object → tz-naive; hist.index also tz-naive → no TypeError
        entry_ts = pd.Timestamp(trade["Entry Date"])
        exit_ts  = pd.Timestamp(trade["Exit Date"])
        mask     = (hist.index >= entry_ts) & (hist.index <= exit_ts)   # ← FIX
        entry_p  = trade["Entry Price"]
        daily_equity[mask] = capital_now * (close[mask] / entry_p)
        capital_now *= (1 + trade["P&L %"] / 100)
    daily_equity      = daily_equity.ffill()
    daily_equity.name = "Strategy (Daily)"

    n_trades      = len(trades_df)
    win_rate      = (trades_df["P&L %"] > 0).mean() * 100
    avg_win       = trades_df[trades_df["P&L %"] > 0]["P&L %"].mean() if win_rate > 0 else 0
    avg_loss      = trades_df[trades_df["P&L %"] <= 0]["P&L %"].mean() if win_rate < 100 else 0
    total_ret     = (equity[-1] / initial_capital - 1) * 100
    bh_ret        = (close.iloc[-1] / close.iloc[sma_period] - 1) * 100
    alpha         = total_ret - bh_ret
    wins_sum      = abs(trades_df[trades_df["P&L %"] > 0]["P&L %"].sum())
    losses_sum    = abs(trades_df[trades_df["P&L %"] <= 0]["P&L %"].sum() or 1)
    profit_factor = wins_sum / losses_sum
    max_dd        = _max_drawdown(pd.Series((daily_equity / initial_capital - 1) * 100))
    avg_hold      = trades_df["Hold (days)"].mean()

    metrics = {
        "Strategy Return":   f"{total_ret:+.2f}%",
        "Buy & Hold Return": f"{bh_ret:+.2f}%",
        "Alpha":             f"{alpha:+.2f}%",
        "Win Rate":          f"{win_rate:.1f}%",
        "Avg Win":           f"{avg_win:+.2f}%",
        "Avg Loss":          f"{avg_loss:+.2f}%",
        "Profit Factor":     f"{profit_factor:.2f}×",
        "Max Drawdown":      f"{max_dd:.1f}%",
        "# Trades":          n_trades,
        "Avg Hold (days)":   f"{avg_hold:.1f}",
    }

    return {
        "trades":       trades_df,
        "equity_curve": pd.concat([daily_equity, bh_equity], axis=1).dropna(),
        "trade_equity": strategy_equity,
        "metrics":      metrics,
        "rsi_series":   rsi,
        "close_series": close,
        "bh_ret":       bh_ret,
        "total_ret":    total_ret,
    }


def render_backtest_tab(ticker: str) -> None:
    st.markdown("### 📉 RSI Mean-Reversion Strategy Backtester")
    st.caption(
        "**Entry:** RSI crosses below oversold (+ optional 200-SMA trend filter)  |  "
        "**Exit:** RSI crosses above overbought OR max hold days reached"
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        oversold = st.number_input(
            "RSI Buy Below", 10, 40, 30, key=f"bt_os_{ticker}",
            help="Enter when RSI falls below this threshold (oversold zone).",
        )
    with c2:
        overbought = st.number_input(
            "RSI Sell Above", 60, 90, 70, key=f"bt_ob_{ticker}",
            help="Exit when RSI rises above this threshold (overbought zone).",
        )
    with c3:
        max_hold = st.number_input(
            "Max Hold Days", 5, 60, 20, key=f"bt_mh_{ticker}",
            help="Force-exit a trade after this many trading days regardless of RSI.",
        )
    with c4:
        sma_filt = st.toggle(
            "200-SMA Filter", value=True, key=f"bt_sma_{ticker}",
            help="Only enter trades when price is above the 200-day SMA (trend filter).",
        )
    with c5:
        capital = st.number_input(
            "Start Capital ($)", 1000, 1_000_000, 10_000, step=1000,
            key=f"bt_cap_{ticker}",
            help="Simulated starting portfolio value in USD.",
        )

    with st.spinner("⚙️ Running backtest…"):
        result = run_rsi_backtest(
            ticker,
            rsi_oversold=float(oversold),
            rsi_overbought=float(overbought),
            max_hold_days=int(max_hold),
            initial_capital=float(capital),
            use_sma_filter=bool(sma_filt),
        )

    if not result:
        st.info("⚠️ No trades generated with these parameters over the last 2 years. "
                "Try loosening RSI thresholds (e.g. Buy < 35, Sell > 65).")
        return

    metrics = result["metrics"]
    alpha   = result["total_ret"] - result["bh_ret"]
    alpha_c = "🟢" if alpha > 0 else "🔴"

    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    with mc1:
        st.metric("Strategy Return", metrics["Strategy Return"],
                  f"vs B&H {metrics['Buy & Hold Return']}",
                  help="Cumulative return from all RSI strategy trades combined.")
    with mc2:
        st.metric("Alpha", metrics["Alpha"], alpha_c,
                  help="Excess return versus a passive buy-and-hold strategy.")
    with mc3:
        st.metric("Win Rate", metrics["Win Rate"],
                  help="Percentage of trades that closed with a positive P&L.")
    with mc4:
        st.metric("Profit Factor", metrics["Profit Factor"],
                  help="Gross wins ÷ gross losses. A value above 1.5 is considered solid.")
    with mc5:
        st.metric("Max Drawdown", metrics["Max Drawdown"],
                  help="Largest peak-to-trough loss in the strategy equity curve.")

    # Equity curve chart
    eq = result["equity_curve"].dropna()
    fig_eq = go.Figure()
    if "Strategy (Daily)" in eq.columns:
        fig_eq.add_trace(go.Scatter(
            x=eq.index, y=eq["Strategy (Daily)"], name="RSI Strategy",
            line=dict(color="#58a6ff", width=2.5),
            fill="tozeroy", fillcolor="rgba(88,166,255,0.07)",
        ))
    if "Buy & Hold" in eq.columns:
        fig_eq.add_trace(go.Scatter(
            x=eq.index, y=eq["Buy & Hold"], name="Buy & Hold",
            line=dict(color="#f0f6fc", width=2, dash="dot"),
        ))
    fig_eq.add_hline(y=float(capital), line_dash="dot",
                     line_color="rgba(255,255,255,0.2)", annotation_text="Start Capital")
    fig_eq.update_layout(
        template="plotly_dark", height=380,
        title="📈 Strategy vs Buy & Hold — Portfolio Value",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified", font=dict(color="#f0f6fc"),
        yaxis_title="Portfolio Value ($)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_eq, use_container_width=True)

    # RSI chart with trade markers
    rsi_s  = result["rsi_series"]
    trades = result["trades"]
    fig_rsi = go.Figure()
    fig_rsi.add_trace(go.Scatter(
        x=rsi_s.index, y=rsi_s.values, name="RSI (14)",
        line=dict(color="#e3b341", width=1.8),
    ))
    fig_rsi.add_hline(y=oversold,   line_dash="dot", line_color="#26a69a",
                      annotation_text=f"Buy ≤ {oversold}")
    fig_rsi.add_hline(y=overbought, line_dash="dot", line_color="#ef5350",
                      annotation_text=f"Sell ≥ {overbought}")

    entry_dates = pd.to_datetime(trades["Entry Date"])
    exit_dates  = pd.to_datetime(trades["Exit Date"])
    entry_rsi   = rsi_s.reindex(entry_dates, method="nearest")
    exit_rsi    = rsi_s.reindex(exit_dates,  method="nearest")
    fig_rsi.add_trace(go.Scatter(
        x=entry_rsi.index, y=entry_rsi.values, mode="markers",
        name="Buy Signal", marker=dict(symbol="triangle-up", size=10, color="#26a69a"),
    ))
    fig_rsi.add_trace(go.Scatter(
        x=exit_rsi.index, y=exit_rsi.values, mode="markers",
        name="Sell Signal", marker=dict(symbol="triangle-down", size=10, color="#ef5350"),
    ))
    fig_rsi.update_layout(
        template="plotly_dark", height=280,
        title="RSI Oscillator with Trade Signals",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#f0f6fc"), yaxis_title="RSI", yaxis_range=[0, 100],
    )
    st.plotly_chart(fig_rsi, use_container_width=True)

    with st.expander(f"📋 Trade Log ({len(trades)} trades)"):
        # trades_df columns: Entry/Exit Date (date objects), Entry/Exit Price (float),
        # P&L % (float), Hold days (int), Exit Reason (str), Result (str).
        # Mixed numeric + str columns → ArrowTypeError. Format everything to str.
        display_trades = trades.copy()
        display_trades["Entry Date"]  = display_trades["Entry Date"].astype(str)
        display_trades["Exit Date"]   = display_trades["Exit Date"].astype(str)
        display_trades["Entry Price"] = display_trades["Entry Price"].apply(lambda v: f"${v:,.2f}")
        display_trades["Exit Price"]  = display_trades["Exit Price"].apply(lambda v: f"${v:,.2f}")
        display_trades["P&L %"]       = display_trades["P&L %"].apply(lambda v: f"{v:+.2f}%")
        display_trades["Hold (days)"] = display_trades["Hold (days)"].astype(str)
        st.dataframe(display_trades, use_container_width=True, hide_index=True)

    with st.expander("📊 Full Metrics"):
        # metrics dict contains a mix of str values and one raw int (# Trades).
        # Passing dict.items() directly to pd.DataFrame produces a "Value" column
        # of object dtype with mixed types → ArrowTypeError on Streamlit Cloud.
        # Cast every value to str to guarantee a uniform string column.
        st.dataframe(
            pd.DataFrame(
                {"Metric": list(metrics.keys()),
                 "Value":  [str(v) for v in metrics.values()]},
            ),
            use_container_width=True, hide_index=True,
        )

    st.caption("⚠️ Past performance ≠ future results. No commissions, slippage, or taxes modelled.")



# =============================================================================
# MODULE 4 — SUPABASE WATCHLIST MANAGER
# =============================================================================
