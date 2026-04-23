#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/reports/$(date +%Y-%m-%d).txt"
python3 "$DIR/report.py" --cadence daily --json "$DIR/portfolio.json" > "$LOG" 2>&1
echo "Report written to $LOG"
