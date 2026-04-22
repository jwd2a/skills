#!/usr/bin/env bash
# Daily portfolio analysis — runs after US market close (scheduled 21:30 UTC / 4:30 PM ET)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"

mkdir -p "$LOG_DIR"

{
  echo "===== Portfolio Daily Report: $(date -u '+%Y-%m-%d %H:%M:%S UTC') ====="
  echo ""

  python3 "$SCRIPT_DIR/report.py" \
    --cadence daily \
    --json "$SCRIPT_DIR/portfolio.json"

  echo ""
  echo "--- Trailing Stops ---"
  python3 "$SCRIPT_DIR/trailing_stops.py" --check || true

} | tee "$LOG_FILE"
