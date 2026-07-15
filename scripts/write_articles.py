"""Full-article writer across all 8 personas → one ~1000-1200w .docx feature each.

Runs render/writer.build_article_full for every persona: a narrative arc with a foreshadowing
executive summary (naming the pivot, defining terms), the models woven together, charts inline (the
richest comparison chart preferred, redundant 'today' snapshots dropped), the Van Gogh header, the
infographic as the visual summary, real 'Further reading' citations — every figure firewall-traced and
the StoryScope anti-slop critic clean. Deliverables land in output/articles/<persona>/article.docx.

    ~/venv/bin/python scripts/write_articles.py                    # backend=auto (OpenAI illus if key)
    VANGOGH_BACKEND=openai ~/venv/bin/python scripts/write_articles.py
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
from render.writer import build_article_full  # noqa: E402
from render.output_paths import article_dir, run_root  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
GRAPH_DIR = REPO / "catalog" / "graph"


def main() -> None:
    backend = os.environ.get("VANGOGH_BACKEND", "auto")
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    personas = list(yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"].keys())

    rows = []
    for pid in personas:
        try:
            r = build_article_full(pid, conn, article_dir(pid), backend=backend)
            rows.append(r)
            note = (" | " + "; ".join(r["reasons"])) if r["reasons"] else ""
            print(f"PASS  {pid:26} {r['words']}w  {r['sections']}sec  charts={r['n_charts']}  "
                  f"critic_ok={r['critic_ok']}  “{r['headline'][:60]}”{note}")
        except Exception as exc:
            import traceback
            print(f"FAIL  {pid:26} {type(exc).__name__}: {str(exc)[:160]}")
            traceback.print_exc()

    ok = sum(1 for r in rows if r.get("critic_ok"))
    print(f"\n{len(rows)}/{len(personas)} articles   critic-clean: {ok}/{len(rows)}")
    summary = run_root() / "articles" / "_summary.txt"
    summary.write_text("\n".join(
        f"{r['persona']:26} {r['words']}w {r['sections']}sec charts={r['n_charts']} "
        f"critic_ok={r['critic_ok']} gist={r.get('gist_src','')} "
        f"“{r['headline']}”  {'; '.join(r['reasons'])}" for r in rows))
    print(f"summary → {summary}")


if __name__ == "__main__":
    main()
