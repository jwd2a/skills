#!/usr/bin/env python3
"""
Rotation Tracker — Logs all portfolio rotations and tracks performance.

Usage:
  python rotation_tracker.py --log GOOGL exit 311.49 "Trailing stop breach"
  python rotation_tracker.py --log POWL enter 85.20 "Top momentum screener pick"
  python rotation_tracker.py --status
  python rotation_tracker.py --stats
  python rotation_tracker.py --json
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROTATION_FILE = os.path.join(SCRIPT_DIR, "rotations.json")


def load_rotations() -> List[Dict]:
    if os.path.exists(ROTATION_FILE):
        with open(ROTATION_FILE) as f:
            return json.load(f)
    return []


def save_rotations(rotations: List[Dict]):
    with open(ROTATION_FILE, "w") as f:
        json.dump(rotations, f, indent=2)


def log_rotation(symbol: str, action: str, price: float, reason: str = ""):
    """Log an entry or exit."""
    rotations = load_rotations()
    rotations.append({
        "symbol": symbol.upper(),
        "action": action,  # "enter" or "exit"
        "price": price,
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
    })
    save_rotations(rotations)
    print(f"Logged: {action.upper()} {symbol.upper()} @ ${price:.2f} — {reason}")


def calculate_stats(rotations: List[Dict]) -> Dict:
    """Calculate rotation stats — pair entries with exits."""
    # Group by symbol, match entries to exits
    trades = []
    open_positions = {}
    
    for r in rotations:
        sym = r["symbol"]
        if r["action"] == "enter":
            if sym not in open_positions:
                open_positions[sym] = []
            open_positions[sym].append(r)
        elif r["action"] == "exit":
            if sym in open_positions and open_positions[sym]:
                entry = open_positions[sym].pop(0)
                pnl_pct = ((r["price"] - entry["price"]) / entry["price"]) * 100
                entry_dt = datetime.fromisoformat(entry["timestamp"])
                exit_dt = datetime.fromisoformat(r["timestamp"])
                days_held = (exit_dt - entry_dt).days
                trades.append({
                    "symbol": sym,
                    "entry_price": entry["price"],
                    "exit_price": r["price"],
                    "pnl_pct": round(pnl_pct, 2),
                    "days_held": days_held,
                    "entry_date": entry["timestamp"][:10],
                    "exit_date": r["timestamp"][:10],
                    "exit_reason": r.get("reason", ""),
                })
    
    if not trades:
        return {"total_trades": 0, "open_positions": list(open_positions.keys())}
    
    winners = [t for t in trades if t["pnl_pct"] > 0]
    losers = [t for t in trades if t["pnl_pct"] <= 0]
    
    avg_win = sum(t["pnl_pct"] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t["pnl_pct"] for t in losers) / len(losers) if losers else 0
    avg_hold = sum(t["days_held"] for t in trades) / len(trades)
    
    return {
        "total_trades": len(trades),
        "winners": len(winners),
        "losers": len(losers),
        "hit_rate": round(len(winners) / len(trades) * 100, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "avg_days_held": round(avg_hold, 1),
        "best_trade": max(trades, key=lambda t: t["pnl_pct"]),
        "worst_trade": min(trades, key=lambda t: t["pnl_pct"]),
        "open_positions": [sym for sym, entries in open_positions.items() if entries],
        "recent_trades": trades[-5:],
    }


def format_stats_slack(stats: Dict) -> str:
    if stats["total_trades"] == 0:
        open_str = ", ".join(stats.get("open_positions", [])) or "none"
        return f":arrows_counterclockwise: _Rotation Tracker_\n\nNo completed trades yet.\nOpen positions: {open_str}"
    
    lines = [
        f":arrows_counterclockwise: _Rotation Stats_\n",
        f"• Completed trades: {stats['total_trades']}",
        f"• Hit rate: {stats['hit_rate']}% ({stats['winners']}W / {stats['losers']}L)",
        f"• Avg win: +{stats['avg_win_pct']}% | Avg loss: {stats['avg_loss_pct']}%",
        f"• Avg hold time: {stats['avg_days_held']} days",
        f"• Best: {stats['best_trade']['symbol']} +{stats['best_trade']['pnl_pct']}%",
        f"• Worst: {stats['worst_trade']['symbol']} {stats['worst_trade']['pnl_pct']}%",
    ]
    
    if stats["open_positions"]:
        lines.append(f"• Open: {', '.join(stats['open_positions'])}")
    
    if stats["recent_trades"]:
        lines.append("\n_Recent:_")
        for t in stats["recent_trades"]:
            emoji = ":white_check_mark:" if t["pnl_pct"] > 0 else ":x:"
            lines.append(f"  {emoji} {t['symbol']}: {t['pnl_pct']:+.1f}% ({t['days_held']}d) — {t['exit_reason']}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Rotation Tracker")
    parser.add_argument("--log", nargs=4, metavar=("SYMBOL", "ACTION", "PRICE", "REASON"),
                       help="Log a rotation (symbol enter/exit price reason)")
    parser.add_argument("--status", action="store_true", help="Show current status")
    parser.add_argument("--stats", action="store_true", help="Show trade statistics")
    parser.add_argument("--json", action="store_true", help="JSON output")
    
    args = parser.parse_args()
    
    if args.log:
        symbol, action, price, reason = args.log
        if action not in ("enter", "exit"):
            print("Action must be 'enter' or 'exit'", file=sys.stderr)
            sys.exit(1)
        log_rotation(symbol, action, float(price), reason)
    elif args.stats or args.status:
        rotations = load_rotations()
        stats = calculate_stats(rotations)
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print(format_stats_slack(stats))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
