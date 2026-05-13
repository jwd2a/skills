#!/usr/bin/env python3
"""
Momentum Screener — Scans the market for top momentum stocks.

Usage:
  python momentum_screener.py                          # Default: top 20 by 2-week momentum
  python momentum_screener.py --lookback 5             # 5-day momentum  
  python momentum_screener.py --lookback 20            # 20-day (1 month)
  python momentum_screener.py --top 10                 # Top 10 results
  python momentum_screener.py --min-price 10           # Min share price
  python momentum_screener.py --max-price 500          # Max share price
  python momentum_screener.py --min-volume 500000      # Min avg daily volume
  python momentum_screener.py --universe sp500         # sp500, nasdaq100, or full
  python momentum_screener.py --exclude AAPL,MSFT      # Exclude specific tickers
  python momentum_screener.py --json                   # JSON output
  python momentum_screener.py --compare                # Compare against current portfolio
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, "screener_cache")
FINNHUB_API_KEY = "d3r63jhr01qopgh74tlgd3r63jhr01qopgh74tm0"

# Universe definitions — curated lists of liquid, tradeable stocks
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Fallback: hardcoded top ~100 liquid tickers for when web scraping fails
TOP_LIQUID = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B", "UNH", "JNJ",
    "V", "XOM", "WMT", "JPM", "MA", "PG", "HD", "CVX", "MRK", "ABBV",
    "LLY", "PEP", "KO", "COST", "AVGO", "TMO", "MCD", "CSCO", "ACN", "ABT",
    "DHR", "NEE", "LIN", "TXN", "UNP", "PM", "RTX", "LOW", "HON", "AMGN",
    "IBM", "CAT", "BA", "GE", "SBUX", "INTC", "AMD", "QCOM", "INTU", "ISRG",
    "MDLZ", "ADI", "ADP", "REGN", "BKNG", "GILD", "VRTX", "SYK", "MMC", "DE",
    "CB", "SCHW", "BLK", "CI", "DUK", "SO", "CME", "CL", "MO", "ZTS",
    "SLB", "EOG", "APD", "FCX", "NEM", "EQIX", "PSA", "PLD", "AMT", "CCI",
    "SPG", "O", "WBA", "GLD", "EFA", "EEM", "IWM", "QQQ", "DIA", "VTI",
    "POWL", "CECO", "ONTO", "PLXS", "MOD", "CRS",  # From Justin's bullpen
    "BELFA",  # Current holding
]


def get_universe(universe: str) -> List[str]:
    """Get list of tickers for the specified universe."""
    if universe == "full":
        return TOP_LIQUID
    elif universe == "sp500":
        # Try to fetch S&P 500 list, fall back to hardcoded
        try:
            tickers = fetch_sp500_tickers()
            if tickers and len(tickers) > 400:
                return tickers
        except Exception:
            pass
        return TOP_LIQUID
    elif universe == "nasdaq100":
        return TOP_LIQUID[:50]  # Rough proxy
    elif universe == "bullpen":
        return ["POWL", "CECO", "ONTO", "PLXS", "MOD", "CRS"]
    else:
        return TOP_LIQUID


def fetch_sp500_tickers() -> List[str]:
    """Fetch S&P 500 tickers from Wikipedia."""
    try:
        import re
        resp = requests.get(SP500_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        # Parse the first table for tickers
        tickers = re.findall(r'<td><a[^>]*>([A-Z.]+)</a>', resp.text)
        return list(set(tickers))[:505]
    except Exception:
        return []


def fetch_yahoo_history(symbol: str, days: int = 30) -> Optional[List[Dict]]:
    """Fetch historical daily prices from Yahoo Finance."""
    end = int(datetime.now().timestamp())
    start = int((datetime.now() - timedelta(days=days + 10)).timestamp())  # Extra buffer for weekends
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "period1": start,
        "period2": end,
        "interval": "1d",
        "includePrePost": "false",
    }
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        
        timestamps = result[0].get("timestamp", [])
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = quotes.get("close", [])
        volumes = quotes.get("volume", [])
        
        if not timestamps or not closes:
            return None
        
        history = []
        for i, ts in enumerate(timestamps):
            if closes[i] is not None:
                history.append({
                    "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                    "close": closes[i],
                    "volume": volumes[i] if i < len(volumes) and volumes[i] else 0,
                })
        
        return history
    except Exception as e:
        return None


def calculate_momentum(history: List[Dict], lookback: int) -> Optional[Dict]:
    """Calculate momentum metrics from price history."""
    if not history or len(history) < lookback + 1:
        return None
    
    recent = history[-lookback:]
    current_price = recent[-1]["close"]
    start_price = recent[0]["close"]
    
    if start_price <= 0:
        return None
    
    # Raw momentum (return over lookback)
    raw_return = (current_price - start_price) / start_price
    
    # Average volume over period
    avg_volume = sum(d["volume"] for d in recent if d["volume"]) / max(len(recent), 1)
    
    # Volatility (daily returns std dev, annualized)
    daily_returns = []
    for i in range(1, len(recent)):
        if recent[i-1]["close"] > 0:
            daily_returns.append((recent[i]["close"] - recent[i-1]["close"]) / recent[i-1]["close"])
    
    if len(daily_returns) < 3:
        return None
    
    import statistics
    vol = statistics.stdev(daily_returns) * (252 ** 0.5)
    
    # Risk-adjusted momentum (return / vol)
    risk_adj = raw_return / vol if vol > 0 else 0
    
    # Consistency: what % of days were positive?
    up_days = sum(1 for r in daily_returns if r > 0)
    consistency = up_days / len(daily_returns)
    
    return {
        "current_price": round(current_price, 2),
        "start_price": round(start_price, 2),
        "return_pct": round(raw_return * 100, 2),
        "annualized_vol": round(vol * 100, 1),
        "risk_adjusted": round(risk_adj, 3),
        "avg_volume": int(avg_volume),
        "consistency": round(consistency * 100, 1),
        "days": len(recent),
    }


def load_current_portfolio() -> List[str]:
    """Load current portfolio tickers."""
    portfolio_path = os.path.join(SCRIPT_DIR, "portfolio.json")
    if not os.path.exists(portfolio_path):
        return []
    
    try:
        with open(portfolio_path) as f:
            data = json.load(f)
        if isinstance(data, dict) and "positions" in data:
            positions = data["positions"]
            if isinstance(positions, dict):
                return [sym for sym, p in positions.items() if p.get("quantity", 0) > 0]
            elif isinstance(positions, list):
                return [p["symbol"] for p in positions if p.get("quantity", 0) > 0]
        elif isinstance(data, list):
            return [p["symbol"] for p in data if p.get("quantity", 0) > 0]
    except Exception:
        return []
    return []


def screen(
    universe: str = "full",
    lookback: int = 10,
    top_n: int = 20,
    min_price: float = 5.0,
    max_price: float = 10000.0,
    min_volume: int = 100000,
    exclude: List[str] = None,
) -> List[Dict]:
    """Run the momentum screen."""
    tickers = get_universe(universe)
    if exclude:
        tickers = [t for t in tickers if t not in exclude]
    
    results = []
    total = len(tickers)
    
    for i, symbol in enumerate(tickers):
        if (i + 1) % 10 == 0:
            print(f"  Scanning {i+1}/{total}...", file=sys.stderr)
        
        history = fetch_yahoo_history(symbol, days=lookback + 15)
        if not history:
            continue
        
        momentum = calculate_momentum(history, lookback)
        if not momentum:
            continue
        
        # Apply filters
        if momentum["current_price"] < min_price or momentum["current_price"] > max_price:
            continue
        if momentum["avg_volume"] < min_volume:
            continue
        
        results.append({
            "symbol": symbol,
            **momentum,
        })
        
        # Rate limiting — Yahoo is generous but don't hammer it
        time.sleep(0.15)
    
    # Sort by raw return (primary), risk-adjusted (secondary)
    results.sort(key=lambda x: x["return_pct"], reverse=True)
    
    return results[:top_n]


def score_portfolio_fit(candidate_history: List[Dict], portfolio_histories: Dict[str, List[Dict]], lookback: int) -> Dict:
    """Score how well a candidate would fit into the current portfolio.
    
    Evaluates:
    - Correlation with existing positions (lower = better diversification)
    - Marginal impact on portfolio return
    - Marginal impact on portfolio volatility
    """
    import statistics
    
    if not portfolio_histories:
        return {"avg_correlation": 0, "diversification_value": 1.0, "portfolio_fit_score": 0.5}
    
    # Get daily returns for candidate
    cand_returns = []
    for i in range(1, min(lookback + 1, len(candidate_history))):
        if candidate_history[i-1]["close"] > 0:
            cand_returns.append(
                (candidate_history[i]["close"] - candidate_history[i-1]["close"]) / candidate_history[i-1]["close"]
            )
    
    if len(cand_returns) < 5:
        return {"avg_correlation": 0, "diversification_value": 0.5, "portfolio_fit_score": 0.5}
    
    # Calculate correlation with each existing position
    correlations = []
    for sym, hist in portfolio_histories.items():
        pos_returns = []
        for i in range(1, min(lookback + 1, len(hist))):
            if hist[i-1]["close"] > 0:
                pos_returns.append((hist[i]["close"] - hist[i-1]["close"]) / hist[i-1]["close"])
        
        # Align lengths
        min_len = min(len(cand_returns), len(pos_returns))
        if min_len < 5:
            continue
        
        cr = cand_returns[-min_len:]
        pr = pos_returns[-min_len:]
        
        # Pearson correlation
        try:
            mean_c = statistics.mean(cr)
            mean_p = statistics.mean(pr)
            cov = sum((cr[i] - mean_c) * (pr[i] - mean_p) for i in range(min_len)) / min_len
            std_c = statistics.stdev(cr)
            std_p = statistics.stdev(pr)
            if std_c > 0 and std_p > 0:
                corr = cov / (std_c * std_p)
                correlations.append(corr)
        except Exception:
            continue
    
    if not correlations:
        return {"avg_correlation": 0, "diversification_value": 0.5, "portfolio_fit_score": 0.5}
    
    avg_corr = statistics.mean(correlations)
    # Diversification value: lower correlation = higher value (scale 0-1)
    div_value = max(0, min(1, (1 - avg_corr) / 2))
    
    return {
        "avg_correlation": round(avg_corr, 3),
        "diversification_value": round(div_value, 3),
        "portfolio_fit_score": round(div_value, 3),  # Can be expanded with more factors
    }


def screen_with_portfolio_context(
    universe: str = "full",
    lookback: int = 10,
    top_n: int = 20,
    min_price: float = 5.0,
    max_price: float = 10000.0,
    min_volume: int = 100000,
    exclude: List[str] = None,
) -> Tuple[List[Dict], Dict]:
    """Run momentum screen with portfolio-aware scoring."""
    # First get current portfolio histories
    holdings = load_current_portfolio()
    portfolio_histories = {}
    
    if holdings:
        print(f"  Loading portfolio histories for {len(holdings)} positions...", file=sys.stderr)
        for sym in holdings:
            hist = fetch_yahoo_history(sym, days=lookback + 15)
            if hist:
                portfolio_histories[sym] = hist
            time.sleep(0.15)
    
    # Run base screen
    tickers = get_universe(universe)
    if exclude:
        tickers = [t for t in tickers if t not in exclude]
    
    results = []
    total = len(tickers)
    
    for i, symbol in enumerate(tickers):
        if (i + 1) % 10 == 0:
            print(f"  Scanning {i+1}/{total}...", file=sys.stderr)
        
        history = fetch_yahoo_history(symbol, days=lookback + 15)
        if not history:
            continue
        
        momentum = calculate_momentum(history, lookback)
        if not momentum:
            continue
        
        if momentum["current_price"] < min_price or momentum["current_price"] > max_price:
            continue
        if momentum["avg_volume"] < min_volume:
            continue
        
        # Score portfolio fit
        fit = score_portfolio_fit(history, portfolio_histories, lookback)
        
        # Combined score: momentum (60%) + diversification value (40%)
        # Normalize return to 0-1 range roughly (cap at 30%)
        norm_return = min(max(momentum["return_pct"] / 30, -1), 1)
        combined = 0.6 * norm_return + 0.4 * fit["diversification_value"]
        
        results.append({
            "symbol": symbol,
            **momentum,
            **fit,
            "combined_score": round(combined, 3),
        })
        
        time.sleep(0.15)
    
    # Sort by combined score
    results.sort(key=lambda x: x["combined_score"], reverse=True)
    
    return results[:top_n], portfolio_histories


def format_slack(results: List[Dict], lookback: int, current_holdings: List[str] = None) -> str:
    """Format results for Slack."""
    lines = [f":mag: _Momentum Screener — Top {len(results)} by {lookback}-day return_\n"]
    
    has_fit = any("avg_correlation" in r for r in results)
    
    for i, r in enumerate(results, 1):
        held = " :white_check_mark:" if current_holdings and r["symbol"] in current_holdings else ""
        fit_str = ""
        if has_fit and "avg_correlation" in r:
            corr = r["avg_correlation"]
            corr_emoji = ":large_green_circle:" if corr < 0.3 else (":yellow_circle:" if corr < 0.6 else ":red_circle:")
            fit_str = f" | {corr_emoji} Corr: {corr:.2f}"
        
        lines.append(
            f"{i}. `{r['symbol']}` ${r['current_price']} | "
            f"{r['return_pct']:+.2f}% | "
            f"Vol: {r['annualized_vol']}% | "
            f"RiskAdj: {r['risk_adjusted']} | "
            f"Up: {r['consistency']}% of days{fit_str}{held}"
        )
    
    if current_holdings:
        overlap = [r["symbol"] for r in results if r["symbol"] in current_holdings]
        if overlap:
            lines.append(f"\n:white_check_mark: = already in portfolio ({', '.join(overlap)})")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Momentum Stock Screener")
    parser.add_argument("--lookback", type=int, default=10, help="Lookback period in trading days (default: 10)")
    parser.add_argument("--top", type=int, default=20, help="Number of results (default: 20)")
    parser.add_argument("--min-price", type=float, default=5.0, help="Minimum share price")
    parser.add_argument("--max-price", type=float, default=10000.0, help="Maximum share price")
    parser.add_argument("--min-volume", type=int, default=100000, help="Minimum avg daily volume")
    parser.add_argument("--universe", default="full", choices=["full", "sp500", "nasdaq100", "bullpen"],
                       help="Stock universe to scan")
    parser.add_argument("--exclude", type=str, default="", help="Comma-separated tickers to exclude")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--compare", action="store_true", help="Compare against current portfolio")
    parser.add_argument("--portfolio", action="store_true", 
                       help="Portfolio-aware scoring (momentum + diversification fit)")
    
    args = parser.parse_args()
    
    exclude = [t.strip() for t in args.exclude.split(",") if t.strip()] if args.exclude else []
    
    print(f"Scanning {args.universe} universe ({args.lookback}-day lookback)...", file=sys.stderr)
    
    if args.portfolio:
        results, _ = screen_with_portfolio_context(
            universe=args.universe,
            lookback=args.lookback,
            top_n=args.top,
            min_price=args.min_price,
            max_price=args.max_price,
            min_volume=args.min_volume,
            exclude=exclude,
        )
        holdings = load_current_portfolio()
    else:
        results = screen(
            universe=args.universe,
            lookback=args.lookback,
            top_n=args.top,
            min_price=args.min_price,
            max_price=args.max_price,
            min_volume=args.min_volume,
            exclude=exclude,
        )
        holdings = load_current_portfolio() if args.compare else None
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_slack(results, args.lookback, holdings))


if __name__ == "__main__":
    main()
