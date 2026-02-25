import os
import json
import requests
import yfinance as yf
import pandas as pd
from __future__ import annotations
import os
import json
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich.progress import track
from langchain_groq import ChatGroq

# ==================== CONFIGURATION ====================
# ── API Keys — set via environment variables in production ─────────────────
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY",  "")
FMP_API_KEY   = os.environ.get("FMP_API_KEY",   "")   # Financial Modeling Prep
NEWS_API_KEY  = os.environ.get("NEWS_API_KEY",  "")   # newsapi.org
ALPACA_KEY    = os.environ.get("ALPACA_KEY",    "")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET", "")
SUPABASE_URL  = os.environ.get("SUPABASE_URL",  "")
SUPABASE_KEY  = os.environ.get("SUPABASE_ANON_KEY", "")

os.environ["GROQ_API_KEY"] = GROQ_API_KEY
console = Console()
llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0)

# ==================== UPGRADE #2: RAG Prompt Template ====================
RAG_PROMPT = """You are a Senior Institutional Analyst at a top-tier investment bank.

CRITICAL GUARDRAILS — MUST FOLLOW WITHOUT EXCEPTION:
1. Base your ENTIRE analysis ONLY on the JSON data block below. It is the sole source of truth.
2. Do NOT use any fact from your training weights that is absent from the JSON.
3. For every number you cite, reference the exact JSON key name in parentheses.
4. Do NOT reference any historical events, prices, or data from 2022–2024 training.
5. Today is {date}. All JSON data is current as of this date.
6. If a value is missing from the JSON, say "Data unavailable."

LIVE DATA JSON:
{data}

TASK: Analyse {ticker}.

Provide:
1. **Investment Rating** (STRONG BUY / BUY / HOLD / SELL / STRONG SELL)
2. **Valuation Assessment** — cite specific JSON keys for every number used.
3. **3 Key Bullish Catalysts** (grounded in JSON metrics only)
4. **3 Key Risks / Thesis Killers**
5. **Technical Read** — RSI_14d and trend_vs_200SMA interpretation
6. **12-Month Price Target** with DCF/PEG rationale using JSON values
7. **One-Line Strategic Takeaway**

Be concise, data-driven, and professional."""

# ==================== UPGRADE #1: Professional Data Layer ====================

def get_stock_info(ticker: str) -> dict:
    """Fetch fundamentals — FMP primary, yfinance fallback."""
    if FMP_API_KEY:
        try:
            base    = "https://financialmodelingprep.com/api/v3"
            profile = requests.get(
                f"{base}/profile/{ticker}",
                params={"apikey": FMP_API_KEY}, timeout=8
            ).json()
            if profile and isinstance(profile, list):
                p = profile[0]
                return {
                    "symbol":       p.get("symbol"),
                    "longName":     p.get("companyName"),
                    "sector":       p.get("sector"),
                    "industry":     p.get("industry"),
                    "currentPrice": p.get("price"),
                    "marketCap":    p.get("mktCap"),
                    "forwardPE":    p.get("pe"),
                    "trailingPE":   p.get("pe"),
                    "pegRatio":     p.get("peg"),
                    "profitMargins":  p.get("netProfitMargin", 0) / 100 if p.get("netProfitMargin") else None,
                    "returnOnEquity": p.get("roe", 0) / 100 if p.get("roe") else None,
                    "revenueGrowth":  p.get("revenueGrowth", 0) / 100 if p.get("revenueGrowth") else None,
                    "earningsGrowth": p.get("epsgrowth", 0) / 100 if p.get("epsgrowth") else None,
                    "freeCashflow":   p.get("freeCashFlowPerShare", 0) * p.get("sharesOutstanding", 1) if p.get("freeCashFlowPerShare") else None,
                    "totalDebt":      p.get("totalDebt"),
                    "debtToEquity":   p.get("debtToEquity"),
                    "beta":           p.get("beta"),
                    "trailingEps":    p.get("eps"),
                    "forwardEps":     p.get("eps"),
                    "targetMeanPrice":p.get("dcf"),
                    "sharesOutstanding": p.get("sharesOutstanding"),
                    "totalRevenue":   p.get("revenue"),
                    "operatingMargins": p.get("operatingProfitMargin", 0) / 100 if p.get("operatingProfitMargin") else None,
                    "grossMargins":   p.get("grossProfitRatio"),
                    "_source": "FMP",
                }
        except Exception:
            pass

    info = yf.Ticker(ticker).info
    info["_source"] = "yfinance"
    return info


