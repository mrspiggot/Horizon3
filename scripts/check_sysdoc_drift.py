#!/usr/bin/env python
"""Drift-gate: fail if the code's architecture has diverged from the committed doc.

Rebuilds the manifest from live code (spine census skipped by default — data freshness
is not code drift) and compares its architecture parts (graphs, ats, schemas, catalog)
to the committed docs/system/system_manifest.json.

    ~/venv/bin/python scripts/check_sysdoc_drift.py                 # exit 1 on drift
    ~/venv/bin/python scripts/check_sysdoc_drift.py --include-spine # also compare the census
    ~/venv/bin/python scripts/check_sysdoc_drift.py --changelog A.json B.json

Wire it as a pre-commit hook or CI step:
    - repo: local
      hooks:
        - id: sysdoc-drift
          name: sysdoc architecture drift
          entry: ~/venv/bin/python scripts/check_sysdoc_drift.py
          language: system
          pass_filenames: false
On drift: run `scripts/gen_sysdoc.py` and commit the regenerated docs.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from render.sysdoc.build import build_manifest  # noqa: E402
from render.sysdoc.diff import diff_manifests  # noqa: E402
from render.sysdoc.manifest import MANIFEST_PATH  # noqa: E402


def _print(lines, header):
    if lines:
        print(header)
        for ln in lines:
            print(ln)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--include-spine", action="store_true", help="also compare the spine census")
    ap.add_argument("--changelog", nargs=2, metavar=("OLD", "NEW"),
                    help="print the architecture changelog between two manifest JSON files")
    args = ap.parse_args()

    if args.changelog:
        old = json.loads(Path(args.changelog[0]).read_text(encoding="utf-8"))
        new = json.loads(Path(args.changelog[1]).read_text(encoding="utf-8"))
        d = diff_manifests(old, new)
        print(f"# Architecture changelog  ({d['version']})")
        _print(d["code_lines"], "\n## Code / architecture")
        _print(d["spine_lines"], "\n## Spine census")
        if not d["code_lines"] and not d["spine_lines"]:
            print("no differences")
        return 0

    if not MANIFEST_PATH.exists():
        print(f"no committed manifest at {MANIFEST_PATH.relative_to(REPO)} — run gen_sysdoc.py first",
              file=sys.stderr)
        return 2

    committed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fresh = asdict(build_manifest(with_spine=args.include_spine))
    d = diff_manifests(committed, fresh)

    drift = d["code_changed"] or (args.include_spine and bool(d["spine_lines"]))
    if not drift:
        print(f"✓ sysdoc in sync ({d['version']}) — no architecture drift")
        return 0

    print(f"✗ sysdoc DRIFT ({d['version']}) — regenerate with scripts/gen_sysdoc.py")
    _print(d["code_lines"], "\n-- code / architecture --")
    if args.include_spine:
        _print(d["spine_lines"], "\n-- spine census --")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
