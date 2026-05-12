#!/usr/bin/env python3
"""
Portfolio management module.
Manages positions, quantities, cost basis. Stores data as JSON.
"""

import csv
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

DEFAULT_PORTFOLIO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.json")
# Also check ~/.openclaw/ for the JSON
ALT_PORTFOLIO_PATH = os.path.expanduser("~/.openclaw/portfolio.json")

SKIP_SYMBOLS = {"SPAXX", "SPAXX**", "FCASH"}


class Portfolio:
    def __init__(self, path: str = None):
        self.path = path or ALT_PORTFOLIO_PATH
        self.positions: Dict[str, dict] = {}
        self.updated_at: str = datetime.now().isoformat()
        if os.path.exists(self.path):
            self.load()

    # ── persistence ──────────────────────────────────────────

    def load(self, path: str = None):
        p = path or self.path
        with open(p, "r") as f:
            data = json.load(f)
        self.positions = data.get("positions", {})
        self.updated_at = data.get("updated_at", self.updated_at)
        self.cash = data.get("cash", 0.0)

    def save(self, path: str = None):
        p = path or self.path
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def to_dict(self) -> dict:
        return {
            "positions": self.positions,
            "updated_at": datetime.now().isoformat(),
        }

    # ── Fidelity CSV import ──────────────────────────────────

    def load_from_fidelity_csv(self, csv_path: str):
        """Parse a Fidelity portfolio CSV export and update positions."""
        with open(csv_path, "r") as f:
            lines = []
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith('"'):
                    # skip disclaimer / empty
                    if not any(c == "," for c in stripped[:50]):
                        continue
                lines.append(stripped)

        if not lines:
            return

        reader = csv.DictReader(lines)
        for row in reader:
            symbol = (row.get("Symbol") or "").strip().replace("**", "")
            if not symbol or symbol in SKIP_SYMBOLS:
                continue
            try:
                qty = float(row.get("Quantity", 0))
                cost_basis = float((row.get("Cost Basis Total") or "0").replace("$", "").replace(",", ""))
                last_price = float((row.get("Last Price") or "0").replace("$", "").replace(",", ""))
            except (ValueError, TypeError):
                continue

            self.positions[symbol] = {
                "symbol": symbol,
                "quantity": qty,
                "cost_basis": cost_basis,
                "avg_cost": round(cost_basis / qty, 4) if qty else 0,
                "last_price": last_price,
                "asset_type": "stock",
            }

    # ── accessors ────────────────────────────────────────────

    def list_assets(self) -> List[dict]:
        return list(self.positions.values())

    def get_asset(self, symbol: str) -> Optional[dict]:
        return self.positions.get(symbol.upper())

    def update_asset_price(self, symbol: str, price: float):
        symbol = symbol.upper()
        if symbol in self.positions:
            self.positions[symbol]["last_price"] = price

    def save_portfolio(self):
        """Alias used by prices.py"""
        self.save()

    def symbols(self) -> List[str]:
        return list(self.positions.keys())


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        p = Portfolio()
        p.load_from_fidelity_csv(sys.argv[1])
        p.save()
        print(f"Imported {len(p.positions)} positions → {p.path}")
        for sym, pos in p.positions.items():
            print(f"  {sym}: {pos['quantity']} shares, cost ${pos['cost_basis']:.2f}")
    else:
        print("Usage: python portfolio.py <fidelity_csv>")
