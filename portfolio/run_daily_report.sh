#!/usr/bin/env bash
# Daily portfolio analysis runner.
# Runs report.py --cadence daily and appends output to daily_report.log.
# Designed to be called from cron or any scheduler.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/daily_report.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

{
  echo "========================================"
  echo "Run: $TIMESTAMP"
  echo "========================================"
  python "$SCRIPT_DIR/report.py" --cadence daily --json "$SCRIPT_DIR/portfolio.json"
  echo ""
} >> "$LOG_FILE" 2>&1

echo "Daily portfolio report complete. Output appended to $LOG_FILE"
