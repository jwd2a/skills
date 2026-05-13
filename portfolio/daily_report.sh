#!/usr/bin/env bash
# Daily portfolio report runner — output appended to daily_reports.log
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$SCRIPT_DIR/daily_reports.log"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
  cd "$SCRIPT_DIR"
  python report.py --cadence daily
  echo ""
} >> "$LOG" 2>&1
