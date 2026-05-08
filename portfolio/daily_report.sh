#!/usr/bin/env bash
# Runs the full daily portfolio analysis and appends output to a dated log.
set -euo pipefail

PORTFOLIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PORTFOLIO_DIR}/logs"
DATE=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/portfolio_${DATE}.log"

mkdir -p "$LOG_DIR"

{
  echo "================================================================"
  echo " FULL PORTFOLIO ANALYSIS — ${DATE} $(date +%H:%M %Z)"
  echo "================================================================"

  echo ""
  echo "--- DAILY P&L ---"
  python "${PORTFOLIO_DIR}/report.py" --cadence daily 2>&1 || echo "⚠️  report.py failed"

  echo ""
  echo "--- 90-DAY ANALYTICS ---"
  python "${PORTFOLIO_DIR}/analyze.py" --days 90 2>&1 || echo "⚠️  analyze.py failed"

  echo ""
  echo "--- TRAILING STOP ALERTS ---"
  python "${PORTFOLIO_DIR}/trailing_stops.py" --check 2>&1 || echo "⚠️  trailing_stops.py failed"

  echo ""
  echo "--- MOMENTUM SCREENER (Top 20, vs holdings) ---"
  python "${PORTFOLIO_DIR}/momentum_screener.py" --top 20 --compare 2>&1 || echo "⚠️  momentum_screener.py failed"

  echo ""
  echo "================================================================"
  echo " END OF REPORT"
  echo "================================================================"
} | tee "$LOG_FILE"

echo ""
echo "Report saved to: $LOG_FILE"
