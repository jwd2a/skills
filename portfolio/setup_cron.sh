#!/usr/bin/env bash
# Installs a daily 6 PM cron job for the portfolio report.
# Run this once on your machine to register the schedule.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/run_daily_report.sh"

chmod +x "$RUNNER"

CRON_LINE="0 18 * * * $RUNNER"
COMMENT="# Daily portfolio analysis (after market close)"

# Avoid duplicate entries
if crontab -l 2>/dev/null | grep -qF "$RUNNER"; then
  echo "Cron job already installed."
else
  (crontab -l 2>/dev/null; echo "$COMMENT"; echo "$CRON_LINE") | crontab -
  echo "Cron job installed: runs daily at 6:00 PM."
  echo "Output logs to: $SCRIPT_DIR/daily_report.log"
fi

echo ""
echo "Current crontab:"
crontab -l
