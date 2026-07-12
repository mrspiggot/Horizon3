"""Relationship-family gallery: one renderer for models whose output IS a fit between inputs.

Phillips (fit) / Okun (fit) / Beveridge (path) through render_relationship, each consuming
an already-authored kind:scatter contract. Every chart lint-gated.

    ~/venv/bin/python scripts/relationship_gallery.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt   # noqa: E402
import psycopg2                   # noqa: E402
import yaml                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render import graph_corpus                                              # noqa: E402
from render.studio.families.relationship import (                           # noqa: E402
    render_relationship, spec_from_run)

REPO = Path(__file__).resolve().parents[1]
GRAPH_DIR = REPO / "catalog" / "graph"
OUT = Path("/private/tmp/claude-501/-Users-richardwalker-PycharmProjects-Horizon3/"
           "228d447a-ca1c-45a3-8270-88c34b5c527a/scratchpad/relationship_gallery")

JOBS = [
    ("phillips_curve", "The Phillips curve (unemployment vs inflation)", "Central banker"),
    ("okun_law", "Okun's Law (GDP growth vs change in unemployment)", "Economist / forecaster"),
    ("beveridge_curve", "The Beveridge curve (vacancies vs unemployment)", "Economist / forecaster"),
]


def _conn():
    return psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")


def _load_model(mid: str) -> dict:
    return yaml.safe_load((GRAPH_DIR / f"{mid}.yaml").read_text())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    conn = _conn()
    tiles = []
    for mid, chart_id, persona in JOBS:
        try:
            run = graph_corpus.run_model(mid, conn)
            built = spec_from_run(_load_model(mid), run, chart_id, persona)
            if not built:
                print(f"FAIL {persona}: spec_from_run None ({mid})"); continue
            df, spec = built
            out = OUT / f"{mid}.png"
            render_relationship(df, spec, str(out))
            tiles.append((persona, spec.mode, out))
            print(f"OK  {persona:24}| {spec.mode:4} | {spec.title}   [{len(df)} pts]")
        except Exception as exc:
            print(f"FAIL {persona} ({mid}): {type(exc).__name__}: {str(exc)[:200]}")

    if tiles:
        fig, axes = plt.subplots(1, 3, figsize=(30, 8.2))
        for ax, (_p, _m, png) in zip(axes.ravel(), tiles):
            ax.imshow(mpimg.imread(str(png))); ax.axis("off")
        fig.subplots_adjust(left=0.004, right=0.996, top=0.99, bottom=0.01, wspace=0.02)
        sheet = OUT / "_contact_sheet.png"
        fig.savefig(str(sheet), dpi=100, facecolor="white"); plt.close(fig)
        print(f"\ncontact sheet -> {sheet}")


if __name__ == "__main__":
    main()
