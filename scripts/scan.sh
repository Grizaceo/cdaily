#!/usr/bin/env bash
# scan.sh — Run blogwatcher-cli scan, meant to be called by cron
# Exit codes: 0 = success, 1 = error

set -e

LOG="${HOME}/.blogwatcher-cli/scan.log"
BLOGWATCHER="${HOME}/.local/bin/blogwatcher-cli"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting scan..." >> "$LOG"

if ! "$BLOGWATCHER" scan >> "$LOG" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: scan failed" >> "$LOG"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scan complete." >> "$LOG"
exit 0