def get_stock_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Fetch OHLCV — always yfinance."""
    return yf.Ticker(ticker).history(period=period)


# ==================== UPGRADE #5: DCF Valuation ====================

def dcf_valuation(fcf, shares_outstanding, growth_rate=0.20, terminal_g=0.03, wacc=0.10, years=5):
    """5-year DCF intrinsic value per share."""
    try:
        if not fcf or not shares_outstanding or float(fcf) <= 0 or float(shares_outstanding) <= 0:
            return None
        fcf    = float(fcf)
        shares = float(shares_outstanding)
        cfs    = [fcf * (1 + growth_rate) ** i for i in range(1, years + 1)]
        pv_cf  = sum(cf / (1 + wacc) ** i for i, cf in enumerate(cfs, 1))
        tv     = cfs[-1] * (1 + terminal_g) / (wacc - terminal_g)
        return (pv_cf + tv / (1 + wacc) ** years) / shares
    except Exception:
        return None


# ==================== STYLING & FORMATTING ====================

def format_value(val, val_type="number"):
    if val in [None, "N/A"]:
        return "N/A"
    try:
        if pd.isna(val):
            return "N/A"
    except Exception:
        pass
    try:
        if val_type == "percent":
            return f"{float(val) * 100:.2f}%"
        elif val_type == "money":
            v = abs(float(val))
            if v >= 1e12: return f"${float(val)/1e12:.2f}T"
            if v >= 1e9:  return f"${float(val)/1e9:.2f}B"
            if v >= 1e6:  return f"${float(val)/1e6:.2f}M"
            return f"${float(val):,.2f}"
        else:
            return f"{float(val):.2f}"
    except Exception:
        return "N/A"


def get_quality_assessment(roe, margin):
    if roe is None or margin is None:
        return 0, "Insufficient Data", "⚪"
    roe_pct, margin_pct = float(roe) * 100, float(margin) * 100
    score  = (5 if roe_pct > 25 else 4 if roe_pct > 15 else 3 if roe_pct > 10 else 1)
    score += (5 if margin_pct > 20 else 3 if margin_pct > 10 else 1)
    if score >= 8: return score, f"Exceptional (ROE: {roe_pct:.1f}% | Margin: {margin_pct:.1f}%)", "🟢"
    if score >= 6: return score, f"Strong (ROE: {roe_pct:.1f}% | Margin: {margin_pct:.1f}%)", "🟡"
    return score, f"Weak (ROE: {roe_pct:.1f}% | Margin: {margin_pct:.1f}%)", "🔴"


# ==================== UPGRADE #3: ATR Position Sizing ====================

def calculate_atr(hist: pd.DataFrame, period: int = 14) -> float | None:
    try:
        tr = pd.concat([
            hist["High"] - hist["Low"],
            (hist["High"] - hist["Close"].shift(1)).abs(),
            (hist["Low"]  - hist["Close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])
    except Exception:
        return None


def position_size(account: float, risk_pct: float, atr: float, price: float, multiplier: float = 2.0):
    try:
        risk_dollars  = account * risk_pct
        stop_distance = atr * multiplier
        shares        = max(1, int(risk_dollars / stop_distance))
        return shares, price - stop_distance, stop_distance
    except Exception:
        return None, None, None


# ==================== UPGRADE #4: News & Structured Sentiment ====================

def get_news_structured(ticker: str, company_name: str = "") -> list:
    """Fetch news via NewsAPI (primary) or yfinance (fallback), score with AI."""
    articles = []

    if NEWS_API_KEY:
        try:
            query = f"{ticker} OR \"{company_name}\"" if company_name else f"{ticker} stock"
            resp  = requests.get(
                "https://newsapi.org/v2/everything",
                params={"q": query, "language": "en", "sortBy": "publishedAt",
                        "pageSize": 8, "apiKey": NEWS_API_KEY},
                timeout=8,
            ).json()
            if resp.get("status") == "ok":
                for art in resp.get("articles", [])[:8]:
                    articles.append({
                        "title":     art.get("title", ""),
                        "publisher": art.get("source", {}).get("name", ""),
                        "link":      art.get("url", ""),
                        "published": art.get("publishedAt", "")[:10],
                    })
        except Exception:
            pass

    if not articles:
        try:
            import urllib.parse
            for item in (yf.Ticker(ticker).news or [])[:8]:
                pub = item.get("providerPublishTime", 0)
                canonical = item.get("canonicalUrl", {})
                url = canonical.get("url", "") if isinstance(canonical, dict) else str(canonical)
                if not url:
                    raw = item.get("link", "") or item.get("url", "")
                    url = raw if raw and "/news/" in raw else \
                          f"https://news.google.com/search?q={urllib.parse.quote(item.get('title','') + ' ' + ticker)}"
                articles.append({
                    "title":     item.get("title", "Market Update"),
                    "publisher": item.get("publisher", "Financial News"),
                    "link":      url,
                    "published": datetime.fromtimestamp(pub).strftime("%Y-%m-%d") if pub else "N/A",
                })
        except Exception:
            pass

    enriched = []
    for art in articles:
        try:
            prompt = (
                f"Return ONLY valid JSON (no markdown): "
                f"{{\"sentiment\":\"Bullish|Bearish|Neutral\","
                f"\"score\":0.0-1.0,\"reason\":\"one sentence\"}} "
                f"for headline: '{art['title']}'"
            )
            raw  = llm.invoke(prompt).content.strip().replace("```json","").replace("```","").strip()
            data = json.loads(raw)
            s    = data.get("sentiment", "Neutral")
            art["sentiment"] = s if s in ("Bullish","Bearish","Neutral") else "Neutral"
            art["score"]     = float(data.get("score", 0.5))
            art["reason"]    = data.get("reason", "")
        except Exception:
            art.update({"sentiment": "Neutral", "score": 0.5, "reason": ""})
        enriched.append(art)

    enriched.sort(key=lambda x: abs(x["score"] - 0.5), reverse=True)
    return enriched


# ==================== DATA RETRIEVAL ====================

def get_peer_benchmarks(ticker):
    peer_map = {
        "AMZN": {"names": "Walmart, Microsoft, Alphabet", "tickers": ["WMT","MSFT","GOOGL"], "avg_pe": 32.0, "avg_roe": 0.22},
        "TSLA": {"names": "BYD, Rivian, Toyota",          "tickers": ["BYDDF","RIVN","TM"],  "avg_pe": 45.0, "avg_roe": 0.18},
        "NVDA": {"names": "AMD, Intel, Broadcom",         "tickers": ["AMD","INTC","AVGO"],  "avg_pe": 38.5, "avg_roe": 0.25},
        "AAPL": {"names": "Microsoft, Alphabet, Samsung", "tickers": ["MSFT","GOOGL","SSNLF"],"avg_pe": 28.0,"avg_roe": 0.35},
        "MSFT": {"names": "Apple, Google, Amazon",        "tickers": ["AAPL","GOOGL","AMZN"],"avg_pe": 30.0, "avg_roe": 0.38},
    }
    return peer_map.get(ticker, {"names": "Industry Average", "tickers": ["SPY"], "avg_pe": 22.0, "avg_roe": 0.15})


def calculate_technical_signals(hist: pd.DataFrame) -> dict | None:
    try:
        close  = hist["Close"]
        delta  = close.diff()
        gain   = delta.where(delta > 0, 0).rolling(14).mean()
        loss   = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi    = 100 - (100 / (1 + gain / loss))
        exp1   = close.ewm(span=12, adjust=False).mean()
        exp2   = close.ewm(span=26, adjust=False).mean()
        macd   = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        return {
            "rsi":         rsi.iloc[-1],
            "sma_20":      close.rolling(20).mean().iloc[-1],
            "sma_50":      close.rolling(50).mean().iloc[-1],
            "sma_200":     close.rolling(200).mean().iloc[-1],
            "macd":        macd.iloc[-1],
            "macd_signal": signal.iloc[-1],
        }
    except Exception:
        return None


# ==================== UPGRADE #6: Backtesting ====================

def run_backtest(hist: pd.DataFrame) -> dict | None:
    """RSI oversold + 200 SMA trend-filter strategy."""
    try:
        if len(hist) < 252:
            return None
        close  = hist["Close"].copy()
        delta  = close.diff()
        rsi    = 100 - (100 / (1 + delta.where(delta>0,0).rolling(14).mean() /
                                   (-delta.where(delta<0,0)).rolling(14).mean()))
        sma200 = close.rolling(200).mean()

        trades, in_trade, entry_px, entry_idx = [], False, 0.0, 0
        for i in range(200, len(close)):
            if not in_trade and rsi.iloc[i] < 30 and close.iloc[i] > sma200.iloc[i]:
                in_trade, entry_px, entry_idx = True, close.iloc[i], i
            elif in_trade and (rsi.iloc[i] > 70 or i - entry_idx >= 20):
                ret = (close.iloc[i] - entry_px) / entry_px
                trades.append({"return_pct": ret * 100, "entry": entry_px, "exit": close.iloc[i], "hold": i-entry_idx})
                in_trade = False

        if not trades:
            return None
        df = pd.DataFrame(trades)
        equity = [100.0]
        for r in df["return_pct"]:
            equity.append(equity[-1] * (1 + r / 100))
        return {
            "trades": df, "total_return": df["return_pct"].sum(),
            "win_rate": (df["return_pct"] > 0).mean() * 100,
            "avg_return": df["return_pct"].mean(), "n_trades": len(df),
            "equity": pd.Series(equity),
        }
    except Exception:
        return None


# ==================== UPGRADE #7: Beta & Correlation ====================

def compute_rolling_beta(hist: pd.DataFrame, window: int = 90) -> pd.Series | None:
    try:
        spy     = yf.Ticker("SPY").history(period="1y")["Close"].pct_change()
        stock   = hist["Close"].pct_change()
        aligned = pd.concat([stock.rename("s"), spy.rename("m")], axis=1).dropna()
        if len(aligned) < window:
            return None
        cov  = aligned["s"].rolling(window).cov(aligned["m"])
        var  = aligned["m"].rolling(window).var()
        return (cov / var).dropna()
    except Exception:
        return None


# ==================== UPGRADE #9: Supabase Persistence ====================

def _supabase():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            from supabase import create_client
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception:
            pass
    return None


def save_watchlist(user_id: str, ticker: str, note: str = "") -> bool:
    c = _supabase()
    if not c: return False
    try:
        c.table("watchlists").insert({"user_id": user_id, "ticker": ticker, "note": note}).execute()
        return True
    except Exception:
        return False


def get_watchlist(user_id: str) -> list:
    c = _supabase()
    if not c: return []
    try:
        return c.table("watchlists").select("*").eq("user_id", user_id).execute().data or []
    except Exception:
        return []


# ==================== UPGRADE #10: Alpaca Broker ====================

def place_alpaca_order(ticker: str, qty: int, side: str = "buy"):
    if not (ALPACA_KEY and ALPACA_SECRET):
        return None, "Alpaca keys not configured"
    try:
        import alpaca_trade_api as tradeapi
        api   = tradeapi.REST(ALPACA_KEY, ALPACA_SECRET, base_url="https://paper-api.alpaca.markets")
        order = api.submit_order(symbol=ticker, qty=qty, side=side, type="market", time_in_force="day")
        return order, None
    except Exception as e:
        return None, str(e)


# ==================== MAIN DATA AGGREGATOR ====================

def get_comprehensive_data(ticker: str, account: float = 10000, risk_pct: float = 0.01,
                           atr_mult: float = 2.0, dcf_growth: float = 0.20, dcf_wacc: float = 0.10) -> dict | None:
    """Fetch all data and compute all derived metrics."""
    try:
        console.print(f"[dim]Fetching data via {'FMP' if FMP_API_KEY else 'yfinance'}...[/dim]")
        info = get_stock_info(ticker)
        hist = get_stock_history(ticker, "1y")

        if hist.empty:
            return None

        current_price   = float(info.get("currentPrice") or hist["Close"].iloc[-1])
        prev_close      = float(info.get("previousClose") or hist["Close"].iloc[-2] if len(hist) > 1 else current_price)
        revenue_growth  = float(info.get("revenueGrowth")  or 0.10)
        earnings_growth = float(info.get("earningsGrowth") or revenue_growth)
        profit_margin   = float(info.get("profitMargins")  or 0.10)

        # Fair value (Rule-of-40 PEG + FCF yield)
        eps         = float(info.get("forwardEps") or info.get("trailingEps") or 1.0)
        rule_of_40  = (revenue_growth * 100) + (profit_margin * 100)
        peg_mult    = 2.5 if rule_of_40 >= 60 else 1.8 if rule_of_40 >= 40 else 1.2 if rule_of_40 >= 20 else 0.8
        fair_pe     = max(10, min(earnings_growth * 100 * peg_mult, 80))
        peg_fv      = eps * fair_pe

        market_cap  = float(info.get("marketCap") or current_price * 1e9)
        fcf         = info.get("freeCashflow")
        if fcf and market_cap > 0:
            disc_rate = max(0.03, 0.085 - revenue_growth * 0.3)
            fcf_fv    = (float(fcf) / market_cap) / disc_rate * current_price
        else:
            fcf_fv = peg_fv

        # DCF model
        dcf_val      = dcf_valuation(fcf, info.get("sharesOutstanding"), dcf_growth, wacc=dcf_wacc)
        analyst_tgt  = float(info.get("targetMeanPrice") or current_price)

        if dcf_val:
            fair_value = (peg_fv * 0.35) + (fcf_fv * 0.25) + (dcf_val * 0.20) + (analyst_tgt * 0.20)
        else:
            fair_value = (peg_fv * 0.40) + (fcf_fv * 0.30) + (analyst_tgt * 0.30)

        # Position sizing (ATR)
        atr                          = calculate_atr(hist)
        shares_rec, stop_px, stop_dist = position_size(account, risk_pct, atr, current_price, atr_mult) if atr else (None, None, None)

        # News with structured sentiment
        company_name = info.get("longName", "")
        news         = get_news_structured(ticker, company_name)
        bull_count   = sum(1 for n in news if n["sentiment"] == "Bullish")
        bear_count   = sum(1 for n in news if n["sentiment"] == "Bearish")

        # Rolling beta
        rolling_beta = compute_rolling_beta(hist)
        curr_beta    = float(rolling_beta.iloc[-1]) if rolling_beta is not None else None

        # Backtest
        bt = run_backtest(hist)

        return {
            "info":          info,
            "hist":          hist,
            "price":         current_price,
            "prev_close":    prev_close,
            "fair_value":    fair_value,
            "peg_fv":        peg_fv,
            "fcf_fv":        fcf_fv,
            "dcf_fv":        dcf_val,
            "analyst_tgt":   analyst_tgt,
            "bull_case":     fair_value * (1 + max(0.20, revenue_growth)),
            "base_case":     fair_value,
            "bear_case":     fair_value * (1 - max(0.15, revenue_growth * 0.5)),
            "rule_of_40":    rule_of_40,
            "peers":         get_peer_benchmarks(ticker),
            "technicals":    calculate_technical_signals(hist),
            "atr":           atr,
            "shares_rec":    shares_rec,
            "stop_price":    stop_px,
            "stop_dist":     stop_dist,
            "news":          news,
            "bull_news":     bull_count,
            "bear_news":     bear_count,
            "rolling_beta":  rolling_beta,
            "curr_beta":     curr_beta,
            "backtest":      bt,
            "_source":       info.get("_source", "yfinance"),
        }
    except Exception as e:
        console.print(f"[red]Error fetching data: {e}[/red]")
        return None


# ==================== DISPLAY FUNCTIONS ====================

def display_header(ticker, info):
    company = info.get("longName", ticker)
    sector  = info.get("sector", "N/A")
    src     = info.get("_source", "yfinance")
    t = Text()
    t.append("🐳 ", style="bold cyan")
    t.append(ticker, style="bold white")
    t.append(" | ", style="dim")
    t.append(company, style="bold blue")
    t.append(" | ", style="dim")
    t.append(sector, style="bold green")
    t.append(f"  [data: {src}]", style="dim")
    console.print(Rule(t, style="bold cyan"))
    console.print()


def display_market_snapshot(data):
    info      = data["info"]
    price     = data["price"]
    prev      = data["prev_close"]
    change    = price - prev
    change_pct= (change / prev * 100) if prev else 0

    table = Table(show_header=False, box=None, expand=True, padding=(0, 2))
    for _ in range(4): table.add_column(width=20)

    table.add_row("Current Price", f"${price:.2f}", "Change",
                  f"[{'green' if change >= 0 else 'red'}]{change:+.2f} ({change_pct:+.2f}%)[/]")
    table.add_row("Market Cap",  format_value(info.get("marketCap"), "money"),
                  "Volume",      f"{info.get('volume', 0):,}")
    table.add_row("52W High", f"${info.get('fiftyTwoWeekHigh', 0):.2f}" if info.get('fiftyTwoWeekHigh') else "N/A",
                  "52W Low",  f"${info.get('fiftyTwoWeekLow', 0):.2f}"  if info.get('fiftyTwoWeekLow')  else "N/A")
    if data.get("curr_beta"):
        table.add_row("Rolling Beta (90d)", f"{data['curr_beta']:.2f}", "Data Source", data.get("_source","yfinance"))

    console.print(Panel(table, title="📊 Market Snapshot", border_style="cyan"))
    console.print()


def display_quality_metrics(data):
    info = data["info"]
    score, desc, emoji = get_quality_assessment(info.get("returnOnEquity"), info.get("profitMargins"))
    table = Table(show_header=True, box=None, expand=True)
    table.add_column("Metric",     style="bold yellow")
    table.add_column("Value",      style="bold white")
    table.add_column("Assessment", style="bold green")
    table.add_row("Quality Score", f"{score}/10 {emoji}", desc)
    table.add_row("Forward P/E",   format_value(info.get("forwardPE")),          "Valuation Multiple")
    table.add_row("Profit Margin", format_value(info.get("profitMargins"), "percent"), "Profitability")
    table.add_row("Debt/Equity",   format_value(info.get("debtToEquity")),        "Financial Leverage")
    console.print(Panel(table, title="💎 Quality Assessment", border_style="yellow"))
    console.print()


def display_technical_analysis(data):
    tech  = data["technicals"]
    price = data["price"]
    if not tech:
        console.print("[yellow]Technical analysis unavailable[/yellow]")
        return
    table = Table(show_header=True, box=None, expand=True)
    table.add_column("Indicator", style="bold magenta")
    table.add_column("Value",     style="bold white")
    table.add_column("Signal",    style="bold green")

    rsi = tech["rsi"]
    table.add_row("RSI (14)",  f"{rsi:.2f}", "Overbought 🔴" if rsi > 70 else "Oversold 🟢" if rsi < 30 else "Neutral 🟡")
    table.add_row("200 SMA",  f"${tech['sma_200']:.2f}", "Bullish 🟢" if price > tech["sma_200"] else "Bearish 🔴")
    table.add_row("MACD",     f"{tech['macd']:.2f}", "Bullish 🟢" if tech["macd"] > tech["macd_signal"] else "Bearish 🔴")
    table.add_row("20 SMA",   f"${tech['sma_20']:.2f}",  "Short-term Support")
    table.add_row("50 SMA",   f"${tech['sma_50']:.2f}",  "Medium-term Support")
    console.print(Panel(table, title="📈 Technical Signals", border_style="magenta"))
    console.print()


def display_position_sizing(data):
    """Upgrade #3 — ATR position sizing display."""
    atr       = data.get("atr")
    shares    = data.get("shares_rec")
    stop_px   = data.get("stop_price")
    stop_dist = data.get("stop_dist")
    price     = data["price"]
    if not atr:
        console.print("[yellow]ATR unavailable — insufficient history.[/yellow]")
        return
    table = Table(show_header=True, box=None, expand=True)
    table.add_column("Parameter",  style="bold cyan")
    table.add_column("Value",      style="bold white")
    table.add_row("ATR (14-day)",      f"${atr:.2f}")
    table.add_row("Recommended Shares",f"{shares}")
    table.add_row("Stop-Loss Price",   f"${stop_px:.2f}")
    table.add_row("Stop Distance",     f"${stop_dist:.2f}")
    table.add_row("Position Value",    f"${shares * price:,.2f}" if shares else "N/A")
    console.print(Panel(table, title="⚖️ ATR Position Sizing", border_style="blue"))
    console.print()


