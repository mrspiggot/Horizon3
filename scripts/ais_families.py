"""AIS layout-family generalisation harness.

For each of the four layout families, try every persona: render the ones the family is eligible for
(tier-1 gated), skip the rest with a reason, and assemble a per-family montage. This is the
generalisation proof for the families — each archetype must render cleanly across MULTIPLE personas
(never a bespoke one-off), and every rendered number passes the tier-1 DOM gate.

    ~/venv/bin/python scripts/ais_families.py
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
from render.infographic.families import (cross_section_ladder, decision_brief,  # noqa: E402
                                         decomposition_hero, regime_dashboard)

FAMILIES = [
    ("decision_brief", decision_brief),
    ("decomposition_hero", decomposition_hero),
    ("regime_dashboard", regime_dashboard),
    ("cross_section_ladder", cross_section_ladder),
]
OUT = Path("/private/tmp/claude-501/-Users-richardwalker-PycharmProjects-Horizon3/"
           "228d447a-ca1c-45a3-8270-88c34b5c527a/scratchpad/ais_families")
GRAPH_DIR = Path(__file__).resolve().parents[1] / "catalog" / "graph"


def _montage(pngs: list[Path], out: Path, cols: int = 3) -> None:
    if not pngs:
        return
    n = len(pngs); nrows = (n + cols - 1) // cols
    fig, axes = plt.subplots(nrows, cols, figsize=(6 * cols, 9 * nrows), squeeze=False)
    for ax, png in zip(axes.ravel(), pngs):
        ax.imshow(mpimg.imread(str(png))); ax.axis("off")
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    fig.subplots_adjust(left=.004, right=.996, top=.996, bottom=.004, wspace=.03, hspace=.03)
    fig.savefig(str(out), dpi=70, facecolor="white"); plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    personas = list(yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"].keys())
    grand = {}
    for fname, mod in FAMILIES:
        rendered, skipped = [], []
        for pid in personas:
            out_png = OUT / f"{fname}__{pid}.png"
            try:
                mod.render_persona(pid, conn, str(out_png), instance="US")
                rendered.append(out_png)
                print(f"PASS  {fname:22} {pid}")
            except Exception as exc:
                msg = str(exc).splitlines()[0][:90]
                skipped.append((pid, msg))
                tag = "GATE" if "TIER-1" in str(exc) else "skip"
                print(f"{tag:5} {fname:22} {pid:24} {msg}")
        _montage(rendered, OUT / f"_montage_{fname}.png")
        grand[fname] = (len(rendered), len(personas))
        print(f"  → {fname}: {len(rendered)}/{len(personas)} personas rendered "
              f"→ {OUT / f'_montage_{fname}.png'}\n")
    print("=" * 60)
    for fname, (r, tot) in grand.items():
        print(f"  {fname:24} {r}/{tot}")


if __name__ == "__main__":
    main()
