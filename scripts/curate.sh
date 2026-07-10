#!/bin/bash
# Twice-weekly knowledge-corpus curation (arXiv discovery -> review digest).
# Cron:  0 9 * * 0,3  /Users/richardwalker/PycharmProjects/Horizon3/scripts/curate.sh
# Pattern mirrors unified_market_data/scripts/lch_scrape.sh.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# .env first (secrets: SMTP_*), then .env.generated last (registry wins) if present
[ -f .env ] && set -a && source .env && set +a
[ -f .env.generated ] && set -a && source .env.generated && set +a

# shared venv (has chromadb, pymupdf, pyyaml, requests)
PY="${HORIZON3_PYTHON:-$HOME/venv/bin/python}"

exec "$PY" -m knowledge.curate
