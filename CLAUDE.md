# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is a personal Claude Code skills repository — a collection of reusable skill packages that extend Claude Code's capabilities for specific recurring tasks. Each subdirectory is a self-contained skill with its own `SKILL.md` defining when and how to use it.

## Skills Overview

### `portfolio/` — Stock Portfolio Analytics

Analyzes Justin's personal Fidelity brokerage portfolio (SPY, WMT, GLD, EQIX, CRS, POWL, TRGP) against the S&P 500 benchmark using a momentum rotation strategy.

**Running reports:**
```bash
cd portfolio/
python report.py --cadence daily       # Live quotes, ~10-15 lines
python report.py --cadence weekly      # Weekly perf + trailing stops
python report.py --cadence monthly     # Full analytics, 30-day lookback
python report.py --cadence quarterly   # 90-day + momentum trends + weight drift
python report.py --cadence yearly      # 252-day + annual ranking + diversification trend
```

**Running analysis directly:**
```bash
python analyze.py                    # 90-day default
python analyze.py --days 180
python analyze.py --json portfolio.json --days 60
```

**Trailing stop monitoring:**
```bash
python trailing_stops.py --status    # Show current levels for all positions
python trailing_stops.py --check     # Daily monitoring (fires alerts on breach)
```

**Momentum screener:**
```bash
python3 momentum_screener.py --universe bullpen --lookback 10 --compare
python3 momentum_screener.py --universe sp500 --top 20
```

**Rotation tracker:**
```bash
python3 rotation_tracker.py --log GOOGL exit 311.49 "Trailing stop breach"
python3 rotation_tracker.py --stats
```

**Dependencies:** `pip install numpy pandas requests` (no virtual environment or lockfile present)

**Architecture:**
- `portfolio.py` — `Portfolio` class; loads/saves `portfolio.json`; imports from Fidelity CSV; excludes money-market symbols (SPAXX, FCASH)
- `prices.py` — Price fetching with file-level caching (`price_cache.json`, gitignored); primary sources are Finnhub (live) and AlphaVantage (historical); Yahoo Finance as fallback; crypto via CoinGecko; **API keys are hardcoded** in this file; AlphaVantage has a 3s delay between calls for the free-tier 5 calls/min limit
- `analyze.py` — Computes annualized volatility, correlation matrix, Sortino ratio, diversification score, growth vs SPY; outputs Slack-formatted text
- `report.py` — Orchestrates the above modules; daily reports use Finnhub only, weekly+ use AlphaVantage historical data
- `trailing_stops.py` — Stateful stop monitor; persists trailing highs in `stops_state.json`; alert threshold is 1.5× daily vol for 2 consecutive trading days; "adjusted drop" = raw drop from high − (beta × SPY drop from its high)
- `trades.json` — Append-only trade log maintained by `rotation_tracker.py`

### `drawer-content/` — Drawer App Content Management

Creates and manages drawers and places in the Drawer app's production Supabase database under the `drawer` brand account (User ID: `24b55cde-afcf-4e8b-8e8b-7b75d49c7801`).

**Critical rule:** Never reference a `ilovedrawer.com/d/{username}/{slug}` URL without first verifying it exists in the DB. Always: create → verify → then post.

**Scripts (run from the skill root):**
```bash
bash scripts/drawer-api.sh list-drawers
bash scripts/drawer-api.sh create-drawer "Name" "emoji" "Description"
bash scripts/drawer-api.sh verify-url <slug>
bash scripts/drawer-api.sh add-place <drawer-id> <google_place_id> "Name" "Address" lat lng "notes" "what_to_get" "" "types"
bash scripts/google-places-lookup.sh "Place Name, City ST"
```

**Architecture:**
- `scripts/drawer-api.sh` — Wraps Supabase REST API; reads `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from a `.env` file three directories up from the script
- `scripts/google-places-lookup.sh` — Google Places text search; requires `GOOGLE_PLACES_API_KEY` (the app's iOS-restricted key won't work from CLI)
- `references/schema.md` — Canonical Supabase table schemas for `drawers` and `places`

**Key constraints:**
- Slugs are auto-generated from the drawer name (lowercase, hyphens) — predict before creating
- `google_place_id` + `drawer_id` must be unique — can't add the same place twice to a drawer
- Places need `status: "recommended"` to appear in the feed
- All content created as `is_public: true` by default
