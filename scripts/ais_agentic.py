"""AIS agentic harness — the LLM-narrated, critic-reviewed infographic across every persona.

Runs render/infographic/agentic.run_agentic for all 8 personas (LLM authors the thesis + read with
verified numbers; deterministic tier-1 gate then multimodal critic, bounded-looping), and assembles
a montage. Slower than the deterministic ais_report.py (multiple Opus calls per persona).

    ~/venv/bin/python scripts/ais_agentic.py
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
from render.infographic.agentic import run_agentic  # noqa: E402

OUT = Path("/private/tmp/claude-501/-Users-richardwalker-PycharmProjects-Horizon3/"
           "228d447a-ca1c-45a3-8270-88c34b5c527a/scratchpad/ais_agentic")
GRAPH_DIR = Path(__file__).resolve().parents[1] / "catalog" / "graph"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    personas = list(yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"].keys())
    tiles, npass, ncritic = [], 0, 0
    for pid in personas:
        try:
            r = run_agentic(pid, conn, str(OUT / f"{pid}.png"), max_iter=3)
            if r["ok"]:
                tiles.append(OUT / f"{pid}.png"); npass += 1
                ncritic += 1 if r.get("critic_ok") else 0
                print(f"PASS  {pid:26} iters={r['iters']} critic_ok={r.get('critic_ok')}")
                print(f"      thesis: {r.get('thesis','')[:150]}")
            else:
                print(f"FAIL  {pid:26} tier1: {r.get('problems')}")
        except Exception as exc:
            print(f"ERR   {pid:26} {type(exc).__name__}: {str(exc)[:160]}")

    print(f"\nTIER-1 CLEAN: {npass}/{len(personas)}   CRITIC-CLEAN: {ncritic}/{len(personas)}")
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
