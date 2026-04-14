#!/usr/bin/env python3
"""
Volatility-based trailing stop monitor with beta adjustment.
Detects idiosyncratic drops (beyond market moves) using rolling vol and beta.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from portfolio import Portfolio

# ── Config ──
ALPHAVANTAGE_API_KEY = "HJUI1TZ5H1QTYU4D"
ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stops_state.json")
SKIP_SYMBOLS = {"SPAXX", "SPAXX**", "FCASH", "SPY"}
LOOKBACK = 30  # days for vol/beta
VOL_MULTIPLIER = 1.5
CONSECUTIVE_DAYS_THRESHOLD = 2

import requests


def fetch_daily_closes(symbol: str, days: int = 100) -> pd.Series:
    """Fetch daily closing prices from AlphaVantage."""
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
        raise ValueError(f"No data for {symbol}: {data.get('Note') or data.get('Error Message') or 'unknown'}")
    dates_sorted = sorted(ts.keys())[-days:]
    closes = {d: float(ts[d]["4. close"]) for d in dates_sorted}
    return pd.Series(closes, name=symbol).sort_index()


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def compute_metrics(prices: pd.Series, spy_prices: pd.Series):
    """Compute 30-day annualized vol, beta, trailing high, and current drop metrics."""
    # Align
    df = pd.DataFrame({"stock": prices, "spy": spy_prices}).dropna()
    if len(df) < LOOKBACK + 1:
        raise ValueError(f"Not enough data: {len(df)} days")

    recent = df.iloc[-LOOKBACK:]
    stock_ret = recent["stock"].pct_change().dropna()
    spy_ret = recent["spy"].pct_change().dropna()

    ann_vol = float(stock_ret.std() * sqrt(252))
    daily_vol = ann_vol / sqrt(252)

    # Beta = cov(stock, spy) / var(spy)
    cov = float(np.cov(stock_ret, spy_ret)[0, 1])
    spy_var = float(spy_ret.var())
    beta = cov / spy_var if spy_var > 0 else 1.0

    # Trailing highs
    trailing_high = float(recent["stock"].max())
    spy_trailing_high = float(recent["spy"].max())

    current_price = float(df["stock"].iloc[-1])
    spy_current = float(df["spy"].iloc[-1])

    raw_drop = (trailing_high - current_price) / trailing_high
    spy_drop = (spy_trailing_high - spy_current) / spy_trailing_high
    adjusted_drop = raw_drop - beta * spy_drop

    threshold = VOL_MULTIPLIER * daily_vol

    return {
        "current_price": current_price,
        "trailing_high": trailing_high,
        "ann_vol": ann_vol,
        "daily_vol": daily_vol,
        "beta": beta,
        "raw_drop": raw_drop,
        "spy_drop": spy_drop,
        "adjusted_drop": adjusted_drop,
        "threshold": threshold,
        "breached": adjusted_drop > threshold,
    }


def run_status(portfolio_path: str = None) -> str:
    port = Portfolio(portfolio_path)
    symbols = [s for s in port.symbols() if s not in SKIP_SYMBOLS]

    # Fetch SPY first
    try:
        spy_prices = fetch_daily_closes("SPY", 100)
    except Exception as e:
        return f"❌ Could not fetch SPY data: {e}"

    lines = ["📊 *Trailing Stop Status*"]
    errors = []

    for sym in symbols:
        try:
            prices = fetch_daily_closes(sym, 100)
            m = compute_metrics(prices, spy_prices)
            stop_distance_pct = m["threshold"] / (1.0)  # threshold is on daily scale as fraction
            # Convert: stop triggers when adjusted_drop > threshold
            # Distance to stop = threshold - adjusted_drop (if not breached)
            remaining = m["threshold"] - m["adjusted_drop"]
            # Express as % of current price (approximate)
            remaining_pct = remaining * 100  # it's already a fraction
            remaining_dollar = remaining * m["trailing_high"]

            status_char = "🟢" if remaining > 0 else "🔴"
            lines.append(
                f"• {status_char} *{sym}*: ${m['current_price']:.2f} | "
                f"High: ${m['trailing_high']:.2f} | "
                f"Vol: {m['ann_vol']*100:.1f}% | "
                f"Beta: {m['beta']:.2f} | "
                f"Stop distance: {remaining_pct:.1f}% (${remaining_dollar:.2f})"
            )
        except Exception as e:
            errors.append(f"• ⚠️ {sym}: {e}")

    if errors:
        lines.append("")
        lines.extend(errors)

    return "\n".join(lines)


def run_check(portfolio_path: str = None) -> str:
    port = Portfolio(portfolio_path)
    symbols = [s for s in port.symbols() if s not in SKIP_SYMBOLS]
    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    # Don't run twice on same day
    if state.get("last_check_date") == today:
        return "ℹ️ Already checked today. Use --status to view current levels."

    try:
        spy_prices = fetch_daily_closes("SPY", 100)
    except Exception as e:
        return f"❌ Could not fetch SPY data: {e}"

    alerts = []
    status_lines = []

    for sym in symbols:
        try:
            prices = fetch_daily_closes(sym, 100)
            m = compute_metrics(prices, spy_prices)

            sym_state = state.get(sym, {"trailing_high": 0, "consecutive_breach_days": 0})

            # Update trailing high (only goes up)
            if m["trailing_high"] > sym_state.get("trailing_high", 0):
                sym_state["trailing_high"] = m["trailing_high"]

            if m["breached"]:
                sym_state["consecutive_breach_days"] = sym_state.get("consecutive_breach_days", 0) + 1
            else:
                sym_state["consecutive_breach_days"] = 0

            state[sym] = sym_state

            if sym_state["consecutive_breach_days"] >= CONSECUTIVE_DAYS_THRESHOLD:
                alerts.append(
                    f"• *{sym}* breached vol stop — adjusted drop of {m['adjusted_drop']*100:.1f}% "
                    f"exceeds {VOL_MULTIPLIER}× vol ({m['threshold']*100:.1f}%) for {sym_state['consecutive_breach_days']} days\n"
                    f"  Current: ${m['current_price']:.2f} | Trailing High: ${sym_state['trailing_high']:.2f} | "
                    f"Recommendation: Sell 50%"
                )
                # Reset after alert
                sym_state["consecutive_breach_days"] = 0
                sym_state["trailing_high"] = m["current_price"]

        except Exception as e:
            status_lines.append(f"• ⚠️ {sym}: {e}")

    state["last_check_date"] = today
    save_state(state)

    if alerts:
        output = "🚨 *Trailing Stop Alert*\n" + "\n".join(alerts)
    else:
        output = "✅ All positions within trailing stop bounds."

    if status_lines:
        output += "\n" + "\n".join(status_lines)

    return output


def main():
    parser = argparse.ArgumentParser(description="Volatility-based trailing stop monitor")
    parser.add_argument("--check", action="store_true", help="Run daily check (alerts on breach)")
    parser.add_argument("--status", action="store_true", help="Show current stop levels")
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
