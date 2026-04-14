#!/usr/bin/env python3
"""Compare current vs proposed portfolio with GLD, LLY, EFA, EQIX additions."""

import sys, os, time
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

def fetch_yahoo(symbol, days=100):
    """Fetch daily closes via yfinance."""
    end = datetime.now()
    start = end - timedelta(days=int(days * 1.5))
    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
    if hist.empty:
        raise ValueError(f"No data for {symbol}")
    closes = hist['Close']
    closes.index = closes.index.strftime('%Y-%m-%d')
    return closes.rename(symbol).iloc[-days:]

# Current portfolio
CURRENT = {
    'BELFA': {'shares': 19.072, 'value': 4029},
    'GOOGL': {'shares': 8.1825, 'value': 2654},
    'SPY':   {'shares': 3.2, 'value': 2221},
    'WMT':   {'shares': 23.063, 'value': 2976},
    'AAPL':  {'shares': 3.227, 'value': 886},
    'NVDA':  {'shares': 0.003, 'value': 0.57},
}

# Proposed additions
ADDITIONS = {
    'GLD':  1200,
    'LLY':  1040,
    'EQIX': 780,
    'EFA':  520,
}

DAYS = 100  # fetch extra, trim to 90 trading days

all_tickers = list(set(list(CURRENT.keys()) + list(ADDITIONS.keys())))
print(f"Fetching {len(all_tickers)} tickers: {all_tickers}")

prices = {}
for sym in all_tickers:
    try:
        prices[sym] = fetch_yahoo(sym, DAYS)
        print(f"  ✓ {sym}: {len(prices[sym])} days")
    except Exception as e:
        print(f"  ✗ {sym}: {e}")

df = pd.DataFrame(prices).dropna()
print(f"\nOverlapping days: {len(df)}")

# Trim to ~90 trading days
if len(df) > 90:
    df = df.iloc[-90:]

ret = df.pct_change().dropna()

def analyze_portfolio(name, weights_dict, ret_df, df_prices):
    """Compute metrics for a portfolio given weights."""
    active = [s for s in weights_dict if s in ret_df.columns]
    w = np.array([weights_dict[s] for s in active])
    w = w / w.sum()  # normalize
    
    # Portfolio returns
    port_ret = sum(w[i] * ret_df[active[i]] for i in range(len(active)))
    
    # Annualized vol
    port_vol = float(port_ret.std() * np.sqrt(252))
    
    # Individual vols
    ind_vols = {s: float(ret_df[s].std() * np.sqrt(252)) for s in active}
    
    # Weighted sum of individual vols
    weighted_vol_sum = sum(w[i] * ind_vols[active[i]] for i in range(len(active)))
    
    # Diversification ratio
    div_ratio = weighted_vol_sum / port_vol if port_vol > 0 else 1.0
    
    # Sortino (0% risk-free)
    excess = port_ret
    downside = excess[excess < 0]
    downside_std = float(np.sqrt((downside ** 2).mean())) * np.sqrt(252)
    ann_return = float(port_ret.mean() * 252)
    sortino = ann_return / downside_std if downside_std > 0 else float('inf')
    
    # Period return
    port_growth = sum(w[i] * ((df_prices[active[i]].iloc[-1] / df_prices[active[i]].iloc[0]) - 1) for i in range(len(active)))
    
    return {
        'name': name,
        'vol': port_vol,
        'div_ratio': div_ratio,
        'sortino': sortino,
        'growth': port_growth,
        'ind_vols': ind_vols,
        'weights': {active[i]: w[i] for i in range(len(active))},
        'active': active,
    }

# Current weights (by dollar value)
current_total = sum(v['value'] for v in CURRENT.values())
current_weights = {s: v['value'] / current_total for s, v in CURRENT.items()}

# Proposed weights: current + additions
proposed_values = {s: v['value'] for s, v in CURRENT.items()}
for s, val in ADDITIONS.items():
    proposed_values[s] = proposed_values.get(s, 0) + val
proposed_total = sum(proposed_values.values())
proposed_weights = {s: v / proposed_total for s, v in proposed_values.items()}

# SPY benchmark
spy_ret = ret['SPY']
spy_vol = float(spy_ret.std() * np.sqrt(252))
spy_excess = spy_ret
spy_down = spy_excess[spy_excess < 0]
spy_down_std = float(np.sqrt((spy_down ** 2).mean())) * np.sqrt(252)
spy_ann_ret = float(spy_ret.mean() * 252)
spy_sortino = spy_ann_ret / spy_down_std if spy_down_std > 0 else float('inf')
spy_growth = float((df['SPY'].iloc[-1] / df['SPY'].iloc[0]) - 1)

