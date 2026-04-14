#!/usr/bin/env python3
"""Inverse-volatility rebalance analysis."""

import sys, os, time
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

PORTFOLIO = {
    'BELFA': {'value': 4029, 'weight': 0.247},
    'GOOGL': {'value': 2654, 'weight': 0.163},
    'SPY':   {'value': 2221, 'weight': 0.136},
    'WMT':   {'value': 2976, 'weight': 0.183},
    'AAPL':  {'value': 886,  'weight': 0.054},
    'GLD':   {'value': 918,  'weight': 0.056},
    'LLY':   {'value': 1059, 'weight': 0.065},
    'EQIX':  {'value': 965,  'weight': 0.059},
    'EFA':   {'value': 519,  'weight': 0.032},
}
TOTAL = sum(p['value'] for p in PORTFOLIO.values())

def fetch(symbol, days=120):
    end = datetime.now()
    start = end - timedelta(days=int(days * 1.8))
    t = yf.Ticker(symbol)
    h = t.history(start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
    if h.empty:
        raise ValueError(f"No data for {symbol}")
    closes = h['Close']
    closes.index = closes.index.strftime('%Y-%m-%d')
    return closes.rename(symbol).iloc[-days:]

symbols = list(PORTFOLIO.keys())
print(f"Fetching {len(symbols)} tickers...")

prices = {}
for sym in symbols:
    try:
        prices[sym] = fetch(sym)
        print(f"  ✓ {sym}: {len(prices[sym])} days")
    except Exception as e:
        print(f"  ✗ {sym}: {e}")

df = pd.DataFrame(prices).dropna()
print(f"Overlapping days: {len(df)}")

ret = df.pct_change().dropna()

# 30-day annualized volatility
ret_30 = ret.iloc[-30:]
vols_30 = {s: float(ret_30[s].std() * np.sqrt(252)) for s in symbols}

# Inverse-vol weights
inv_vols = {s: 1.0 / vols_30[s] for s in symbols}
inv_sum = sum(inv_vols.values())
iv_weights = {s: inv_vols[s] / inv_sum for s in symbols}

# Current weights
cur_weights = {s: PORTFOLIO[s]['value'] / TOTAL for s in symbols}

# Current prices (last close)
last_prices = {s: float(df[s].iloc[-1]) for s in symbols}

# ── Trades needed ──
trades = {}
for s in symbols:
    cur_val = cur_weights[s] * TOTAL
    tgt_val = iv_weights[s] * TOTAL
    delta_val = tgt_val - cur_val
    delta_shares = delta_val / last_prices[s]
    trades[s] = {'delta_$': delta_val, 'delta_shares': delta_shares, 'price': last_prices[s]}

# ── Backtest both allocations over 90 trading days ──
ret_90 = ret.iloc[-90:] if len(ret) >= 90 else ret
df_90 = df.iloc[-90:] if len(df) >= 90 else df
period = len(ret_90)

def backtest(weights, ret_df, df_prices):
    active = list(weights.keys())
    w = np.array([weights[s] for s in active])
    w = w / w.sum()
    port_ret = sum(w[i] * ret_df[active[i]] for i in range(len(active)))
    port_vol = float(port_ret.std() * np.sqrt(252))
    ind_vols = {s: float(ret_df[s].std() * np.sqrt(252)) for s in active}
    weighted_vol_sum = sum(w[i] * ind_vols[active[i]] for i in range(len(active)))
    div_ratio = weighted_vol_sum / port_vol if port_vol > 0 else 1.0
    downside = port_ret[port_ret < 0]
    downside_std = float(np.sqrt((downside ** 2).mean())) * np.sqrt(252) if len(downside) > 0 else 0
    ann_return = float(port_ret.mean() * 252)
    sortino = ann_return / downside_std if downside_std > 0 else float('inf')
    port_growth = sum(w[i] * ((df_prices[active[i]].iloc[-1] / df_prices[active[i]].iloc[0]) - 1) for i in range(len(active)))
    return {'vol': port_vol, 'div_ratio': div_ratio, 'sortino': sortino, 'growth': port_growth}

cur_bt = backtest(cur_weights, ret_90, df_90)
iv_bt = backtest(iv_weights, ret_90, df_90)

# ── Format output ──
lines = []
lines.append("📊 *Inverse-Volatility Rebalance Analysis*")
lines.append(f"_Total portfolio: ~${TOTAL:,.0f} | {period}-trading-day backtest ending {df_90.index[-1]}_\n")

# Volatilities
lines.append("*30-Day Annualized Volatility*")
for s in sorted(vols_30, key=lambda x: vols_30[x]):
    lines.append(f"  • `{s:5s}`: {vols_30[s]*100:.1f}%")

# Weight comparison
lines.append("\n*Current vs Inverse-Vol Weights*")
lines.append(f"  {'Ticker':<6} {'Current':>8} {'Inv-Vol':>8} {'Delta':>8}")
for s in sorted(iv_weights, key=lambda x: -iv_weights[x]):
    c = cur_weights[s] * 100
    t = iv_weights[s] * 100
    d = t - c
    lines.append(f"  `{s:5s}` {c:>7.1f}% {t:>7.1f}% {d:>+7.1f}pp")

# Trades
lines.append("\n*Trades to Rebalance*")
for s in sorted(trades, key=lambda x: -abs(trades[x]['delta_$'])):
    t = trades[s]
    if abs(t['delta_$']) < 1:
        continue
    action = "BUY" if t['delta_$'] > 0 else "SELL"
    lines.append(f"  • {action} `{s}`: {abs(t['delta_shares']):.2f} shares (${abs(t['delta_$']):,.0f}) @ ${t['price']:.2f}")

# Backtest comparison
lines.append(f"\n*{period}-Day Backtest Comparison*")
lines.append(f"  {'Metric':<24} {'Current':>10} {'Inv-Vol':>10} {'Delta':>10}")
lines.append(f"  {'─'*54}")

metrics = [
    ('Ann. Volatility', f"{cur_bt['vol']*100:.1f}%", f"{iv_bt['vol']*100:.1f}%", f"{(iv_bt['vol']-cur_bt['vol'])*100:+.1f}pp"),
    ('Diversification Ratio', f"{cur_bt['div_ratio']:.2f}x", f"{iv_bt['div_ratio']:.2f}x", f"{iv_bt['div_ratio']-cur_bt['div_ratio']:+.2f}x"),
    ('Sortino Ratio', f"{cur_bt['sortino']:.2f}", f"{iv_bt['sortino']:.2f}", f"{iv_bt['sortino']-cur_bt['sortino']:+.2f}"),
    (f'{period}-Day Return', f"{cur_bt['growth']*100:+.2f}%", f"{iv_bt['growth']*100:+.2f}%", f"{(iv_bt['growth']-cur_bt['growth'])*100:+.2f}pp"),
]
for name, cur, iv, delta in metrics:
    lines.append(f"  {name:<24} {cur:>10} {iv:>10} {delta:>10}")

# Bottom line
lines.append("\n*TL;DR*")
vol_better = iv_bt['vol'] < cur_bt['vol']
sort_better = iv_bt['sortino'] > cur_bt['sortino']
if vol_better and sort_better:
    lines.append("✅ Inverse-vol weights improve both volatility and risk-adjusted returns.")
elif vol_better:
    lines.append("⚖️ Inverse-vol weights reduce volatility but with lower risk-adjusted returns.")
elif sort_better:
    lines.append("⚖️ Inverse-vol weights improve Sortino but at higher volatility.")
else:
    lines.append("⚠️ Current weights outperform on both vol and Sortino over this period.")

# Biggest shifts
lines.append("\n_Biggest shifts: inverse-vol heavily favors low-vol names (WMT, GLD, SPY, EFA) and underweights high-vol names (LLY, EQIX, GOOGL)._")

print("\n".join(lines))
