#!/usr/bin/env python3
"""
Portfolio analytics — volatility, correlation, diversification, Sortino, growth.
All metrics benchmarked against S&P 500 (SPY).
Output formatted for Slack.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# Add parent paths so we can import prices / portfolio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.expanduser("~/.openclaw"))

from portfolio import Portfolio

# ── AlphaVantage direct fetch (to avoid circular import issues) ────

ALPHAVANTAGE_API_KEY = "HJUI1TZ5H1QTYU4D"
ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"

import requests


def fetch_daily_closes_yahoo(symbol: str, days: int = 100) -> pd.Series:
    """Fallback: fetch daily closes from Yahoo Finance."""
    from datetime import datetime, timedelta
    end = datetime.now()
    start = end - timedelta(days=int(days * 1.5))
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "period1": int(start.timestamp()), "period2": int(end.timestamp())}
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    data = resp.json()
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes_list = result["indicators"]["quote"][0]["close"]
    closes = {}
    for ts_val, c in zip(timestamps, closes_list):
        if c is not None:
            d = datetime.fromtimestamp(ts_val).strftime("%Y-%m-%d")
            closes[d] = float(c)
    s = pd.Series(closes, name=symbol).sort_index()
    return s.iloc[-days:] if len(s) > days else s


def fetch_daily_closes(symbol: str, days: int = 100) -> pd.Series:
    """Fetch daily closing prices. Tries AlphaVantage first, falls back to Yahoo."""
    try:
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "apikey": ALPHAVANTAGE_API_KEY,
            "outputsize": "compact" if days <= 100 else "full",
        }
        time.sleep(3)  # rate limit: 5 calls/min
        resp = requests.get(ALPHAVANTAGE_BASE_URL, params=params, timeout=15)
        data = resp.json()

        ts = data.get("Time Series (Daily)")
        if not ts:
            raise ValueError(f"No data for {symbol}")

        dates_sorted = sorted(ts.keys())[-days:]
        closes = {d: float(ts[d]["4. close"]) for d in dates_sorted}
        return pd.Series(closes, name=symbol).sort_index()
    except Exception:
        # Fallback to Yahoo Finance
        return fetch_daily_closes_yahoo(symbol, days)


# ── analytics helpers ────────────────────────────────────────

def daily_returns(series: pd.Series) -> pd.Series:
    return series.pct_change().dropna()


def annualized_vol(returns: pd.Series) -> float:
    return float(returns.std() * np.sqrt(252))


def sortino_ratio(returns: pd.Series, target: float = 0.0) -> float:
    excess = returns - target / 252
    downside = excess[excess < 0]
    downside_std = float(np.sqrt((downside ** 2).mean())) * np.sqrt(252)
    if downside_std == 0:
        return float("inf")
    ann_return = float(returns.mean() * 252)
    return ann_return / downside_std


def growth(series: pd.Series) -> float:
    """Total return over the period."""
    if len(series) < 2:
        return 0.0
    return float((series.iloc[-1] / series.iloc[0]) - 1)


# ── main analysis ────────────────────────────────────────────

def run_analysis(portfolio_path: str = None, days: int = 90) -> str:
    port = Portfolio(portfolio_path)
    if not port.positions:
        return "❌ No positions found in portfolio."

    all_portfolio_symbols = [s for s in port.symbols()]
    symbols = [s for s in all_portfolio_symbols if s != "SPY"]  # non-SPY for analytics
    all_symbols = list(set(all_portfolio_symbols + ["SPY"]))  # ensure SPY fetched for benchmark

    # ── fetch prices ──
    price_data: dict[str, pd.Series] = {}
    errors = []
    for sym in all_symbols:
        try:
            price_data[sym] = fetch_daily_closes(sym, days)
        except Exception as e:
            errors.append(f"{sym}: {e}")

    if "SPY" not in price_data:
        return "❌ Could not fetch SPY benchmark data."

    # Align all series to common dates
    df = pd.DataFrame(price_data).dropna()
    if len(df) < 5:
        return "❌ Not enough overlapping price data."

    ret = df.pct_change().dropna()
    period_days = len(df)

    # ── portfolio weights (by current value) ──
    # Include ALL holdings (including SPY) for value/weight calculation
    values = {}
    for sym in all_portfolio_symbols:
        if sym in df.columns:
            pos = port.get_asset(sym)
            values[sym] = pos["quantity"] * df[sym].iloc[-1]
    total_val = sum(values.values())
    weights = {s: v / total_val for s, v in values.items()}

    # For analytics (vol, correlation, returns), use non-SPY symbols only
    active_symbols = [s for s in symbols if s in weights]
    # But track all holdings for display
    all_active = [s for s in all_portfolio_symbols if s in weights]

    # ── per-position volatility ──
    vols = {s: annualized_vol(ret[s]) for s in active_symbols}
    spy_vol = annualized_vol(ret["SPY"])

    # ── portfolio returns (weighted) ──
    port_ret = sum(weights[s] * ret[s] for s in active_symbols)
    port_vol = annualized_vol(port_ret)

    # ── weighted sum of individual vols ──
    weighted_vol_sum = sum(weights[s] * vols[s] for s in active_symbols)
    diversification = ((weighted_vol_sum - port_vol) / weighted_vol_sum * 100) if weighted_vol_sum > 0 else 0

    # ── correlation matrix ──
    corr = ret[active_symbols].corr()

    # ── Sortino ──
    port_sortino = sortino_ratio(port_ret)
    spy_sortino = sortino_ratio(ret["SPY"])

    # ── Growth ──
    # portfolio growth: weighted sum of individual growths
    port_growth = sum(weights[s] * growth(df[s]) for s in active_symbols)
    spy_growth = growth(df["SPY"])

    # ── current values ──
    current_total = total_val
    cost_total = sum(port.get_asset(s)["cost_basis"] for s in all_active)
    total_gl = current_total - cost_total
    total_gl_pct = (total_gl / cost_total * 100) if cost_total else 0

    # ── format output ──
    lines = []
    lines.append(f"📊 *Portfolio Report* ({period_days}-day analysis)")
    lines.append(f"_Generated {datetime.now().strftime('%b %d, %Y %I:%M %p')}_")
    lines.append("")

    # Holdings summary
    lines.append("*Holdings*")
    for s in all_active:
        pos = port.get_asset(s)
        cur_val = values[s]
        gl = cur_val - pos["cost_basis"]
        gl_pct = gl / pos["cost_basis"] * 100 if pos["cost_basis"] else 0
        lines.append(f"• `{s:5s}` {pos['quantity']:>9.3f} sh | ${cur_val:>10,.2f} ({weights[s]*100:.1f}%) | P/L: {'+' if gl >= 0 else ''}${gl:,.2f} ({'+' if gl_pct >= 0 else ''}{gl_pct:.1f}%)")
    lines.append(f"• *Total*: ${current_total:,.2f} | P/L: {'+' if total_gl >= 0 else ''}${total_gl:,.2f} ({'+' if total_gl_pct >= 0 else ''}{total_gl_pct:.1f}%)")
    lines.append("")

    # Volatility
    lines.append("*Annualized Volatility*")
    for s in active_symbols:
        lines.append(f"• `{s:5s}`: {vols[s]*100:.1f}%")
    lines.append(f"• *Portfolio*: {port_vol*100:.1f}%")
    lines.append(f"• *SPY (benchmark)*: {spy_vol*100:.1f}%")
    lines.append("")

    # Diversification
    lines.append("*Diversification Score*")
    lines.append(f"• {diversification:.1f}% (higher = more diversification benefit)")
    lines.append("")

    # Sortino
    lines.append("*Sortino Ratio* (0% risk-free)")
    lines.append(f"• Portfolio: {port_sortino:.2f}")
    lines.append(f"• SPY: {spy_sortino:.2f}")
    lines.append("")

    # Growth
    lines.append(f"*Growth ({period_days}-day)*")
    lines.append(f"• Portfolio: {'+' if port_growth >= 0 else ''}{port_growth*100:.2f}%")
    lines.append(f"• SPY: {'+' if spy_growth >= 0 else ''}{spy_growth*100:.2f}%")
    delta = port_growth - spy_growth
    lines.append(f"• Alpha: {'+' if delta >= 0 else ''}{delta*100:.2f}%")
    lines.append("")

    # Correlation matrix
    lines.append("*Correlation Matrix*")
    header = "       " + "  ".join(f"{s:>5s}" for s in active_symbols)
    lines.append(f"```{header}")
    for s1 in active_symbols:
        row = f"{s1:5s}  " + "  ".join(f"{corr.loc[s1, s2]:5.2f}" for s2 in active_symbols)
        lines.append(row)
    lines.append("```")

    if errors:
        lines.append("")
        lines.append("⚠️ *Errors*")
        for e in errors:
            lines.append(f"• {e}")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Portfolio analytics")
    parser.add_argument("--json", default=None, help="Path to portfolio JSON")
    parser.add_argument("--days", type=int, default=90, help="Analysis period in days")
    args = parser.parse_args()

    report = run_analysis(args.json, args.days)
    print(report)
