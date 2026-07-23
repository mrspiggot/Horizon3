#!/bin/bash
# Horizon3 ATS — the Monday & Thursday morning briefing, emailed to the owner.
# Cron:  0 7 * * 1,4  /Users/richardwalker/PycharmProjects/Horizon3/scripts/ats.sh
# Pattern mirrors scripts/curate.sh (env sourcing + HORIZON3_PYTHON + module exec). Requires SMTP_*
# in .env (SMTP_HOST/PORT/USER/PASS/FROM, optional SMTP_TO). Fails soft — a bad feed never blocks the send.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# .env first (secrets: SMTP_*, FRED_API_KEY, ANTHROPIC/OPENAI keys), then .env.generated last
[ -f .env ] && set -a && source .env && set +a
[ -f .env.generated ] && set -a && source .env.generated && set +a

PY="${HORIZON3_PYTHON:-$HOME/venv/bin/python}"
exec "$PY" scripts/ats_briefing.py --as-of "$(date +%F)" --email
