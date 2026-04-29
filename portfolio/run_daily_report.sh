#!/usr/bin/env bash
# Generates a daily portfolio report and saves it to reports/YYYY-MM-DD.txt
# Designed to run after market close (default schedule: 21:00 UTC / 4pm ET + buffer)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORTS_DIR="$SCRIPT_DIR/reports"
DATE="$(date +%Y-%m-%d)"
REPORT_FILE="$REPORTS_DIR/$DATE.txt"
LOG_FILE="$REPORTS_DIR/run.log"

mkdir -p "$REPORTS_DIR"

{
  echo "=== Portfolio Daily Report: $DATE ==="
  echo "Generated: $(date)"
  echo ""
  python3 "$SCRIPT_DIR/report.py" --cadence daily --json "$SCRIPT_DIR/portfolio.json"
  echo ""
  echo "=== Trailing Stop Check ==="
  python3 "$SCRIPT_DIR/trailing_stops.py" --status 2>/dev/null || echo "(trailing stop status unavailable)"
} > "$REPORT_FILE" 2>&1

echo "$(date): report written to $REPORT_FILE" >> "$LOG_FILE"

# Optionally send to Slack — set SLACK_WEBHOOK_URL in environment to enable
if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
  REPORT_TEXT="$(cat "$REPORT_FILE")"
  python3 - <<EOF
import json, os, urllib.request
payload = json.dumps({"text": open("$REPORT_FILE").read()}).encode()
req = urllib.request.Request(
    os.environ["SLACK_WEBHOOK_URL"],
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
urllib.request.urlopen(req, timeout=10)
EOF
  echo "$(date): sent to Slack" >> "$LOG_FILE"
fi
