"""Surface-family gallery: one heatmap renderer across five personas.

Term-premium surface / vol surface / credit ladder / financial conditions / commodity
momentum — each an authored kind:heatmap contract, one render_surface() code path.

    ~/venv/bin/python scripts/surface_gallery.py
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
from render import graph_corpus                                    # noqa: E402
from render.studio.families.surface import render_surface, spec_from_run  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
GRAPH_DIR = REPO / "catalog" / "graph"
OUT = Path("/private/tmp/claude-501/-Users-richardwalker-PycharmProjects-Horizon3/"
           "228d447a-ca1c-45a3-8270-88c34b5c527a/scratchpad/surface_gallery")

JOBS = [
    ("term_premium_surface", "Term-premium surface (tenor x time)", "Macro rates trader"),
    ("financial_conditions", "The subindices as a heatmap (component x time)", "Equity / multi-asset PM"),
    ("credit_quality_ladder", "The credit spread ladder (quality x time)", "Credit investor"),
    ("vol_term_structure", "The implied-vol surface (tenor x time)", "Volatility trader"),
    # commodity_momentum: blocked on the deferred Yahoo→on-demand data migration (task #49) —
    # its CL=F/HG=F/GC=F/ZC=F futures have only 2 points in UMD. Disclosed, not faked.
]


def _conn():
    return psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")


def _load(mid):
    return yaml.safe_load((GRAPH_DIR / f"{mid}.yaml").read_text())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    conn = _conn()
    tiles = []
    for mid, chart_id, persona in JOBS:
        try:
            run = graph_corpus.run_model(mid, conn)
            built = spec_from_run(_load(mid), run, chart_id, persona)
            if not built:
                print(f"FAIL {persona}: spec_from_run None ({mid})"); continue
            dates, mat, spec = built
            out = OUT / f"{mid}.png"
            render_surface(dates, mat, spec, str(out))
            tiles.append((persona, out))
            print(f"OK  {persona:24}| {spec.title}   [{len(spec.items)}x{len(dates)}{' signed' if spec.signed else ''}]")
        except Exception as exc:
            print(f"FAIL {persona} ({mid}): {type(exc).__name__}: {str(exc)[:200]}")

    if tiles:
        n = len(tiles); ncols = 2
        nrows = (n + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(24, 6.2 * nrows))
        for ax, (_p, png) in zip(axes.ravel(), tiles):
            ax.imshow(mpimg.imread(str(png))); ax.axis("off")
        for ax in axes.ravel()[n:]:
            ax.axis("off")
        fig.subplots_adjust(left=0.004, right=0.996, top=0.99, bottom=0.01, wspace=0.03, hspace=0.06)
        sheet = OUT / "_contact_sheet.png"
        fig.savefig(str(sheet), dpi=90, facecolor="white"); plt.close(fig)
        print(f"\ncontact sheet -> {sheet}")


if __name__ == "__main__":
    main()
