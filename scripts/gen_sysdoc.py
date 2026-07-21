#!/usr/bin/env python
"""Generate the living architecture doc for the Horizon3 agentic system.

Extracts the LangGraph DAGs + Neo4j spine census + prompt inventory into
docs/system/system_manifest.json, then renders the HTML + markdown docs from it and a
hand-owned narrative shell.

    ~/venv/bin/python scripts/gen_sysdoc.py                # full build (live spine)
    ~/venv/bin/python scripts/gen_sysdoc.py --no-spine     # code-only (skip Neo4j)
    ~/venv/bin/python scripts/gen_sysdoc.py --snapshot     # also write docs/system/snapshots/<sha>/

Design: machine-truth (auto) is separated from narrative (hand-owned in
render/sysdoc/narrative/). The generator never overwrites the narrative.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from render.sysdoc.build import build_manifest  # noqa: E402
from render.sysdoc.manifest import MANIFEST_PATH  # noqa: E402
from render.sysdoc.render_html import DEFAULT_HTML, write_html  # noqa: E402
from render.sysdoc.render_md import DEFAULT_MD, write_markdown  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-spine", action="store_true", help="skip the live Neo4j census")
    ap.add_argument("--snapshot", action="store_true", help="also write a versioned snapshot")
    args = ap.parse_args()

    m = build_manifest(with_spine=not args.no_spine)
    mpath = m.write(MANIFEST_PATH)
    hpath = write_html(m, DEFAULT_HTML)
    dpath = write_markdown(m, DEFAULT_MD)

    print(f"manifest : {mpath.relative_to(REPO)}")
    print(f"html     : {hpath.relative_to(REPO)}")
    print(f"markdown : {dpath.relative_to(REPO)}")
    print(f"version  : {m.version.pyproject} · {m.version.git_sha} ({m.version.branch})")
    print(f"graphs   : {', '.join(f'{g.name}({len(g.nodes)})' for g in m.graphs)} · ats({len(m.ats.stages)})")
    if m.spine.online:
        print(f"spine    : ONLINE — {m.spine.executable_models} models, {m.spine.proven_cells} cells")
    else:
        print(f"spine    : offline ({m.spine.error})")

    if args.snapshot:
        sha = m.version.git_sha or "nosha"
        snap = REPO / "docs" / "system" / "snapshots" / sha
        snap.mkdir(parents=True, exist_ok=True)
        for p in (mpath, hpath, dpath):
            shutil.copy2(p, snap / p.name)
        print(f"snapshot : {snap.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
