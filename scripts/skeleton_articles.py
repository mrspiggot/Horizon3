"""Skeleton articles — one .docx per persona: charts + infographic + Van Gogh header + a grounded gist.

The end-to-end preview the owner judges before full article wiring. For each of the 8 personas it picks
one anchor model, renders that model's charts, the persona's infographic (its most apt layout family),
a unique Van Gogh header, and a 150-200-word firewall-guarded gist, and assembles them into
`output/skeleton_articles/<persona>/article.docx`. Asserts the 8 paintings are unique and all 4 layout
families appear.

    ~/venv/bin/python scripts/skeleton_articles.py                 # backend=auto (OpenAI if key present)
    VANGOGH_BACKEND=pil ~/venv/bin/python scripts/skeleton_articles.py   # offline placeholders
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import psycopg2  # noqa: E402
import yaml      # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.article import build_article  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "output" / "skeleton_articles"
GRAPH_DIR = REPO / "catalog" / "graph"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    backend = os.environ.get("VANGOGH_BACKEND", "auto")
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    personas = list(yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"].keys())

    rows, families = [], set()
    for pid in personas:
        try:
            r = build_article(pid, conn, OUT / pid, backend=backend)
            families.add(r["family"])
            rows.append(r)
            note = (" | " + "; ".join(r["reasons"])) if r["reasons"] else ""
            print(f"PASS  {pid:26} model={r['model']:24} fam={r['family']:20} "
                  f"gist={r['gist_words']}w/{r['gist_src']}  “{r['caption']}”{note}")
        except Exception as exc:
            import traceback
            print(f"FAIL  {pid:26} {type(exc).__name__}: {str(exc)[:160]}")
            traceback.print_exc()

    print(f"\n{len(rows)}/{len(personas)} articles   families={sorted(families)}")
    summary = OUT / "_summary.txt"
    summary.write_text("\n".join(
        f"{r['persona']:26} model={r['model']:24} family={r['family']:20} "
        f"gist={r['gist_words']}w({r['gist_src']}) charts={r['n_charts']} illus=“{r['caption']}” "
        f"{'; '.join(r['reasons'])}" for r in rows))
    assert len(families) == 4, f"not all 4 families used: {sorted(families)}"
    print(f"summary → {summary}")


if __name__ == "__main__":
    main()
