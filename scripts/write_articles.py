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
    # The batch is driven by the GRAPH, not a hardcoded persona list: every groundable
    # (decision-maker × jurisdiction) the spine proves — US/EU/GB/JP as peers. This is the whole point
    # of the steering rebuild; iterating personas.yaml keys produced US-only articles by construction.
    from render.steering.enumerate import groundable_analyses
    analyses = groundable_analyses()
    print(f"batch: {len(analyses)} groundable (decision-maker × jurisdiction) analyses from the spine\n")

    rows = []
    for a in analyses:
        pid, jur = a.decision_maker, a.jurisdiction
        tag = f"{pid} [{jur}]"
        try:
            r = build_article_full(pid, conn, article_dir(f"{pid}_{jur}"), jurisdiction=jur,
                                   model_ids=a.grounded_models, backend=backend)
            r["_tag"] = tag
            rows.append(r)
            note = (" | " + "; ".join(r["reasons"])) if r["reasons"] else ""
            # `grounded` first, and it is not the same thing as critic_ok. critic_ok is a style score
            # from an editor that has never seen a number; grounded is whether the arithmetic agrees
            # with the prose. The CB article shipped critic_ok=True with two sentences that
            # contradicted their own series.
            print(f"{'PASS ' if r.get('grounded') else 'CHECK'} {tag:34} {r['words']}w  "
                  f"{r['sections']}sec  charts={r['n_charts']}  grounded={r.get('grounded')}  "
                  f"critic_ok={r['critic_ok']}  “{r['headline'][:60]}”{note}")
            for v in r.get("ungrounded") or []:
                print(f"      UNGROUNDED “{v['quote'][:66]}”\n        {v['detail']}")
        except Exception as exc:
            import traceback
            print(f"FAIL  {tag:34} {type(exc).__name__}: {str(exc)[:160]}")
            traceback.print_exc()

    ok = sum(1 for r in rows if r.get("critic_ok"))
    gr = sum(1 for r in rows if r.get("grounded"))
    print(f"\n{len(rows)}/{len(analyses)} articles   GROUNDED: {gr}/{len(rows)}   "
          f"critic-clean: {ok}/{len(rows)}")
    if gr < len(rows):
        # Hard rule #1: done is a human looking at the output and it being good. The gate does not get
        # to decide, so it says plainly which pieces need reading rather than printing a green tick.
        print(f"\n{len(rows) - gr} article(s) carry prose the arithmetic does not confirm. Read them: "
              + ", ".join(r["persona"] for r in rows if not r.get("grounded")))
    summary = run_root() / "articles" / "_summary.txt"
    summary.write_text("\n".join(
        f"{r['persona']:26} {r['words']}w {r['sections']}sec charts={r['n_charts']} "
        f"grounded={r.get('grounded')} critic_ok={r['critic_ok']} gist={r.get('gist_src','')} "
        f"“{r['headline']}”  {'; '.join(r['reasons'])}" for r in rows))
    print(f"summary → {summary}")


if __name__ == "__main__":
    main()
