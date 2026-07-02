#!/usr/bin/env python3
"""
Daily portfolio report — runs from stored portfolio.json when live APIs are unavailable.
Falls back gracefully when Finnhub/Yahoo Finance are blocked by network policy.
"""

import json
import os
import sys
from datetime import datetime

PORTFOLIO_JSON = os.path.join(os.path.dirname(__file__), "portfolio.json")
SKIP = {"SPAXX", "SPAXX**", "FCASH"}


def run():
    with open(PORTFOLIO_JSON) as f:
        data = json.load(f)

    positions = data["positions"]
    cash = data.get("cash", 0)
    last_updated = data.get("last_updated", "unknown")
    source_note = data.get("source", "")
    pending = data.get("pending", {})

    holdings = [(sym, pos) for sym, pos in positions.items() if sym not in SKIP]

    total_value = 0.0
    total_cost = 0.0
    rows = []

    for sym, pos in holdings:
        qty = pos["quantity"]
        price = pos["last_price"]
        cost = pos["cost_basis"]
        val = qty * price
        gl = val - cost
        gl_pct = gl / cost * 100 if cost else 0.0
        total_value += val
        total_cost += cost
        rows.append((sym, qty, price, cost, val, gl, gl_pct))

    total_gl = total_value - total_cost
    total_gl_pct = total_gl / total_cost * 100 if total_cost else 0.0
    portfolio_total = total_value + cash

    now_str = datetime.now().strftime("%a %b %d, %Y")
    data_date = last_updated[:10]

    lines = []
    lines.append(f"📊 *Daily Portfolio Report* — {now_str}")
    lines.append("")
    lines.append(f"⚠️  _Live market data unavailable (API network policy). Prices as of {data_date}._")
    lines.append("")
    lines.append(f"*Portfolio Value*: ${portfolio_total:,.2f}  (${total_value:,.2f} invested + ${cash:,.2f} cash)")

    sign = "+" if total_gl >= 0 else ""
    lines.append(f"*Total P/L*: {sign}${total_gl:,.2f} ({sign}{total_gl_pct:.1f}%)")
    lines.append("")

    lines.append("*Holdings*")
    header = f"{'Sym':<6} {'Qty':>8} {'Price':>10} {'Value':>12} {'P/L $':>10} {'P/L %':>8}"
    lines.append(header)
    lines.append("-" * 58)

    for sym, qty, price, cost, val, gl, gl_pct in sorted(rows, key=lambda x: -x[4]):
        emoji = "🟢" if gl >= 0 else "🔴"
        g1 = "+" if gl >= 0 else ""
        g2 = "+" if gl_pct >= 0 else ""
        lines.append(f"{emoji} {sym:<4} {qty:>8.3f} {price:>10.2f} {val:>12,.2f} {g1}{gl:>9,.2f} {g2}{gl_pct:>7.1f}%")

    lines.append("-" * 58)
    s1 = "+" if total_gl >= 0 else ""
    s2 = "+" if total_gl_pct >= 0 else ""
    lines.append(f"  {'TOTAL':<4} {'':>8} {'':>10} {total_value:>12,.2f} {s1}{total_gl:>9,.2f} {s2}{total_gl_pct:>7.1f}%")
    lines.append("")

    lines.append("*Portfolio Weights*")
    for sym, qty, price, cost, val, gl, gl_pct in sorted(rows, key=lambda x: -x[4]):
        weight = val / total_value * 100 if total_value else 0
        lines.append(f"• `{sym}`: {weight:.1f}%  (${val:,.2f})")
    lines.append("")

    if pending:
        lines.append("*Pending Trades*")
        for sym, trade in pending.items():
            lines.append(
                f"• `{sym}`: {trade['action'].upper()} {trade['shares']} shares"
                f" by {trade['target_date']} — {trade['reason']}"
            )
        lines.append("")

    if source_note:
        lines.append(f"*Last Rebalance Note*: {source_note}")
        lines.append("")

    lines.append(f"_Data source: portfolio.json, last updated {last_updated}_")
    return "\n".join(lines)


if __name__ == "__main__":
    print(run())
