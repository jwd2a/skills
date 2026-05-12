#!/usr/bin/env python3
"""
Portfolio reporting at different cadences: daily, weekly, monthly, quarterly, yearly.
Slack-formatted output. Uses existing prices.py and analyze.py infrastructure.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from math import sqrt

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from portfolio import Portfolio
from prices import get_stock_price, get_stock_historical_alphavantage

# ── Config ──
ALPHAVANTAGE_API_KEY = "HJUI1TZ5H1QTYU4D"
ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"
SKIP_SYMBOLS = {"SPAXX", "SPAXX**", "FCASH"}

import requests


# ── Data fetching ──

def fetch_daily_closes(symbol: str, days: int = 100) -> pd.Series:
    """Fetch daily closing prices from Yahoo Finance. Returns pd.Series indexed by date string."""
    from datetime import datetime as _dt, timedelta as _td
    # Request extra calendar days to ensure enough trading days
    cal_days = int(days * 1.6) + 10
    end = int(_dt.now().timestamp())
    start = int((_dt.now() - _td(days=cal_days)).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"period1": start, "period2": end, "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    data = resp.json()
    result = data.get("chart", {}).get("result", [])
    if not result:
        err = data.get("chart", {}).get("error", {}).get("description", "unknown error")
        raise ValueError(f"No data for {symbol}: {err}")
    timestamps = result[0]["timestamp"]
    closes = result[0]["indicators"]["quote"][0]["close"]
    series = {}
    for ts_val, close in zip(timestamps, closes):
        if close is not None:
            date_str = _dt.fromtimestamp(ts_val).strftime("%Y-%m-%d")
            series[date_str] = close
    # Take the last N days requested
    all_dates = sorted(series.keys())[-days:]
    return pd.Series({d: series[d] for d in all_dates}, name=symbol).sort_index()


def get_live_quote(symbol: str) -> dict:
    """Get live quote via Finnhub (no rate limit issues)."""
    return get_stock_price(symbol, use_cache=False)


# ── Analytics helpers ──

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
    return float(returns.mean() * 252) / downside_std


def growth(series: pd.Series) -> float:
    if len(series) < 2:
        return 0.0
    return float((series.iloc[-1] / series.iloc[0]) - 1)


def fmt_pct(v: float) -> str:
    return f"{'+' if v >= 0 else ''}{v:.2f}%"


def fmt_dollar(v: float) -> str:
    return f"{'+' if v >= 0 else ''}${v:,.2f}"


def compute_trailing_stop_info(stock_prices: pd.Series, spy_prices: pd.Series) -> dict:
    """Compute trailing stop metrics for a single position."""
    LOOKBACK = 30
    VOL_MULTIPLIER = 1.5
    df = pd.DataFrame({"stock": stock_prices, "spy": spy_prices}).dropna()
    if len(df) < LOOKBACK + 1:
        return None
    recent = df.iloc[-LOOKBACK:]
    stock_ret = recent["stock"].pct_change().dropna()
    spy_ret = recent["spy"].pct_change().dropna()
    ann_vol = float(stock_ret.std() * sqrt(252))
    daily_vol = ann_vol / sqrt(252)
    cov = float(np.cov(stock_ret, spy_ret)[0, 1])
    spy_var = float(spy_ret.var())
    beta = cov / spy_var if spy_var > 0 else 1.0
    trailing_high = float(recent["stock"].max())
    spy_trailing_high = float(recent["spy"].max())
    current_price = float(df["stock"].iloc[-1])
    spy_current = float(df["spy"].iloc[-1])
    raw_drop = (trailing_high - current_price) / trailing_high
    spy_drop = (spy_trailing_high - spy_current) / spy_trailing_high
    adjusted_drop = raw_drop - beta * spy_drop
    threshold = VOL_MULTIPLIER * daily_vol
    remaining = threshold - adjusted_drop
    return {
        "current_price": current_price,
        "trailing_high": trailing_high,
        "ann_vol": ann_vol,
        "beta": beta,
        "stop_distance_pct": remaining * 100,
        "breached": remaining <= 0,
    }


# ── Report generators ──

def report_daily(port: Portfolio) -> str:
    """Short daily report using Finnhub live quotes, falling back to stored prices."""
    now = datetime.now()
    lines = [f"📊 *Daily Portfolio Report* — {now.strftime('%a %b %d, %Y')}"]
    lines.append("")

    symbols = [s for s in port.symbols() if s not in SKIP_SYMBOLS and s != "SPY"]

    # Fetch live quotes; detect if all prices came back zero (API unavailable)
    quotes = {}
    for sym in symbols + ["SPY"]:
        quotes[sym] = get_live_quote(sym)

    live_ok = any(quotes[s].get("price", 0) > 0 for s in symbols + ["SPY"])

    if not live_ok:
        # Fall back to stored last_price from portfolio.json
        lines.append("⚠️ _Live quotes unavailable — using stored prices from portfolio data_")
        lines.append("")
        total_value = 0.0
        position_data = []
        for sym in symbols:
            pos = port.get_asset(sym)
            price = pos.get("last_price", 0)
            val = price * pos["quantity"]
            gl = val - pos["cost_basis"]
            gl_pct = (gl / pos["cost_basis"] * 100) if pos["cost_basis"] else 0
            total_value += val
            position_data.append((sym, price, val, gl, gl_pct))

        spy_pos = port.get_asset("SPY")
        spy_price = spy_pos.get("last_price", 0) if spy_pos else 0
        if spy_pos:
            total_value += spy_price * spy_pos["quantity"]

        updated_at = getattr(port, "updated_at", "unknown")
        lines.append(f"*Portfolio Value*: ${total_value:,.2f}  _(as of {updated_at[:10]})_")
        lines.append(f"*Cash*: ${getattr(port, 'cash', 0):,.2f}" if hasattr(port, "cash") and port.cash else "")
        lines.append("")

        position_data.sort(key=lambda x: x[4], reverse=True)
        lines.append("*Positions (Total P/L from cost basis)*")
        for sym, price, val, gl, gl_pct in position_data:
            emoji = "🟢" if gl >= 0 else "🔴"
            lines.append(f"• {emoji} `{sym}`: ${price:,.2f} → ${val:,.2f} | P/L: {fmt_dollar(gl)} ({fmt_pct(gl_pct)})")

        if position_data:
            best = position_data[0]
            worst = position_data[-1]
            lines.append("")
            lines.append(f"⬆️ Best P/L: *{best[0]}* {fmt_pct(best[4])} | ⬇️ Worst P/L: *{worst[0]}* {fmt_pct(worst[4])}")

        lines.append(f"📈 SPY: ${spy_price:,.2f} (stored)" if spy_price else "📈 SPY: n/a")
        return "\n".join(l for l in lines if l is not None)

    # Live quotes available — normal path
    total_value = 0.0
    total_prev = 0.0
    position_changes = []

    for sym in symbols:
        q = quotes[sym]
        pos = port.get_asset(sym)
        price = q.get("price", 0)
        prev = q.get("previous_close", price)
        change = price - prev
        change_pct = (change / prev * 100) if prev else 0
        val = price * pos["quantity"]
        prev_val = prev * pos["quantity"]
        total_value += val
        total_prev += prev_val
        position_changes.append((sym, change, change_pct, val))

    spy_pos = port.get_asset("SPY")
    if spy_pos:
        spy_q = quotes["SPY"]
        total_value += spy_q.get("price", 0) * spy_pos["quantity"]
        total_prev += spy_q.get("previous_close", spy_q.get("price", 0)) * spy_pos["quantity"]

    day_change = total_value - total_prev
    day_change_pct = (day_change / total_prev * 100) if total_prev else 0

    lines.append(f"*Portfolio*: ${total_value:,.2f} | Today: {fmt_dollar(day_change)} ({fmt_pct(day_change_pct)})")
    lines.append("")

    position_changes.sort(key=lambda x: x[2], reverse=True)
    for sym, chg, chg_pct, val in position_changes:
        emoji = "🟢" if chg >= 0 else "🔴"
        lines.append(f"• {emoji} `{sym}`: {fmt_pct(chg_pct)} ({fmt_dollar(chg * port.get_asset(sym)['quantity'])})")

    best = position_changes[0]
    worst = position_changes[-1]
    lines.append("")
    lines.append(f"⬆️ Best: *{best[0]}* {fmt_pct(best[2])} | ⬇️ Worst: *{worst[0]}* {fmt_pct(worst[2])}")

    spy_q = quotes["SPY"]
    spy_chg_pct = float(str(spy_q.get("change_percent", "0")).replace("%", ""))
    lines.append(f"📈 SPY: {fmt_pct(spy_chg_pct)}")

    return "\n".join(lines)


def report_weekly(port: Portfolio) -> str:
    """Weekly report with trailing stop summary."""
    now = datetime.now()
    lines = [f"📊 *Weekly Portfolio Report* — {now.strftime('%a %b %d, %Y')}"]
    lines.append("")

    symbols = [s for s in port.symbols() if s not in SKIP_SYMBOLS and s != "SPY"]
    all_syms = symbols + ["SPY"]

    # Fetch historical data (need ~10 trading days)
    price_data = {}
    errors = []
    for sym in all_syms:
        try:
            price_data[sym] = fetch_daily_closes(sym, 15)
        except Exception as e:
            errors.append(f"{sym}: {e}")

    if "SPY" not in price_data:
        return "❌ Could not fetch SPY data."

    df = pd.DataFrame(price_data).dropna()
    if len(df) < 5:
        return "❌ Not enough data for weekly report."

    # Use last 5 trading days
    week_df = df.iloc[-6:]  # 6 rows = 5 day changes
    
    # Portfolio weekly performance
    total_value_now = 0
    total_value_week_ago = 0
    position_changes = []
    
    for sym in symbols:
        if sym not in week_df.columns:
            continue
        pos = port.get_asset(sym)
        now_price = week_df[sym].iloc[-1]
        week_ago_price = week_df[sym].iloc[0]
        chg_pct = (now_price / week_ago_price - 1) * 100
        val_now = now_price * pos["quantity"]
        val_then = week_ago_price * pos["quantity"]
        total_value_now += val_now
        total_value_week_ago += val_then
        position_changes.append((sym, chg_pct, val_now - val_then))

    # Include SPY position in total if held
    spy_pos = port.get_asset("SPY")
    if spy_pos and "SPY" in week_df.columns:
        total_value_now += week_df["SPY"].iloc[-1] * spy_pos["quantity"]
        total_value_week_ago += week_df["SPY"].iloc[0] * spy_pos["quantity"]

    port_chg_pct = (total_value_now / total_value_week_ago - 1) * 100 if total_value_week_ago else 0
    spy_chg_pct = (week_df["SPY"].iloc[-1] / week_df["SPY"].iloc[0] - 1) * 100

    lines.append(f"*Portfolio*: ${total_value_now:,.2f} | Week: {fmt_pct(port_chg_pct)} ({fmt_dollar(total_value_now - total_value_week_ago)})")
    lines.append(f"*SPY*: {fmt_pct(spy_chg_pct)}")
    lines.append("")

    # Position breakdown
    lines.append("*Positions*")
    position_changes.sort(key=lambda x: x[1], reverse=True)
    for sym, chg_pct, chg_dollar in position_changes:
        lines.append(f"• `{sym}`: {fmt_pct(chg_pct)} ({fmt_dollar(chg_dollar)})")
    lines.append("")

    # Trailing stop summary
    lines.append("*Trailing Stops*")
    spy_prices = price_data.get("SPY")
    for sym in symbols:
        if sym not in price_data:
            continue
        info = compute_trailing_stop_info(price_data[sym], spy_prices)
        if info:
            emoji = "🟢" if not info["breached"] else "🔴"
            lines.append(f"• {emoji} `{sym}`: {info['stop_distance_pct']:.1f}% to stop | Vol: {info['ann_vol']*100:.1f}%")
        else:
            lines.append(f"• ⚠️ `{sym}`: insufficient data")

    # Vol changes (compare current to historical)
    lines.append("")
    ret = df.pct_change().dropna()
    if len(ret) >= 5:
        lines.append("*Volatility (annualized)*")
        for sym in symbols:
            if sym in ret.columns:
                vol = annualized_vol(ret[sym])
                lines.append(f"• `{sym}`: {vol*100:.1f}%")

    if errors:
        lines.append("")
        for e in errors:
            lines.append(f"⚠️ {e}")

    return "\n".join(lines)


def _full_analytics_report(port: Portfolio, days: int, title: str, extras_fn=None) -> str:
    """Shared logic for monthly/quarterly/yearly reports."""
    now = datetime.now()
    lines = [f"📊 *{title}* — {now.strftime('%a %b %d, %Y')}"]
    lines.append("")

    symbols = [s for s in port.symbols() if s not in SKIP_SYMBOLS and s != "SPY"]
    all_syms = symbols + ["SPY"]

    price_data = {}
    errors = []
    for sym in all_syms:
        try:
            price_data[sym] = fetch_daily_closes(sym, days + 20)
        except Exception as e:
            errors.append(f"{sym}: {e}")

    if "SPY" not in price_data:
        return "❌ Could not fetch SPY data."

    df = pd.DataFrame(price_data).dropna()
    if len(df) < 10:
        return "❌ Not enough overlapping price data."

    ret = df.pct_change().dropna()
    period_days = len(df)

    # Portfolio weights by current value
    values = {}
    for sym in symbols:
        if sym in df.columns:
            pos = port.get_asset(sym)
            values[sym] = pos["quantity"] * df[sym].iloc[-1]
    total_val = sum(values.values())
    weights = {s: v / total_val for s, v in values.items()}
    active = [s for s in symbols if s in weights]

    # Per-position vol
    vols = {s: annualized_vol(ret[s]) for s in active}
    spy_vol = annualized_vol(ret["SPY"])

    # Portfolio returns
    port_ret = sum(weights[s] * ret[s] for s in active)
    port_vol = annualized_vol(port_ret)

    # Diversification
    weighted_vol_sum = sum(weights[s] * vols[s] for s in active)
    diversification = ((weighted_vol_sum - port_vol) / weighted_vol_sum * 100) if weighted_vol_sum > 0 else 0

    # Sortino
    port_sortino = sortino_ratio(port_ret)
    spy_sortino = sortino_ratio(ret["SPY"])

    # Growth
    port_growth = sum(weights[s] * growth(df[s]) for s in active)
    spy_growth = growth(df["SPY"])

    # Holdings P/L
    lines.append("*Holdings*")
    cost_total = 0
    for s in active:
        pos = port.get_asset(s)
        cur_val = values[s]
        gl = cur_val - pos["cost_basis"]
        gl_pct = gl / pos["cost_basis"] * 100 if pos["cost_basis"] else 0
        cost_total += pos["cost_basis"]
        # Period P/L
        start_val = pos["quantity"] * df[s].iloc[0]
        period_pl = cur_val - start_val
        period_pl_pct = (cur_val / start_val - 1) * 100 if start_val else 0
        lines.append(f"• `{s:5s}` ${cur_val:>10,.2f} ({weights[s]*100:.1f}%) | Period: {fmt_pct(period_pl_pct)} ({fmt_dollar(period_pl)}) | Total P/L: {fmt_dollar(gl)}")
    
    total_gl = total_val - cost_total
    total_gl_pct = (total_gl / cost_total * 100) if cost_total else 0
    lines.append(f"• *Total*: ${total_val:,.2f} | P/L: {fmt_dollar(total_gl)} ({fmt_pct(total_gl_pct)})")
    lines.append("")

    # Growth vs SPY
    lines.append(f"*Growth ({period_days}-day)*")
    lines.append(f"• Portfolio: {fmt_pct(port_growth * 100)}")
    lines.append(f"• SPY: {fmt_pct(spy_growth * 100)}")
    lines.append(f"• Alpha: {fmt_pct((port_growth - spy_growth) * 100)}")
    lines.append("")

    # Volatility
    lines.append("*Annualized Volatility*")
    for s in active:
        lines.append(f"• `{s}`: {vols[s]*100:.1f}%")
    lines.append(f"• *Portfolio*: {port_vol*100:.1f}% | *SPY*: {spy_vol*100:.1f}%")
    lines.append("")

    # Diversification & Sortino
    lines.append(f"*Diversification Score*: {diversification:.1f}%")
    lines.append(f"*Sortino Ratio*: Portfolio {port_sortino:.2f} | SPY {spy_sortino:.2f}")
    lines.append("")

    # Trailing stops
    lines.append("*Trailing Stops*")
    spy_prices = price_data.get("SPY")
    for sym in active:
        if sym not in price_data:
            continue
        info = compute_trailing_stop_info(price_data[sym], spy_prices)
        if info:
            emoji = "🟢" if not info["breached"] else "🔴"
            lines.append(f"• {emoji} `{sym}`: {info['stop_distance_pct']:.1f}% to stop | Beta: {info['beta']:.2f}")
    lines.append("")

    # Correlation matrix
    corr = ret[active].corr()
    lines.append("*Correlation Matrix*")
    header = "       " + "  ".join(f"{s:>5s}" for s in active)
    lines.append(f"```{header}")
    for s1 in active:
        row = f"{s1:5s}  " + "  ".join(f"{corr.loc[s1, s2]:5.2f}" for s2 in active)
        lines.append(row)
    lines.append("```")

    # Run extras (quarterly/yearly specific)
    if extras_fn:
        extra = extras_fn(df, ret, active, weights, port)
        if extra:
            lines.append("")
            lines.extend(extra)

    if errors:
        lines.append("")
        for e in errors:
            lines.append(f"⚠️ {e}")

    return "\n".join(lines)


def report_monthly(port: Portfolio) -> str:
    return _full_analytics_report(port, 30, "Monthly Portfolio Report")


def report_quarterly(port: Portfolio) -> str:
    def extras(df, ret, active, weights, port):
        lines = []
        # Momentum: compare first half vs second half growth
        mid = len(df) // 2
        lines.append("*Momentum Trend*")
        for s in active:
            first_half = growth(df[s].iloc[:mid])
            second_half = growth(df[s].iloc[mid:])
            trend = "📈 accelerating" if second_half > first_half else "📉 decelerating"
            lines.append(f"• `{s}`: {trend} (1st half: {fmt_pct(first_half*100)}, 2nd half: {fmt_pct(second_half*100)})")
        
        # Weight drift
        lines.append("")
        lines.append("*Weight Drift*")
        equal_weight = 1.0 / len(active) if active else 0
        for s in active:
            drift = (weights[s] - equal_weight) * 100
            lines.append(f"• `{s}`: {weights[s]*100:.1f}% (vs equal {equal_weight*100:.1f}%, drift: {fmt_pct(drift)})")

        return lines

    return _full_analytics_report(port, 90, "Quarterly Portfolio Report", extras)


def report_yearly(port: Portfolio) -> str:
    def extras(df, ret, active, weights, port):
        lines = []
        # Best/worst for the year
        growths = [(s, growth(df[s])) for s in active]
        growths.sort(key=lambda x: x[1], reverse=True)
        lines.append("*Year Performance Ranking*")
        for i, (s, g) in enumerate(growths):
            medal = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else "  "))
            lines.append(f"• {medal} `{s}`: {fmt_pct(g*100)}")

        # Diversification score using rolling windows
        lines.append("")
        lines.append("*Diversification Trend (quarterly windows)*")
        window = 63  # ~quarter
        if len(ret) >= window * 2:
            for i, label in enumerate(["Q1", "Q2", "Q3", "Q4"]):
                start = i * window
                end = start + window
                if end > len(ret):
                    break
                w_ret = ret.iloc[start:end]
                p_ret = sum(weights[s] * w_ret[s] for s in active)
                p_vol = annualized_vol(p_ret)
                w_vol_sum = sum(weights[s] * annualized_vol(w_ret[s]) for s in active)
                div = ((w_vol_sum - p_vol) / w_vol_sum * 100) if w_vol_sum > 0 else 0
                lines.append(f"• {label}: {div:.1f}%")

        return lines

    return _full_analytics_report(port, 252, "Yearly Portfolio Report", extras)


# ── Main ──

CADENCE_MAP = {
    "daily": report_daily,
    "weekly": report_weekly,
    "monthly": report_monthly,
    "quarterly": report_quarterly,
    "yearly": report_yearly,
}


def main():
    parser = argparse.ArgumentParser(description="Portfolio reporting at various cadences")
    parser.add_argument("--cadence", required=True, choices=CADENCE_MAP.keys(), help="Report cadence")
    parser.add_argument("--json", default=None, help="Path to portfolio JSON")
    args = parser.parse_args()

    port = Portfolio(args.json)
    if not port.positions:
        print("❌ No positions found in portfolio.")
        sys.exit(1)

    report_fn = CADENCE_MAP[args.cadence]
    print(report_fn(port))


if __name__ == "__main__":
    main()
