#!/usr/bin/env python3
"""
Correlation-aware trailing stop monitor.
Decomposes each position's drawdown into market/sector-explained vs idiosyncratic.
Only alerts when the idiosyncratic component breaches vol-based thresholds.

Usage:
  python correlation_stops.py --status          # Full decomposition view
  python correlation_stops.py --check           # Daily check with alerts
  python correlation_stops.py --json PATH       # Custom portfolio path
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from math import sqrt

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from portfolio import Portfolio

# ── Config ──
ALPHAVANTAGE_API_KEY = "HJUI1TZ5H1QTYU4D"
ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"
FINNHUB_API_KEY = "d3r63jhr01qopgh74tlgd3r63jhr01qopgh74tm0"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corr_stops_state.json")
SKIP_SYMBOLS = {"SPAXX", "SPAXX**", "FCASH", "SPY", "GLD"}
LOOKBACK = 30  # days for vol/correlation
VOL_MULTIPLIER = 1.5
CONSECUTIVE_DAYS_THRESHOLD = 2

# Sector ETF mapping for sector-level decomposition
SECTOR_MAP = {
    "AAPL": "XLK",    # Tech
    "GOOGL": "XLK",   # Tech
    "MSFT": "XLK",    # Tech
    "WMT": "XLP",     # Consumer Staples
    "LLY": "XLV",     # Healthcare
    "EQIX": "XLRE",   # Real Estate
    "EFA": "EFA",     # International (is its own benchmark)
    "GLD": "GLD",     # Gold (is its own benchmark)
    "CRS": "XLI",     # Industrials
    "CME": "XLF",     # Financials
    "POWL": "XLI",    # Industrials
    "BELFA": "XLI",   # Industrials
    "CECO": "XLI",    # Industrials
    "ONTO": "XLK",    # Tech/Semis
    "PLXS": "XLK",    # Tech
    "MOD": "XLI",     # Industrials
}


def fetch_daily_closes_finnhub(symbol: str, days: int = 100) -> pd.Series:
    """Fetch daily closing prices from Finnhub (no rate limit issues)."""
    import time as _time
    end = int(datetime.now().timestamp())
    start = end - (days + 30) * 86400  # extra buffer for weekends
    url = f"https://finnhub.io/api/v1/stock/candle"
    params = {
        "symbol": symbol,
        "resolution": "D",
        "from": start,
        "to": end,
        "token": FINNHUB_API_KEY,
    }
    _time.sleep(0.3)  # light rate limiting
    resp = requests.get(url, params=params, timeout=15)
    data = resp.json()
    if data.get("s") != "ok" or not data.get("c"):
        raise ValueError(f"No Finnhub data for {symbol}")
    
    dates = [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in data["t"]]
    closes = data["c"]
    series = pd.Series(dict(zip(dates, closes)), name=symbol).sort_index()
    # Deduplicate dates (keep last)
    series = series[~series.index.duplicated(keep="last")]
    return series.iloc[-days:]


def fetch_daily_closes_av(symbol: str, days: int = 100) -> pd.Series:
    """Fetch daily closing prices from AlphaVantage (rate limited)."""
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "apikey": ALPHAVANTAGE_API_KEY,
        "outputsize": "compact" if days <= 100 else "full",
    }
    time.sleep(3)
    resp = requests.get(ALPHAVANTAGE_BASE_URL, params=params, timeout=15)
    data = resp.json()
    ts = data.get("Time Series (Daily)")
    if not ts:
        raise ValueError(f"No AV data for {symbol}: {data.get('Note') or data.get('Error Message') or 'unknown'}")
    dates_sorted = sorted(ts.keys())[-days:]
    closes = {d: float(ts[d]["4. close"]) for d in dates_sorted}
    return pd.Series(closes, name=symbol).sort_index()


def fetch_daily_closes(symbol: str, days: int = 100) -> pd.Series:
    """Fetch with Finnhub primary, AlphaVantage fallback."""
    try:
        return fetch_daily_closes_finnhub(symbol, days)
    except Exception:
        return fetch_daily_closes_av(symbol, days)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def compute_correlation_metrics(stock_prices: pd.Series, spy_prices: pd.Series, sector_prices: pd.Series = None):
    """
    Decompose a stock's drawdown into:
    1. Market-explained component (correlated with SPY)
    2. Sector-explained component (correlated with sector ETF, beyond market)
    3. Idiosyncratic component (stock-specific)
    
    Returns dict with full decomposition.
    """
    # Build aligned DataFrame
    frames = {"stock": stock_prices, "spy": spy_prices}
    if sector_prices is not None:
        frames["sector"] = sector_prices
    df = pd.DataFrame(frames).dropna()
    
    if len(df) < LOOKBACK + 1:
        raise ValueError(f"Not enough aligned data: {len(df)} days (need {LOOKBACK + 1})")
    
    recent = df.iloc[-LOOKBACK:]
    
    # Returns
    stock_ret = recent["stock"].pct_change().dropna()
    spy_ret = recent["spy"].pct_change().dropna()
    
    # Core stats
    ann_vol = float(stock_ret.std() * sqrt(252))
    daily_vol = ann_vol / sqrt(252)
    
    # Beta and R² with SPY
    cov_market = float(np.cov(stock_ret, spy_ret)[0, 1])
    spy_var = float(spy_ret.var())
    beta_market = cov_market / spy_var if spy_var > 0 else 1.0
    
    # R² = correlation²
    corr_market = float(np.corrcoef(stock_ret, spy_ret)[0, 1])
    r2_market = corr_market ** 2
    
    # Sector decomposition (if available and different from SPY)
    r2_sector = 0.0
    beta_sector = 0.0
    corr_sector = 0.0
    if sector_prices is not None and "sector" in recent.columns:
        sector_ret = recent["sector"].pct_change().dropna()
        # Align all three
        aligned = pd.DataFrame({"stock": stock_ret, "spy": spy_ret, "sector": sector_ret}).dropna()
        if len(aligned) > 5:
            corr_sector = float(np.corrcoef(aligned["stock"], aligned["sector"])[0, 1])
            r2_sector = corr_sector ** 2
            sector_var = float(aligned["sector"].var())
            beta_sector = float(np.cov(aligned["stock"], aligned["sector"])[0, 1]) / sector_var if sector_var > 0 else 0
    
    # Current drawdown from trailing high
    trailing_high = float(recent["stock"].max())
    spy_trailing_high = float(recent["spy"].max())
    current_price = float(df["stock"].iloc[-1])
    spy_current = float(df["spy"].iloc[-1])
    
    raw_drop_pct = (trailing_high - current_price) / trailing_high  # as fraction
    spy_drop_pct = (spy_trailing_high - spy_current) / spy_trailing_high
    
    # Decomposition of the drawdown:
    # Market-explained portion = beta * SPY_drop
    market_explained = beta_market * spy_drop_pct
    # Idiosyncratic = total drop - market explained
    idiosyncratic_drop = raw_drop_pct - market_explained
    # Clamp: idiosyncratic can't be negative (would mean stock outperformed market — not a concern)
    idiosyncratic_drop = max(0, idiosyncratic_drop)
    
    # Threshold: vol-based, applied to idiosyncratic portion only
    threshold = VOL_MULTIPLIER * daily_vol
    
    # How much of the total drop is explained by market correlation
    if raw_drop_pct > 0.001:  # avoid div by zero
        pct_market_explained = min(1.0, market_explained / raw_drop_pct)
    else:
        pct_market_explained = 1.0  # no real drop
    
    return {
        "current_price": current_price,
        "trailing_high": trailing_high,
        "ann_vol": ann_vol,
        "daily_vol": daily_vol,
        "beta_market": beta_market,
        "corr_market": corr_market,
        "r2_market": r2_market,
        "corr_sector": corr_sector,
        "r2_sector": r2_sector,
        "raw_drop_pct": raw_drop_pct,
        "spy_drop_pct": spy_drop_pct,
        "market_explained_drop": market_explained,
        "idiosyncratic_drop": idiosyncratic_drop,
        "pct_market_explained": pct_market_explained,
        "threshold": threshold,
        "breached": idiosyncratic_drop > threshold,
        "stop_distance": threshold - idiosyncratic_drop,
    }


def run_status(portfolio_path: str = None) -> str:
    """Full correlation-aware stop status with decomposition."""
    port = Portfolio(portfolio_path)
    symbols = [s for s in port.symbols() if s not in SKIP_SYMBOLS]
    
    try:
        spy_prices = fetch_daily_closes("SPY", 100)
    except Exception as e:
        return f"❌ Could not fetch SPY data: {e}"
    
    # Collect unique sector ETFs we need
    sector_etfs = set()
    for sym in symbols:
        etf = SECTOR_MAP.get(sym)
        if etf and etf not in ("SPY", "GLD", "EFA"):
            sector_etfs.add(etf)
    
    # Fetch sector ETFs
    sector_data = {}
    for etf in sector_etfs:
        try:
            sector_data[etf] = fetch_daily_closes(etf, 100)
        except Exception:
            pass  # skip if can't fetch
    
    lines = [
        "📊 *Correlation-Aware Stop Status*",
        f"_SPY drawdown from 30d high: {0:.1f}%_",  # placeholder, calculated below
    ]
    
    # Calculate SPY's own drawdown for context
    spy_recent = spy_prices.iloc[-LOOKBACK:]
    spy_high = float(spy_recent.max())
    spy_current = float(spy_prices.iloc[-1])
    spy_dd = (spy_high - spy_current) / spy_high * 100
    lines[1] = f"_SPY from 30d high: -{spy_dd:.1f}% (${spy_current:.2f} vs ${spy_high:.2f})_"
    lines.append("")
    
    errors = []
    
    for sym in symbols:
        try:
            sector_etf = SECTOR_MAP.get(sym)
            sector_prices = sector_data.get(sector_etf) if sector_etf else None
            
            prices = fetch_daily_closes(sym, 100)
            m = compute_correlation_metrics(prices, spy_prices, sector_prices)
            
            # Status icon
            if m["breached"]:
                icon = "🔴"
            elif m["stop_distance"] < 0.005:  # within 0.5%
                icon = "🟡"
            else:
                icon = "🟢"
            
            # Format the decomposition
            total_drop = m["raw_drop_pct"] * 100
            market_part = m["market_explained_drop"] * 100
            idio_part = m["idiosyncratic_drop"] * 100
            mkt_pct = m["pct_market_explained"] * 100
            
            line = (
                f"• {icon} *{sym}* ${m['current_price']:.2f} "
                f"(from high ${m['trailing_high']:.2f})\n"
                f"    Drop: {total_drop:.1f}% total → "
                f"{market_part:.1f}% market ({mkt_pct:.0f}%) + "
                f"{idio_part:.1f}% stock-specific\n"
                f"    R²: {m['r2_market']:.2f} | β: {m['beta_market']:.2f} | "
                f"Vol: {m['ann_vol']*100:.0f}% | "
                f"Stop gap: {m['stop_distance']*100:.1f}%"
            )
            lines.append(line)
            
        except Exception as e:
            errors.append(f"• ⚠️ {sym}: {e}")
    
    if errors:
        lines.append("")
        lines.extend(errors)
    
    lines.append("")
    lines.append("_🟢 = clear | 🟡 = close to stop | 🔴 = idiosyncratic breach_")
    lines.append("_Stops only trigger on stock-specific drops, not macro moves._")
    
    return "\n".join(lines)


def run_check(portfolio_path: str = None) -> str:
    """Daily check — only alerts on idiosyncratic breaches."""
    port = Portfolio(portfolio_path)
    symbols = [s for s in port.symbols() if s not in SKIP_SYMBOLS]
    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")
    
    try:
        spy_prices = fetch_daily_closes("SPY", 100)
    except Exception as e:
        return f"❌ Could not fetch SPY data: {e}"
    
    # Fetch sector ETFs
    sector_etfs = set()
    for sym in symbols:
        etf = SECTOR_MAP.get(sym)
        if etf and etf not in ("SPY", "GLD", "EFA"):
            sector_etfs.add(etf)
    sector_data = {}
    for etf in sector_etfs:
        try:
            sector_data[etf] = fetch_daily_closes(etf, 100)
        except Exception:
            pass
    
    alerts = []
    macro_holds = []
    
    for sym in symbols:
        try:
            sector_etf = SECTOR_MAP.get(sym)
            sector_prices = sector_data.get(sector_etf) if sector_etf else None
            prices = fetch_daily_closes(sym, 100)
            m = compute_correlation_metrics(prices, spy_prices, sector_prices)
            
            sym_state = state.get(sym, {"consecutive_breach_days": 0})
            
            if m["breached"]:
                sym_state["consecutive_breach_days"] = sym_state.get("consecutive_breach_days", 0) + 1
            else:
                sym_state["consecutive_breach_days"] = 0
            
            state[sym] = sym_state
            
            # Check if raw drop would have triggered old system but correlation saves it
            raw_would_trigger = m["raw_drop_pct"] > m["threshold"]
            if raw_would_trigger and not m["breached"]:
                macro_holds.append(
                    f"• *{sym}*: -{m['raw_drop_pct']*100:.1f}% total but "
                    f"{m['pct_market_explained']*100:.0f}% is market-correlated → holding"
                )
            
            if sym_state["consecutive_breach_days"] >= CONSECUTIVE_DAYS_THRESHOLD:
                alerts.append(
                    f"• *{sym}* — idiosyncratic drop of {m['idiosyncratic_drop']*100:.1f}% "
                    f"exceeds {VOL_MULTIPLIER}× vol ({m['threshold']*100:.1f}%) "
                    f"for {sym_state['consecutive_breach_days']} days\n"
                    f"  Total drop: {m['raw_drop_pct']*100:.1f}% | "
                    f"Market-explained: {m['market_explained_drop']*100:.1f}% | "
                    f"Stock-specific: {m['idiosyncratic_drop']*100:.1f}%\n"
                    f"  R² with SPY: {m['r2_market']:.2f} | "
                    f"Recommendation: Sell — this isn't just the market"
                )
                sym_state["consecutive_breach_days"] = 0
        
        except Exception as e:
            pass  # skip errors in check mode
    
    state["last_check_date"] = today
    save_state(state)
    
    output_parts = []
    
    if alerts:
        output_parts.append("🚨 *Idiosyncratic Stop Alert*\n" + "\n".join(alerts))
    
    if macro_holds:
        output_parts.append("🛡️ *Macro Filter Saved These*\n" + "\n".join(macro_holds))
    
    if not alerts and not macro_holds:
        output_parts.append("✅ All positions within stops. No idiosyncratic breakdowns detected.")
    elif not alerts:
        output_parts.append("✅ No idiosyncratic stop breaches.")
    
    return "\n\n".join(output_parts)


def main():
    parser = argparse.ArgumentParser(description="Correlation-aware trailing stop monitor")
    parser.add_argument("--check", action="store_true", help="Run daily check (alerts on idiosyncratic breach only)")
    parser.add_argument("--status", action="store_true", help="Show full decomposition")
    parser.add_argument("--json", default=None, help="Path to portfolio JSON")
    args = parser.parse_args()
    
    if args.status:
        print(run_status(args.json))
    elif args.check:
        print(run_check(args.json))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