def display_peer_comparison(data):
    info  = data["info"]
    peers = data["peers"]
    ticker= info.get("symbol")
    pe    = float(info.get("forwardPE") or 0)
    prem  = ((pe / peers["avg_pe"]) - 1) * 100 if peers["avg_pe"] > 0 and pe > 0 else 0
    roe   = float(info.get("returnOnEquity") or 0)
    roe_v = ((roe / peers["avg_roe"]) - 1) * 100 if peers["avg_roe"] > 0 and roe > 0 else 0

    table = Table(show_header=True, box=None, expand=True)
    table.add_column("Metric",           style="bold green")
    table.add_column(ticker or "Stock",  style="bold white")
    table.add_column("Peer Avg",         style="bold cyan")
    table.add_column("Premium/Discount", style="bold yellow")
    table.add_row("Forward P/E", f"{pe:.2f}", f"{peers['avg_pe']:.2f}",
                  f"[{'red' if prem > 0 else 'green'}]{prem:+.1f}%[/]")
    table.add_row("ROE", format_value(roe, "percent"), format_value(peers["avg_roe"], "percent"),
                  f"[{'green' if roe_v > 0 else 'red'}]{roe_v:+.1f}%[/]")
    console.print(Panel(table, title=f"🏁 Peer Comparison: {peers['names']}", border_style="green"))
    console.print()


