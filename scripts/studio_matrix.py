"""Generalisation metric harness for the Agentic Chart Subsystem (ACS).

Runs the Studio across personas × their authored charts and reports OBJECTIVE metrics — the mark
distribution (are we escaping line-dominance?), the judge pass-rate, and insight-type coverage —
so "more capable + generalises" is measured, not asserted.

    python scripts/studio_matrix.py                 # all 8 personas
    python scripts/studio_matrix.py credit_investor macro_rates_trader   # a subset
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaml  # noqa: E402

from render.studio.from_model import studio_charts_for_persona  # noqa: E402

OUT = Path("/private/tmp/claude-501/-Users-richardwalker-PycharmProjects-Horizon3/"
           "228d447a-ca1c-45a3-8270-88c34b5c527a/scratchpad/studio_matrix")
GRAPH_DIR = Path(__file__).resolve().parents[1] / "catalog" / "graph"


def main(personas: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    all_rows = []
    for pid in personas:
        print(f"\n######## {pid} ########", flush=True)
        try:
            res = studio_charts_for_persona(pid, conn, str(OUT / pid))
        except Exception as exc:
            print(f"  PERSONA FAILED: {type(exc).__name__}: {str(exc)[:160]}")
            continue
        for r in res:
            r["persona"] = pid
            all_rows.append(r)
            print(f"  {r.get('insight_type','?'):13} → mark={r.get('mark')!s:16} "
                  f"judge={'PASS' if r.get('judge_pass') else 'fail'} | {(r.get('title') or r.get('error') or '')[:60]}",
                  flush=True)

    ok = [r for r in all_rows if r.get("mark")]
    marks = Counter(str(r["mark"]) for r in ok)
    n = sum(marks.values()) or 1
    line_share = (marks.get("line", 0) + marks.get("area", 0)) / n
    passed = sum(1 for r in ok if r.get("judge_pass"))
    itypes = Counter(r.get("insight_type", "?") for r in all_rows)

    print("\n" + "=" * 60)
    print("ACS GENERALISATION REPORT")
    print("=" * 60)
    print(f"charts rendered: {n} across {len(personas)} personas")
    print(f"\nMARK DISTRIBUTION (target: line+area ≤ ~40%, diverse):")
    for m, c in marks.most_common():
        print(f"  {m:18} {c:3}  {'█' * c}")
    print(f"  → line+area share: {line_share:.0%}")
    print(f"\nJUDGE PASS-RATE: {passed}/{n} = {passed/n:.0%}")
    by_p = {}
    for r in ok:
        by_p.setdefault(r["persona"], []).append(bool(r.get("judge_pass")))
    for p, v in by_p.items():
        print(f"  {p:26} {sum(v)}/{len(v)}")
    print(f"\nINSIGHT-TYPE COVERAGE:")
    for t, c in itypes.most_common():
        print(f"  {t:14} {c}")
    (OUT / "report.json").write_text(json.dumps(
        {"marks": dict(marks), "line_area_share": line_share, "pass": passed, "n": n,
         "insight_types": dict(itypes), "rows": all_rows}, indent=1, default=str))
    print(f"\nsaved: {OUT/'report.json'}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        args = list(yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"].keys())
    main(args)
