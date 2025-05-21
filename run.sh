#!/bin/bash
cd "$(dirname "$0")"

# Rotate log if it gets too large (>10MB)
if [ -f logs/domain-monitor.log ] && [ $(stat -f%z logs/domain-monitor.log 2>/dev/null || stat -c%s logs/domain-monitor.log) -gt 10485760 ]; then
    mv logs/domain-monitor.log logs/domain-monitor.log.old
fi

echo "=== $(date) ===" >> logs/domain-monitor.log

# Show output on screen if running interactively, log to file if running from cron
if [ -t 1 ]; then
    # Interactive - show on screen and log to file
    uv run --with-requirements requirements.txt python domain_monitor.py check 2>&1 | tee -a logs/domain-monitor.log
else
    # Non-interactive (cron) - log to file only
    uv run --with-requirements requirements.txt python domain_monitor.py check >> logs/domain-monitor.log 2>&1
fi