def display_valuation_scenarios(data):
    price = data["price"]
    table = Table(show_header=True, box=None, expand=True)
    table.add_column("Scenario",       style="bold white")
    table.add_column("Target Price",   style="bold cyan")
    table.add_column("Upside/Downside",style="bold yellow")
    table.add_column("Model",          style="dim")
    for label, val, model_key, color_key in [
        ("🟢 Bull Case", data["bull_case"], "peg_fv",   "green"),
        ("🟡 Base Case", data["base_case"], "fcf_fv",   "yellow"),
        ("🔴 Bear Case", data["bear_case"], "dcf_fv",   "red"),
        ("⚪ Current",   price,             None,       "white"),
    ]:
        upside = ((val / price) - 1) * 100
        m_str  = format_value(data.get(model_key)) if model_key else "—"
        c      = color_key if val != price else "white"
        table.add_row(label, f"${val:.2f}", f"[{c}]{upside:+.1f}%[/]", m_str)

    r40c = "🟢" if data["rule_of_40"] >= 40 else "🟡" if data["rule_of_40"] >= 20 else "🔴"
    dcf_str = f"  |  DCF: ${data['dcf_fv']:.2f}" if data.get("dcf_fv") else ""
    console.print(Panel(table, title=f"🎯 Valuation Framework  [Rule of 40: {data['rule_of_40']:.0f}% {r40c}{dcf_str}]",
                        border_style="white"))
    console.print()


