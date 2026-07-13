"""AIS coverage harness — render the infographic for every persona, prove generalisation.

Sibling of scripts/families_report.py. Renders the decision_brief infographic for all 8 personas
through the tier-1 gate (numeric-equality / provenance / units / structure), reports the pass rate,
and assembles an 8-up montage for human review. The phase does not close until every persona renders
gate-clean and the montage is judged good.

    ~/venv/bin/python scripts/ais_report.py
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
from render.infographic.families import decision_brief as db  # noqa: E402
from render.infographic.gate import emit  # noqa: E402

OUT = Path("/private/tmp/claude-501/-Users-richardwalker-PycharmProjects-Horizon3/"
           "228d447a-ca1c-45a3-8270-88c34b5c527a/scratchpad/ais")
GRAPH_DIR = Path(__file__).resolve().parents[1] / "catalog" / "graph"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    personas = list(yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"].keys())
    tiles, npass = [], 0
    for pid in personas:
        try:
            spec, valid = db.spec_from_persona(pid, conn)
            out = OUT / f"{pid}.png"
            emit(spec, str(out), valid)
            nnum = len(spec.all_numbers())
            ntile = len(spec.blocks_of("kpi_tile"))
            nchart = len(spec.blocks_of("chart_embed"))
            tiles.append(out); npass += 1
            print(f"PASS  {pid:26} tiles={ntile} charts={nchart} numbers={nnum} (all DOM-verified)")
        except Exception as exc:
            print(f"FAIL  {pid:26} {type(exc).__name__}: {str(exc)[:180]}")

    print(f"\nTIER-1 PASS RATE: {npass}/{len(personas)}")
    if tiles:
        n = len(tiles); ncols = 4; nrows = (n + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 9 * nrows))
        for ax, png in zip(axes.ravel(), tiles):
            ax.imshow(mpimg.imread(str(png))); ax.axis("off")
        for ax in axes.ravel()[n:]:
            ax.axis("off")
        fig.subplots_adjust(left=0.004, right=0.996, top=0.996, bottom=0.004, wspace=0.03, hspace=0.03)
        sheet = OUT / "_montage.png"
        fig.savefig(str(sheet), dpi=70, facecolor="white"); plt.close(fig)
        print(f"montage -> {sheet}")


if __name__ == "__main__":
    main()
