#!/bin/bash
cd "$(dirname "$0")"

# Rotate log if it gets too large (>10MB)
if [ -f logs/domain-monitor.log ] && [ $(stat -f%z logs/domain-monitor.log 2>/dev/null || stat -c%s logs/domain-monitor.log) -gt 10485760 ]; then
    mv logs/domain-monitor.log logs/domain-monitor.log.old
fi

echo "=== $(date) ===" >> logs/domain-monitor.log
uv run --with-requirements requirements.txt python domain_monitor.py check >> logs/domain-monitor.log 2>&1