def display_news(data):
    """Upgrade #4 — structured sentiment display."""
    news = data.get("news", [])
    if not news:
        console.print(Panel("[yellow]No recent news available.[/yellow]",
                             title="📰 Market Intelligence", border_style="magenta"))
        return
    table = Table(show_header=True, box=None, expand=True)
    table.add_column("Signal",    style="bold", width=8)
    table.add_column("Date",      style="dim",  width=12)
    table.add_column("Headline",  style="white", ratio=3)
    table.add_column("Conviction",style="cyan",  width=12)
    table.add_column("Source",    style="dim",   width=20)
    icon_map = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}
    for n in news[:8]:
        icon = icon_map.get(n.get("sentiment","Neutral"), "⚪")
        table.add_row(icon, n.get("published",""), n.get("title",""),
                      f"{n.get('score',0.5):.0%}", n.get("publisher",""))
    bull, bear = data.get("bull_news", 0), data.get("bear_news", 0)
    overall = "🟢 Net Bullish" if bull > bear else "🔴 Net Bearish" if bear > bull else "🟡 Mixed"
    console.print(Panel(table, title=f"📰 Market Intelligence — {overall} ({bull}B / {bear}Br)",
                        border_style="magenta"))
    console.print()


def display_backtest(data):
    """Upgrade #6 — backtest summary."""
    bt = data.get("backtest")
    if not bt:
        console.print("[dim]Backtest: insufficient history (need ≥252 trading days).[/dim]")
        return
    table = Table(show_header=True, box=None, expand=True)
    table.add_column("Metric",   style="bold cyan")
    table.add_column("Value",    style="bold white")
    table.add_row("Strategy Return", f"{bt['total_return']:+.1f}%")
    table.add_row("Win Rate",        f"{bt['win_rate']:.1f}%")
    table.add_row("Avg Trade Return",f"{bt['avg_return']:+.2f}%")
    table.add_row("# Trades",        str(bt["n_trades"]))
    console.print(Panel(table, title="📈 Backtest — RSI Oversold + 200 SMA Strategy", border_style="blue"))
    console.print()


