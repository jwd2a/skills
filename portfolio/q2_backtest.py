#!/usr/bin/env python3
"""
Q2 2026 Portfolio Backtest: 3 options vs current portfolio vs SPY.
Backtests over 90 trading days (~1 quarter) and 252 trading days (~1 year).
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ── Current portfolio (post-trim: drop EFA + CME) ──────────
# Current positions with approximate current values
CURRENT_POSITIONS = {
    'SPY':  {'shares': 3.2,    'cost': 1649.47},
    'WMT':  {'shares': 23.063, 'cost': 2591.55},
    'AAPL': {'shares': 3.2,    'cost': 771.79},
    'GLD':  {'shares': 4,      'cost': 1866.31},
    'EQIX': {'shares': 1,      'cost': 963.32},
    'CRS':  {'shares': 2,      'cost': 809.22},
    'POWL': {'shares': 2,      'cost': 1016.52},
}

# Cash after selling EFA (~$504) + CME (~$642) + existing cash ($3,562)
DEPLOYABLE_CASH = 3562 + 504 + 642  # ~$4,708

# If also selling WMT: add ~$2,935
WMT_VALUE = 2935
DEPLOYABLE_NO_WMT = DEPLOYABLE_CASH + WMT_VALUE  # ~$7,643

# Total portfolio value ~$15,105
TOTAL_VALUE = sum([
    2097,  # SPY
    2877,  # WMT 
    818,   # AAPL
    1751,  # GLD
    996,   # EQIX
    809,   # CRS
    1108,  # POWL
]) + DEPLOYABLE_CASH

print(f"Total portfolio value: ~${TOTAL_VALUE:,.0f}")
print(f"Cash after EFA+CME exit: ~${DEPLOYABLE_CASH:,.0f}")
print(f"Cash if also exit WMT: ~${DEPLOYABLE_NO_WMT:,.0f}")

# ── Three portfolio options (target weights by dollar value) ─

# Option A: Keep WMT, add TRGP + beef up EQIX
# Rationale: WMT is our defensive anchor, add TRGP for energy/momentum, EQIX for data center secular
OPTION_A = {
    'name': 'A: Keep WMT + Add TRGP',
    'desc': 'Defensive anchor (WMT) + momentum rotation (TRGP). 6 positions.',
    'weights': {
        'SPY':  2097,
        'WMT':  2877,
        'GLD':  1751,
        'EQIX': 996 + 1500,   # add $1,500 to EQIX
        'POWL': 1108,
        'TRGP': 2000,         # new: energy infrastructure momentum
        # Sell AAPL ($818) + CRS ($809) to fund TRGP/EQIX adds
        # Remaining cash: 4708 + 818 + 809 - 1500 - 2000 = $2,835 reserve
    },
}

# Option B: Drop WMT, full momentum — TRGP + PLXS
# Rationale: Pure momentum rotation strategy. No defensive anchors. Ride the wave.
OPTION_B = {
    'name': 'B: Drop WMT, Full Momentum',
    'desc': 'Pure momentum rotation. Drop WMT+AAPL, add TRGP+PLXS. 6 positions.',
    'weights': {
        'SPY':  2097,
        'GLD':  1751,
        'EQIX': 996 + 1000,   # add $1,000
        'POWL': 1108 + 500,   # add $500
        'TRGP': 2500,         # new: best risk-adj momentum
        'PLXS': 2000,         # new: solid momentum, moderate vol
        # Sell WMT ($2,877) + AAPL ($818) + CRS ($809)
        # Total freed: 4708 + 2877 + 818 + 809 = $9,212
        # Deployed: 1000 + 500 + 2500 + 2000 = $6,000 new
        # Reserve: ~$3,212
    },
}

# Option C: Drop WMT, inverse-vol balanced — beef up low-vol names + TRGP
# Rationale: Vol-weight toward stability but keep TRGP for momentum
OPTION_C = {
    'name': 'C: Drop WMT, Vol-Balanced + TRGP',
    'desc': 'Inverse-vol weighted. Overweight low-vol (SPY, EQIX), add TRGP. 6 positions.',
    'weights': {
        'SPY':  2097 + 1500,  # add $1,500 — lowest vol, inverse-vol says overweight
        'GLD':  1751 + 800,   # add $800 — uncorrelated hedge
        'EQIX': 996 + 2000,   # add $2,000 — low vol, secular trend
        'POWL': 1108,         # keep as-is — high vol, don't add
        'CRS':  809,          # keep as-is — high vol, don't add  
        'TRGP': 2000,         # new: low vol momentum
        # Sell WMT ($2,877) + AAPL ($818)
        # Total freed: 4708 + 2877 + 818 = $8,403
        # Deployed: 1500 + 800 + 2000 + 2000 = $6,300
        # Reserve: ~$2,103
    },
}

OPTIONS = [OPTION_A, OPTION_B, OPTION_C]

# Also need the "current" (post EFA/CME trim, pre-rebalance) as baseline
CURRENT_POST_TRIM = {
    'name': 'Current (post EFA/CME trim)',
    'desc': 'Existing positions minus EFA/CME, cash on sideline.',
    'weights': {
        'SPY':  2097,
        'WMT':  2877,
        'AAPL': 818,
        'GLD':  1751,
        'EQIX': 996,
        'CRS':  809,
        'POWL': 1108,
    },
}

# ── Fetch prices ───────────────────────────────────────────
ALL_TICKERS = list(set(
    list(CURRENT_POST_TRIM['weights'].keys()) +
    [t for o in OPTIONS for t in o['weights'].keys()] +
    ['SPY']  # benchmark
))

print(f"\nFetching {len(ALL_TICKERS)} tickers: {sorted(ALL_TICKERS)}")

end = datetime.now()
start = end - timedelta(days=400)  # ~1 year + buffer

prices = {}
for sym in ALL_TICKERS:
    try:
        ticker = yf.Ticker(sym)
        hist = ticker.history(start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
        if hist.empty:
            print(f"  ✗ {sym}: no data")
            continue
        closes = hist['Close']
        closes.index = pd.to_datetime(closes.index).strftime('%Y-%m-%d')
        prices[sym] = closes
        print(f"  ✓ {sym}: {len(closes)} days")
    except Exception as e:
        print(f"  ✗ {sym}: {e}")

df_all = pd.DataFrame(prices).dropna()
print(f"\nOverlapping trading days: {len(df_all)}")

# ── Backtest function ──────────────────────────────────────
def backtest(name, weights_dict, df, benchmark='SPY'):
    """Backtest a portfolio over the given price dataframe."""
    active = [s for s in weights_dict if s in df.columns]
    if not active:
        return None
    
    total = sum(weights_dict[s] for s in active)
    w = np.array([weights_dict[s] / total for s in active])
    
    ret = df[active].pct_change().dropna()
    port_ret = (ret * w).sum(axis=1)
    
    # Cumulative return
    cum = (1 + port_ret).cumprod()
    total_return = float(cum.iloc[-1] - 1)
    
    # Annualized return
    days = len(ret)
    ann_return = float((1 + total_return) ** (252 / days) - 1)
    
    # Annualized vol
    ann_vol = float(port_ret.std() * np.sqrt(252))
    
    # Max drawdown
    rolling_max = cum.cummax()
    drawdown = (cum - rolling_max) / rolling_max
    max_dd = float(drawdown.min())
    
    # Sharpe (0% risk-free for simplicity)
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0
    
    # Sortino
    downside = port_ret[port_ret < 0]
    downside_std = float(np.sqrt((downside ** 2).mean())) * np.sqrt(252) if len(downside) > 0 else 0.001
    sortino = ann_return / downside_std
    
    # Beta vs SPY
    if benchmark in df.columns:
        spy_ret = df[benchmark].pct_change().dropna()
        aligned = pd.DataFrame({'port': port_ret, 'spy': spy_ret}).dropna()
        if len(aligned) > 10:
            cov = np.cov(aligned['port'], aligned['spy'])
            beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] > 0 else 1.0
            spy_total = float((1 + aligned['spy']).cumprod().iloc[-1] - 1)
            alpha = total_return - spy_total
        else:
            beta, alpha = 1.0, 0.0
    else:
        beta, alpha = 1.0, 0.0
    
    return {
        'name': name,
        'total_return': total_return,
        'ann_return': ann_return,
        'ann_vol': ann_vol,
        'max_drawdown': max_dd,
        'sharpe': sharpe,
        'sortino': sortino,
        'beta': beta,
        'alpha': alpha,
        'weights': {active[i]: float(w[i]) for i in range(len(active))},
        'positions': len(active),
    }

# ── Run backtests ──────────────────────────────────────────
PERIODS = {
    '90-Day (Q1 2026)': 90,
    '252-Day (1 Year)': 252,
}

all_portfolios = [CURRENT_POST_TRIM] + OPTIONS

results = {}
for period_name, days in PERIODS.items():
    df_period = df_all.iloc[-min(days, len(df_all)):]
    print(f"\n{'='*60}")
    print(f"BACKTEST: {period_name} ({len(df_period)} trading days)")
    print(f"Period: {df_period.index[0]} → {df_period.index[-1]}")
    print(f"{'='*60}")
    
    period_results = []
    for port in all_portfolios:
        r = backtest(port['name'], port['weights'], df_period)
        if r:
            r['desc'] = port.get('desc', '')
            period_results.append(r)
    
    # SPY benchmark
    spy_r = backtest('SPY Benchmark', {'SPY': 1.0}, df_period)
    if spy_r:
        spy_r['desc'] = '100% SPY'
        period_results.append(spy_r)
    
    results[period_name] = period_results

# ── Format output ──────────────────────────────────────────
print("\n" + "🔮" * 30)
print("\n📊 *Q2 2026 Portfolio Options — Backtest Results*\n")

for period_name, period_results in results.items():
    print(f"\n{'━'*50}")
    print(f"*{period_name}*")
    print(f"_{period_results[0].get('name', 'N/A')} period_")
    print(f"{'━'*50}")
    
    for r in period_results:
        emoji = '📌' if 'Current' in r['name'] else ('🎯' if 'SPY' not in r['name'] else '📈')
        print(f"\n{emoji} *{r['name']}*")
        if r.get('desc'):
            print(f"_{r['desc']}_")
        
        # Weights
        if r['positions'] > 1 and 'Benchmark' not in r['name']:
            sorted_w = sorted(r['weights'].items(), key=lambda x: -x[1])
            weight_str = " · ".join([f"{s} {v*100:.0f}%" for s, v in sorted_w])
            print(f"  Weights: {weight_str}")
        
        ret_sign = '+' if r['total_return'] >= 0 else ''
        ann_sign = '+' if r['ann_return'] >= 0 else ''
        alpha_sign = '+' if r['alpha'] >= 0 else ''
        
        print(f"  Return: {ret_sign}{r['total_return']*100:.2f}% (ann: {ann_sign}{r['ann_return']*100:.1f}%)")
        print(f"  Vol: {r['ann_vol']*100:.1f}% | Max DD: {r['max_drawdown']*100:.1f}%")
        print(f"  Sharpe: {r['sharpe']:.2f} | Sortino: {r['sortino']:.2f}")
        print(f"  Beta: {r['beta']:.2f} | Alpha vs SPY: {alpha_sign}{r['alpha']*100:.2f}pp")

# ── Summary comparison table ───────────────────────────────
print(f"\n{'━'*50}")
print("*HEAD-TO-HEAD COMPARISON*")
print(f"{'━'*50}")

for period_name, period_results in results.items():
    print(f"\n*{period_name}:*")
    
    # Sort by Sortino (risk-adjusted return)
    ranked = sorted([r for r in period_results if 'Benchmark' not in r['name']], 
                     key=lambda x: -x['sortino'])
    
    for i, r in enumerate(ranked):
        medal = ['🥇', '🥈', '🥉', '4️⃣'][i] if i < 4 else f'{i+1}.'
        ret_sign = '+' if r['total_return'] >= 0 else ''
        alpha_sign = '+' if r['alpha'] >= 0 else ''
        print(f"  {medal} {r['name']}: {ret_sign}{r['total_return']*100:.2f}% return, "
              f"{r['sortino']:.2f} Sortino, {r['max_drawdown']*100:.1f}% max DD, "
              f"{alpha_sign}{r['alpha']*100:.2f}pp alpha")
    
    # SPY for reference
    spy = [r for r in period_results if 'Benchmark' in r['name']]
    if spy:
        s = spy[0]
        ret_sign = '+' if s['total_return'] >= 0 else ''
        print(f"  📈 SPY: {ret_sign}{s['total_return']*100:.2f}% return, {s['sortino']:.2f} Sortino, {s['max_drawdown']*100:.1f}% max DD")

# ── WMT analysis ──────────────────────────────────────────
print(f"\n{'━'*50}")
print("*WMT DEEP DIVE — Should We Keep It?*")
print(f"{'━'*50}")

if 'WMT' in df_all.columns:
    wmt_90 = df_all['WMT'].iloc[-90:]
    wmt_252 = df_all['WMT'].iloc[-252:] if len(df_all) >= 252 else df_all['WMT']
    spy_90 = df_all['SPY'].iloc[-90:]
    spy_252 = df_all['SPY'].iloc[-252:] if len(df_all) >= 252 else df_all['SPY']
    
    wmt_90_ret = float(wmt_90.iloc[-1] / wmt_90.iloc[0] - 1)
    wmt_252_ret = float(wmt_252.iloc[-1] / wmt_252.iloc[0] - 1) if len(wmt_252) >= 252 else None
    spy_90_ret = float(spy_90.iloc[-1] / spy_90.iloc[0] - 1)
    spy_252_ret = float(spy_252.iloc[-1] / spy_252.iloc[0] - 1) if len(spy_252) >= 252 else None
    
    wmt_vol = float(wmt_90.pct_change().dropna().std() * np.sqrt(252))
    
    # Momentum (10-day)
    wmt_10d = df_all['WMT'].iloc[-10:]
    wmt_10d_ret = float(wmt_10d.iloc[-1] / wmt_10d.iloc[0] - 1)
    
    # Correlation with other holdings
    ret_90 = df_all.iloc[-90:].pct_change().dropna()
    corrs = {}
    for sym in ['SPY', 'GLD', 'EQIX', 'POWL', 'CRS', 'TRGP', 'PLXS']:
        if sym in ret_90.columns:
            corrs[sym] = float(ret_90['WMT'].corr(ret_90[sym]))
    
    print(f"\n• 10-day momentum: {'+' if wmt_10d_ret >= 0 else ''}{wmt_10d_ret*100:.1f}%")
    print(f"• 90-day return: {'+' if wmt_90_ret >= 0 else ''}{wmt_90_ret*100:.1f}% (SPY: {'+' if spy_90_ret >= 0 else ''}{spy_90_ret*100:.1f}%)")
    if wmt_252_ret is not None:
        print(f"• 1-year return: {'+' if wmt_252_ret >= 0 else ''}{wmt_252_ret*100:.1f}% (SPY: {'+' if spy_252_ret >= 0 else ''}{spy_252_ret*100:.1f}%)")
    print(f"• Annualized vol: {wmt_vol*100:.1f}%")
    print(f"• Correlations:")
    for sym, c in sorted(corrs.items(), key=lambda x: x[1]):
        print(f"    {sym}: {c:.2f}")
    
    print(f"\n• Our cost basis: $112.37/sh, current ~$127. P/L: +13.2%")
    print(f"• Position size: 24.9% of invested — our largest holding")
    
    # Verdict
    if wmt_10d_ret < 0 and wmt_90_ret < spy_90_ret:
        print(f"\n🔴 *Verdict: WMT is losing momentum and underperforming SPY.*")
        print(f"   At 25% of invested, it's a big drag if it stalls. The momentum strategy says rotate out.")
    elif wmt_10d_ret > 0 and wmt_vol < 0.20:
        print(f"\n🟡 *Verdict: WMT still has low vol and some momentum.*")
        print(f"   Could keep as defensive anchor but it's oversized at 25%.")
    else:
        print(f"\n🟡 *Verdict: WMT is mixed.*")
        print(f"   Decent return but momentum may be fading. Consider trimming to 10-15% rather than full exit.")

print("\n✅ Backtest complete.")
