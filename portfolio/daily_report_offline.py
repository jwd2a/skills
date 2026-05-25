#!/usr/bin/env python3
"""Offline daily portfolio report using stored portfolio.json prices."""
import json
import os
import sys
from datetime import datetime

PORTFOLIO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.json")

with open(PORTFOLIO_PATH) as f:
    data = json.load(f)

positions = data["positions"]
cash = data.get("cash", 0)
updated_at = data.get("last_updated", "unknown")

SKIP = {"SPAXX", "SPAXX**", "FCASH"}
active = {k: v for k, v in positions.items() if k not in SKIP}

now = datetime.now()
print(f"📊 *Daily Portfolio Report* — {now.strftime('%a %b %d, %Y')}")
print(f"_Prices as of last save: {updated_at} (live quotes unavailable)_")
print()

total_val = sum(p["quantity"] * p["last_price"] for p in active.values())
total_cost = sum(p["cost_basis"] for p in active.values())
total_gl = total_val - total_cost
total_gl_pct = total_gl / total_cost * 100 if total_cost else 0

print(f"*Portfolio Value*: ${total_val:,.2f} | Cash: ${cash:,.2f} | Total: ${total_val + cash:,.2f}")
sign = "+" if total_gl >= 0 else ""
print(f"*Total P/L*: {sign}${total_gl:,.2f} ({sign}{total_gl_pct:.1f}%)")
print()

print("*Positions*")
pos_list = []
for sym, p in active.items():
    val = p["quantity"] * p["last_price"]
    gl = val - p["cost_basis"]
    gl_pct = gl / p["cost_basis"] * 100 if p["cost_basis"] else 0
    weight = val / total_val * 100 if total_val else 0
    pos_list.append((sym, p, val, gl, gl_pct, weight))

pos_list.sort(key=lambda x: x[5], reverse=True)

for sym, p, val, gl, gl_pct, weight in pos_list:
    emoji = "🟢" if gl >= 0 else "🔴"
    s = "+" if gl >= 0 else ""
    print(f"• {emoji} `{sym:5s}` {p['quantity']:>8.3f} sh @ ${p['last_price']:,.2f} | ${val:>10,.2f} ({weight:.1f}%) | P/L: {s}${gl:,.2f} ({s}{gl_pct:.1f}%)")

print()
print("*Portfolio Composition*")
for sym, p, val, gl, gl_pct, weight in pos_list:
    bar = "█" * max(1, int(weight / 5))
    print(f"• `{sym:5s}` {weight:5.1f}% {bar}")

pending = data.get("pending", {})
if pending:
    print()
    print("*Pending Trades*")
    for sym, t in pending.items():
        print(f"• {t['action'].upper()} {t['shares']} {sym} by {t['target_date']} — {t['reason']}")

source = data.get("source", "")
if source:
    print()
    print(f"_Note: {source}_")

print()
print("⚠️ _Live quotes blocked by network policy. Report uses last saved prices._")