def display_ai_verdict(data):
    """Upgrade #2 — RAG-enforced AI verdict."""
    info  = data["info"]
    tech  = data.get("technicals") or {}
    price = data["price"]
    ticker= info.get("symbol")

    with console.status("[bold cyan]🤖 Generating RAG-enforced verdict...[/bold cyan]"):
        try:
            rsi_str  = f"{tech.get('rsi', 'N/A'):.2f}" if isinstance(tech.get("rsi"), float) else "N/A"
            sma200   = tech.get("sma_200")
            trend    = ("Above" if price > sma200 else "Below") if sma200 else "N/A"
            dcf_str  = f"${data['dcf_fv']:.2f}" if data.get("dcf_fv") else "N/A"
            beta_str = f"{data['curr_beta']:.2f}" if data.get("curr_beta") else "N/A"

            live_data = {
                "ticker":           ticker,
                "currentPrice":     round(price, 2),
                "marketCap":        format_value(info.get("marketCap"), "money"),
                "forwardPE":        format_value(info.get("forwardPE")),
                "trailingPE":       format_value(info.get("trailingPE")),
                "pegRatio":         format_value(info.get("pegRatio")),
                "revenueGrowth":    format_value(info.get("revenueGrowth"), "percent"),
                "earningsGrowth":   format_value(info.get("earningsGrowth"), "percent"),
                "profitMargins":    format_value(info.get("profitMargins"), "percent"),
                "returnOnEquity":   format_value(info.get("returnOnEquity"), "percent"),
                "freeCashflow":     format_value(info.get("freeCashflow"), "money"),
                "debtToEquity":     format_value(info.get("debtToEquity")),
                "RSI_14d":          rsi_str,
                "trend_vs_200SMA":  trend,
                "analystTarget":    format_value(info.get("targetMeanPrice")),
                "blendedFairValue": f"${data['base_case']:.2f}",
                "dcfFairValue":     dcf_str,
                "rollingBeta":      beta_str,
                "newsSignal":       f"{data.get('bull_news',0)} Bullish / {data.get('bear_news',0)} Bearish",
                "sector":           info.get("sector", "N/A"),
            }

            prompt  = RAG_PROMPT.format(
                date=datetime.now().strftime("%B %Y"),
                ticker=ticker,
                data=json.dumps(live_data, indent=2),
            )
            verdict = llm.invoke(prompt)
            console.print(Panel(verdict.content,
                                title="🐳 Institutional Verdict (RAG-Enforced)",
                                border_style="bold cyan"))

            # Save to Supabase if configured
            if SUPABASE_URL:
                if save_watchlist("cli_user", ticker):
                    console.print("[dim]✅ Saved to watchlist.[/dim]")

            # Alpaca paper trading prompt
            if ALPACA_KEY and data.get("shares_rec"):
                v_upper = verdict.content.upper()
                if "STRONG BUY" in v_upper or ("BUY" in v_upper and "SELL" not in v_upper):
                    console.print()
                    confirm = console.input(
                        f"[bold yellow]⚡ Place paper BUY order: {data['shares_rec']} × {ticker} "
                        f"@ ~${price:.2f}? (y/n) >[/bold yellow] "
                    ).strip().lower()
                    if confirm == "y":
                        order, err = place_alpaca_order(ticker, data["shares_rec"], "buy")
                        if order:
                            console.print(f"[green]✅ Paper order placed: {order.id}[/green]")
                        else:
                            console.print(f"[red]Order failed: {err}[/red]")

        except Exception as e:
            console.print(f"[red]AI analysis unavailable: {e}[/red]")
    console.print()


