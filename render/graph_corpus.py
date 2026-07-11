"""Load the authored model graph (catalog/graph/*.yaml) and produce per-persona article stubs.

Each model is an enriched YAML spec (see catalog/_ontology.md) that deserializes to an executor
ModelSpec + its chart specs. This module loads them, runs each model over history via the non-LLM
Executor against the live UMD DB, and assembles a persona stub — title + <150-word summary (grounded
strictly in the executed outputs) + the selected insight charts. The LLM authors the prose template;
every number is injected from a ModelRun.
"""
from __future__ import annotations

import base64
import re
import sys
from dataclasses import fields
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import psycopg2  # noqa: E402
import yaml  # noqa: E402

sys.path.insert(0, str(Path.home() / "PycharmProjects/unified_market_data/src"))
from unified_market_data.analysis.executor import (  # noqa: E402
    Executor, ExecutionSpec, InputSpec, ModelSpec, OutputSpec)

from . import from_graph  # noqa: E402

GRAPH_DIR = Path(__file__).resolve().parents[1] / "catalog" / "graph"
_INPUT_FIELDS = {f.name for f in fields(InputSpec)}


def _load_model(model_id: str) -> dict:
    d = yaml.safe_load((GRAPH_DIR / f"{model_id}.yaml").read_text())
    db_sources: dict[str, str] = {}
    inputs = []
    for i in d["inputs"]:
        if i.get("db_source") and i.get("series_id"):
            db_sources[i["series_id"]] = i["db_source"]
        inputs.append(InputSpec(**{k: v for k, v in i.items() if k in _INPUT_FIELDS}))
    spec = ModelSpec(
        model_id=d["model_id"],
        inputs=inputs,
        execution=ExecutionSpec(**d["execution"]),
        outputs=[OutputSpec(**o) for o in d["outputs"]],
        params=(d.get("spec") or {}).get("params", {}) or {})
    return {"spec": spec, "charts": d.get("charts", []), "db_sources": db_sources,
            "history": d.get("history", {}), "meta": d}


def _monthly(start: str, end: str) -> list[str]:
    (ys, ms), (ye, me) = (int(x) for x in start.split("-")), (int(x) for x in end.split("-"))
    out, y, m = [], ys, ms
    while (y, m) <= (ye, me):
        out.append(f"{y}-{m:02d}-28")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _fetch_factory(conn, db_sources: dict[str, str]):
    def fetch(sid: str) -> list[dict]:
        with conn.cursor() as cur:
            src = db_sources.get(sid)
            if src:
                cur.execute("SELECT timestamp, value FROM observations WHERE series_id=%s AND source=%s "
                            "ORDER BY timestamp", (sid, src))
            else:
                cur.execute("SELECT timestamp, value FROM observations WHERE series_id=%s ORDER BY timestamp",
                            (sid,))
            rows = [{"timestamp": str(t), "value": float(v)} for t, v in cur.fetchall()]
        byd = {}
        for r in rows:
            byd[r["timestamp"][:10]] = r          # dedup to one value per date
        return [byd[k] for k in sorted(byd)]
    return fetch


def run_model(model_id: str, conn) -> dict:
    m = _load_model(model_id)
    ex = Executor(_fetch_factory(conn, m["db_sources"]))
    dates = _monthly(m["history"].get("start", "2021-01"), m["history"].get("end", "2026-05"))
    history = ex.run_history(m["spec"], dates)
    return {**m, "history": history, "latest": history[-1] if history else None}


def render_selected(items: list, out_path: str, *, suptitle: str | None = None) -> str:
    """Compose one figure from selected charts that may span models: items = [(chart_spec, history)]."""
    n = len(items)
    ncol = 2 if n > 1 else 1
    nrow = (n + ncol - 1) // ncol
    fig = plt.figure(figsize=(8.2 * ncol, 5.0 * nrow))
    for i, (chart, history) in enumerate(items):
        ax = fig.add_subplot(nrow, ncol, i + 1)
        from_graph.render_chart(ax, chart, history)
    if suptitle:
        fig.suptitle(suptitle, fontsize=13, y=1.0, fontweight="bold")
    fig.savefig(out_path, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def _b64_png(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def build_persona_stub(persona_id: str, conn, out_dir: str) -> dict:
    """Run a persona's models, render its selected charts, and return the stub payload
    (title, grounded summary, chart PNG path, models + papers). The summary template lives in
    catalog/graph/personas.yaml and is formatted with the latest executed outputs."""
    personas = yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"]
    p = personas[persona_id]
    runs = {mid: run_model(mid, conn) for mid in p["models"]}

    # {model.output} -> latest value, for the summary template
    ctx = {}
    for mid, r in runs.items():
        if r["latest"]:
            for name, val in r["latest"].outputs.items():
                ctx[f"{mid}.{name}"] = val
            for iid, obj in r["latest"].inputs.items():
                ctx[f"{mid}.{iid}"] = getattr(obj, "level", obj)
    def _sub(mobj):
        key = mobj.group(1)
        if key not in ctx:
            raise KeyError(f"summary_template references unknown output {{{key}}}")
        v = ctx[key]
        return f"{v:.2f}" if isinstance(v, float) else str(v)

    summary = " ".join(re.sub(r"\{([^}]+)\}", _sub, p["summary_template"]).split())

    items = []
    for mid, chart_id in p["stub_charts"]:
        chart = next(c for c in runs[mid]["charts"] if c["id"] == chart_id)
        items.append((chart, runs[mid]["history"]))
    png = str(Path(out_dir) / f"stub_{persona_id}.png")
    render_selected(items, png, suptitle=p["title"])

    papers = sorted({g for r in runs.values() for g in (r["meta"].get("grounded_in") or [])})
    return {"persona": persona_id, "title": p["title"], "summary": summary,
            "png": png, "png_b64": _b64_png(png), "models": list(runs), "papers": papers,
            "n_charts": len(items)}


if __name__ == "__main__":
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    pid = sys.argv[1] if len(sys.argv) > 1 else "central_bank_policymaker"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp"
    stub = build_persona_stub(pid, conn, out)
    print(f"[{stub['persona']}] {stub['title']}")
    print(f"models: {stub['models']}  papers: {stub['papers']}  charts: {stub['n_charts']}")
    print(f"\nSUMMARY ({len(stub['summary'].split())} words):\n{stub['summary']}")
    print(f"\nfigure: {stub['png']}")
