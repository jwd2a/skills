# Portfolio Analytics Skill

Analyzes Justin's stock portfolio with benchmarking against S&P 500 (SPY).

## Files
- `portfolio.py` — Portfolio class for managing positions (also symlinked to `~/.openclaw/`)
- `analyze.py` — Analytics engine (volatility, correlation, Sortino, diversification, growth)
- `prices.py` — Copy of the price fetching module from `~/.openclaw/`

## Usage

### Update portfolio from Fidelity CSV
```python
from portfolio import Portfolio
p = Portfolio()
p.load_from_fidelity_csv("/path/to/export.csv")
p.save()
```

### Run analysis
```bash
python analyze.py                    # 90-day default
python analyze.py --days 180         # custom period
python analyze.py --json portfolio.json --days 60
```

### Output
Slack-formatted text with:
- Per-position and portfolio volatility (annualized)
- Correlation matrix
- Diversification score
- Sortino ratio (0% risk-free rate)
- Growth vs SPY benchmark

## Trailing Stop Monitor

`trailing_stops.py` — Beta-adjusted volatility trailing stops for each position.

### How it works
- Calculates 30-day rolling annualized volatility and beta to SPY
- Tracks trailing high price per position
- Computes adjusted drop = raw drop from high − (beta × SPY drop from its high)
- Alerts when adjusted drop exceeds 1.5× daily vol for 2 consecutive trading days
- State persisted in `stops_state.json`

### Usage
```bash
python trailing_stops.py --status          # Show current levels for all positions
python trailing_stops.py --check           # Daily monitoring (fires alerts on breach)
```

### Output
- `--status`: Current price, trailing high, vol, beta, distance to stop level
- `--check`: Alert if breached, otherwise "all clear". Resets state after alerting.

## Reports

`report.py` — Multi-cadence portfolio reporting with Slack-formatted output.

### Usage
```bash
python report.py --cadence daily       # Short daily summary (Finnhub live quotes)
python report.py --cadence weekly      # Weekly perf + trailing stops
python report.py --cadence monthly     # Full analytics, 30-day lookback
python report.py --cadence quarterly   # 90-day + momentum trends + weight drift
python report.py --cadence yearly      # 252-day + annual ranking + diversification trend
```

### Cadence Details
- **Daily**: ~10-15 lines. Live quotes, position changes, best/worst, SPY comparison
- **Weekly**: ~20 lines. Weekly changes, trailing stop distances, volatility
- **Monthly**: Full suite — vol, correlation matrix, Sortino, diversification, growth vs SPY, P/L, trailing stops
- **Quarterly**: Monthly + momentum trends (accelerating/decelerating), weight drift from equal-weight
- **Yearly**: Monthly + annual rankings, diversification score trend by quarter

### Data Sources
- Daily: Finnhub live quotes (no rate limit issues)
- Weekly+: AlphaVantage historical (3s delay between calls for rate limiting)

## Momentum Screener

`momentum_screener.py` — Scans the market for top momentum stocks using Yahoo Finance data.

### Usage
```bash
python3 momentum_screener.py                          # Default: top 20 by 10-day momentum
python3 momentum_screener.py --lookback 5             # 5-day momentum
python3 momentum_screener.py --lookback 20            # 20-day (1 month)
python3 momentum_screener.py --top 10                 # Top 10 results
python3 momentum_screener.py --universe bullpen       # Scan bullpen stocks only
python3 momentum_screener.py --universe sp500         # Full S&P 500
python3 momentum_screener.py --min-volume 500000      # Min avg daily volume filter
python3 momentum_screener.py --compare                # Flag current holdings in results
python3 momentum_screener.py --json                   # JSON output
```

### Output
Per-stock: raw return, annualized vol, risk-adjusted momentum, up-day consistency, avg volume.

## Rotation Tracker

`rotation_tracker.py` — Logs portfolio entries/exits and tracks rotation performance.

### Usage
```bash
python3 rotation_tracker.py --log GOOGL exit 311.49 "Trailing stop breach"
python3 rotation_tracker.py --log POWL enter 85.20 "Momentum screener pick"
python3 rotation_tracker.py --stats          # Trade stats (hit rate, avg gain/loss, etc.)
python3 rotation_tracker.py --json           # JSON output
```

## Strategy Document

See `docs/finance/STRATEGY.md` for the full momentum rotation strategy documentation.

## Notes
- Uses AlphaVantage for historical prices (5 calls/min free tier, 3s delay between calls)
- Portfolio data stored as JSON at `~/.openclaw/portfolio.json`
- SPAXX (money market) is excluded from analytics