def display_full_report(data):
    info   = data["info"]
    ticker = info.get("symbol", "")

    display_header(ticker, info)
    display_market_snapshot(data)
    display_quality_metrics(data)
    display_technical_analysis(data)
    display_position_sizing(data)       # Upgrade #3
    display_peer_comparison(data)
    display_valuation_scenarios(data)   # Upgrade #5 (DCF included)
    display_backtest(data)              # Upgrade #6
    display_news(data)                  # Upgrade #4
    display_ai_verdict(data)            # Upgrade #2

    console.print(Rule(style="dim"))
    console.print(f"[dim]Analysis completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                  f"Data: {data.get('_source','yfinance')}[/dim]")
    console.print()


# ==================== MAIN LOOP ====================

def main():
    console.clear()
    welcome = Text()
    welcome.append("🐳 ", style="bold cyan")
    welcome.append("WHALE TERMINAL ELITE v5.0", style="bold white")
    welcome.append(" 🐳", style="bold cyan")
    console.print()
    console.print(Panel(welcome, subtitle="Institutional-Grade Stock Intelligence | 10-Upgrade Build",
                        border_style="bold cyan"))
    console.print()

    # Configuration summary
    console.print("[dim]API Status:[/dim]")
    console.print(f"  {'✅' if FMP_API_KEY  else '⚠️ '} Data:    {'FMP'        if FMP_API_KEY  else 'yfinance (fallback)'}")
    console.print(f"  {'✅' if NEWS_API_KEY else '⚠️ '} News:    {'NewsAPI'    if NEWS_API_KEY else 'yfinance (fallback)'}")
    console.print(f"  {'✅' if SUPABASE_URL else '⚠️ '} Storage: {'Supabase'   if SUPABASE_URL else 'not connected'}")
    console.print(f"  {'✅' if ALPACA_KEY   else '⚠️ '} Broker:  {'Alpaca Paper' if ALPACA_KEY else 'not connected'}")
    console.print()

    # Risk parameters
    try:
        account  = float(console.input("[cyan]Account size ($) [10000]: [/cyan]").strip() or "10000")
        risk_pct = float(console.input("[cyan]Risk per trade (%) [1.0]: [/cyan]").strip() or "1.0") / 100
    except ValueError:
        account, risk_pct = 10000.0, 0.01

    while True:
        ticker_input = console.input("\n[bold cyan]Enter Ticker (or 'EXIT') >[/bold cyan] ").strip().upper()
        if ticker_input == "EXIT":
            console.print("\n[bold green]Thank you for using Whale Terminal Elite! 🐳[/bold green]\n")
            break
        if not ticker_input:
            console.print("[yellow]Please enter a valid ticker symbol.[/yellow]")
            continue

        console.print()
        with console.status(f"[bold blue]Analysing {ticker_input}...[/bold blue]"):
            data = get_comprehensive_data(ticker_input, account=account, risk_pct=risk_pct)

        if data:
            console.print()
            display_full_report(data)
        else:
            console.print(f"[red]Could not retrieve data for {ticker_input}.[/red]")


if __name__ == "__main__":
    main()
