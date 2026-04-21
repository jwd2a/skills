#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/reports"
mkdir -p "$LOG_DIR"

DATE="$(date +%Y-%m-%d)"
OUT="$LOG_DIR/daily_${DATE}.txt"

cd "$SCRIPT_DIR"
python report.py --cadence daily --json portfolio.json > "$OUT" 2>&1
echo "Daily report written to $OUT"
