"""sysdoc — living documentation for the Horizon3 agentic system.

A two-tier generator that separates *machine truth* (auto-extracted, volatile) from
*human narrative* (hand-owned, durable):

    Tier 1  extract_*  → a versioned SystemManifest (docs/system/system_manifest.json)
    Tier 2  render_*    → the HTML + markdown docs, injecting the manifest into a
                          stable narrative shell

plus `diff` (a manifest→manifest architecture changelog) and the drift-gate in
`scripts/check_sysdoc_drift.py`. The LangGraph DAGs and the Neo4j spine are the two
fastest-churning parts of the system and are exactly the parts extracted from ground
truth here, so the diagrams and counts never silently go stale.
"""
from __future__ import annotations
