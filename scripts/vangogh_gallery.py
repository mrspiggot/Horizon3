"""Van Gogh gallery — one header illustration per article, each generated FROM that article's finding.

For every persona it takes the article's actual number-filled finding, lets the art-director invent a
van Gogh scene that evokes it, renders it (OpenAI gpt-image-1 by default; PIL offline), and montages the
eight with the art-director's metaphor caption for human review. The proof is fidelity — does each
picture evoke ITS article — not a fixed variety count.

    ~/venv/bin/python scripts/vangogh_gallery.py                    # backend=auto (OpenAI if key present)
    VANGOGH_BACKEND=pil ~/venv/bin/python scripts/vangogh_gallery.py
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt   # noqa: E402
import psycopg2                   # noqa: E402
import yaml                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.article import MODEL_PICK, _fill_template     # noqa: E402
from render.illustration import illustration_png          # noqa: E402
from render.infographic.from_persona import persona_material  # noqa: E402

OUT = Path("/private/tmp/claude-501/-Users-richardwalker-PycharmProjects-Horizon3/"
           "228d447a-ca1c-45a3-8270-88c34b5c527a/scratchpad/vangogh")
GRAPH_DIR = Path(__file__).resolve().parents[1] / "catalog" / "graph"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    backend = os.environ.get("VANGOGH_BACKEND", "auto")
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    personas = yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"]

    tiles = []
    for pid, p in personas.items():
        mat = persona_material(pid, conn)
        finding = _fill_template(mat)                       # the article's actual, number-filled content
        b64, meta = illustration_png(finding, title=p["title"], decision=p.get("decision", ""),
                                     cache_key=f"{pid}|{MODEL_PICK.get(pid, '')}", backend=backend)
        png = OUT / f"{pid}.png"
        png.write_bytes(base64.b64decode(b64))
        tiles.append((png, p["name"], meta.get("caption", "")))
        print(f"PASS  {pid:26} “{meta.get('caption','')}”")

    ncols, nrows = 2, 4
    fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 4.2 * nrows))
    for ax, (png, name, cap) in zip(axes.ravel(), tiles):
        ax.imshow(mpimg.imread(str(png))); ax.axis("off")
        ax.set_title(f"{name} — {cap}", fontsize=10)
    for ax in axes.ravel()[len(tiles):]:
        ax.axis("off")
    fig.subplots_adjust(left=.01, right=.99, top=.96, bottom=.01, wspace=.04, hspace=.16)
    sheet = OUT / "_montage.png"
    fig.savefig(str(sheet), dpi=95, facecolor="white"); plt.close(fig)
    print(f"\nmontage → {sheet}   (backend={backend})")


if __name__ == "__main__":
    main()