current = analyze_portfolio("Current Portfolio", current_weights, ret, df)
proposed = analyze_portfolio("Proposed Portfolio", proposed_weights, ret, df)

# Correlation matrix for proposed
prop_active = proposed['active']
corr = ret[prop_active].corr()

# Format output
lines = []
lines.append("📊 *Portfolio Backtest: Current vs Proposed*")
lines.append(f"_{len(df)}-trading-day lookback ending {df.index[-1]}_\n")

lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
lines.append("*CURRENT PORTFOLIO*")
lines.append(f"Total value: ~${current_total:,.0f}")
lines.append("Weights:")
for s in sorted(current['weights'], key=lambda x: -current['weights'][x]):
    lines.append(f"  • {s}: {current['weights'][s]*100:.1f}%")
lines.append(f"\n• Annualized Volatility: {current['vol']*100:.1f}%")
lines.append(f"• Diversification Ratio: {current['div_ratio']:.2f}x (higher = better)")
lines.append(f"• Sortino Ratio: {current['sortino']:.2f}")
lines.append(f"• {len(df)}-day Return: {'+' if current['growth']>=0 else ''}{current['growth']*100:.2f}%")

lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
lines.append("*PROPOSED PORTFOLIO (with GLD, LLY, EQIX, EFA)*")
lines.append(f"Total value: ~${proposed_total:,.0f}")
lines.append("Weights:")
for s in sorted(proposed['weights'], key=lambda x: -proposed['weights'][x]):
    lines.append(f"  • {s}: {proposed['weights'][s]*100:.1f}%")
lines.append(f"\n• Annualized Volatility: {proposed['vol']*100:.1f}%")
lines.append(f"• Diversification Ratio: {proposed['div_ratio']:.2f}x (higher = better)")
lines.append(f"• Sortino Ratio: {proposed['sortino']:.2f}")
lines.append(f"• {len(df)}-day Return: {'+' if proposed['growth']>=0 else ''}{proposed['growth']*100:.2f}%")

lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
lines.append("*SPY BENCHMARK*")
lines.append(f"• Annualized Volatility: {spy_vol*100:.1f}%")
lines.append(f"• Sortino Ratio: {spy_sortino:.2f}")
lines.append(f"• {len(df)}-day Return: {'+' if spy_growth>=0 else ''}{spy_growth*100:.2f}%")

# Changes
lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
lines.append("*IMPACT OF PROPOSED CHANGES*")
vol_change = (proposed['vol'] - current['vol']) * 100
div_change = proposed['div_ratio'] - current['div_ratio']
sort_change = proposed['sortino'] - current['sortino']
growth_change = (proposed['growth'] - current['growth']) * 100
lines.append(f"• Volatility: {'+' if vol_change>=0 else ''}{vol_change:.1f}pp")
lines.append(f"• Diversification: {'+' if div_change>=0 else ''}{div_change:.2f}x")
lines.append(f"• Sortino: {'+' if sort_change>=0 else ''}{sort_change:.2f}")
lines.append(f"• Return: {'+' if growth_change>=0 else ''}{growth_change:.2f}pp")

# Alpha vs SPY
lines.append(f"\n• Alpha vs SPY (current): {'+' if (current['growth']-spy_growth)>=0 else ''}{(current['growth']-spy_growth)*100:.2f}pp")
lines.append(f"• Alpha vs SPY (proposed): {'+' if (proposed['growth']-spy_growth)>=0 else ''}{(proposed['growth']-spy_growth)*100:.2f}pp")

# Correlation matrix
lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
lines.append("*CORRELATION MATRIX (Proposed Portfolio)*")
# Format as readable text, not a markdown table
for s1 in prop_active:
    pairs = []
    for s2 in prop_active:
        if s2 > s1:  # upper triangle only
            pairs.append(f"{s1}/{s2}: {corr.loc[s1,s2]:.2f}")
    if pairs:
        lines.append("• " + " | ".join(pairs))

# Key low correlations
lines.append("\n_Key low-correlation pairs (< 0.3):_")
found = False
for i, s1 in enumerate(prop_active):
    for s2 in prop_active[i+1:]:
        c = corr.loc[s1, s2]
        if c < 0.3:
            lines.append(f"  • {s1}/{s2}: {c:.2f}")
            found = True
if not found:
    lines.append("  (none below 0.3)")

print("\n".join(lines))
