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
CATALOG_DIR = GRAPH_DIR.parent
_INPUT_FIELDS = {f.name for f in fields(InputSpec)}
_JUR_CACHE: dict | None = None


def _jurisdictions() -> dict:
    """Load the jurisdiction axis (catalog/jurisdictions.yaml): {id: {meta, bindings{role:(ref,source)}}}."""
    global _JUR_CACHE
    if _JUR_CACHE is None:
        d = yaml.safe_load((CATALOG_DIR / "jurisdictions.yaml").read_text())
        out = {}
        for j in d.get("jurisdictions", []):
            b = {}
            for role, binding in (j.get("bindings") or {}).items():
                if isinstance(binding, dict) and binding.get("ref"):
                    b[role] = (binding["ref"], binding.get("source"))
            out[j["id"]] = {"meta": j, "bindings": b}
        _JUR_CACHE = out
    return _JUR_CACHE


def _load_model(model_id: str, instance: str | None = None) -> dict:
    """Deserialize a model. Inputs may be jurisdiction-generic (carry a `role`) or legacy (a concrete
    `series_id`). For a role-based model, roles are resolved to that jurisdiction's series via the
    jurisdiction axis — `instance` defaults to the model's first declared instance, so the US is one
    instance among the Fed/ECB/BoE/BoJ, never the definition."""
    d = yaml.safe_load((GRAPH_DIR / f"{model_id}.yaml").read_text())
    instances = d.get("instances") or ["US"]
    inst = instance or instances[0]
    jbind = _jurisdictions().get(inst, {}).get("bindings", {})
    db_sources: dict[str, str] = {}
    inputs = []
    for i in d["inputs"]:
        ii = dict(i)
        if i.get("role"):                                   # jurisdiction-generic: resolve role -> series
            if i["role"] not in jbind:
                raise KeyError(f"{model_id}: role '{i['role']}' has no binding for jurisdiction '{inst}'")
            sid, src = jbind[i["role"]]
            ii["series_id"] = sid
            if src and src != "observations":
                db_sources[sid] = src
        elif i.get("db_source") and i.get("series_id"):     # legacy concrete series
            db_sources[i["series_id"]] = i["db_source"]
        inputs.append(InputSpec(**{k: v for k, v in ii.items() if k in _INPUT_FIELDS}))
    spec = ModelSpec(
        model_id=d["model_id"],
        inputs=inputs,
        execution=ExecutionSpec(**d["execution"]),
        outputs=[OutputSpec(**o) for o in d["outputs"]],
        params=(d.get("spec") or {}).get("params", {}) or {})
    return {"spec": spec, "charts": d.get("charts", []), "db_sources": db_sources,
            "history": d.get("history", {}), "meta": d, "instance": inst, "instances": instances}


def run_model_instances(model_id: str, conn) -> dict:
    """Run a jurisdiction-generic model across ALL its declared instances (the Fed, ECB, BoE, BoJ…),
    each resolving its own roles→series. Returns {instance_id: {history, latest, cb, ccy}} — the raw
    material for the cross-jurisdiction comparison where the DIVERGENCE is the insight."""
    d = yaml.safe_load((GRAPH_DIR / f"{model_id}.yaml").read_text())
    instances = d.get("instances") or ["US"]
    jur = _jurisdictions()
    hist = d.get("history", {})
    out = {}
    for jid in instances:
        m = _load_model(model_id, instance=jid)
        ex = Executor(_fetch_factory(conn, m["db_sources"]))
        dates = _dates(hist.get("start", "2021-01"), hist.get("end", "2026-05"), hist.get("cadence", "monthly"))
        dates = _clamp(dates, _instance_start(conn, m))
        h = ex.run_history(m["spec"], dates)
        meta = jur.get(jid, {}).get("meta", {})
        out[jid] = {"history": h, "latest": h[-1] if h else None, "dates": dates,
                    "coverage": _coverage(dates, h),
                    "cb": meta.get("central_bank", jid), "ccy": meta.get("ccy", "")}
    return {"meta": d, "charts": d.get("charts", []), "instances": out,
            "common": _common_window(out)}


def _common_window(instances: dict) -> dict:
    """The window every instance shares — the ONLY honest scope for a cross-jurisdiction claim.

    A Fed-vs-ECB comparison is a 1999+ story because the euro is 27 years old; a Fed-alone chart is a
    1954+ story. Both are true and they are different exhibits. This computes the intersection so a
    comparison can DECLARE its window rather than let the reader infer it from a line that stops.
    Also carries the coarsest cadence: comparing a daily US policy rate against a monthly UK one means
    resampling to monthly — never upsampling, which would be fabrication.
    """
    live = {j: v for j, v in instances.items() if v.get("history")}
    if not live:
        return {"instances": [], "start": None, "end": None}
    starts = [v["history"][0].as_of[:7] for v in live.values()]
    ends = [v["history"][-1].as_of[:7] for v in live.values()]
    return {"instances": sorted(live), "start": max(starts), "end": min(ends),
            "n_instances": len(live)}


def _dates(start: str, end: str, cadence: str = "monthly") -> list[str]:
    if cadence == "weekly":
        from datetime import datetime, timedelta
        d = datetime.fromisoformat(f"{start}-01" if len(start) == 7 else start)
        e = datetime.fromisoformat(f"{end}-28" if len(end) == 7 else end)
        out = []
        while d <= e:
            out.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=7)
        return out
    step = 3 if cadence == "quarterly" else 1
    (ys, ms), (ye, me) = (int(x) for x in start.split("-")), (int(x) for x in end.split("-"))
    out, y, m = [], ys, ms
    while (y, m) <= (ye, me):
        out.append(f"{y}-{m:02d}-28")
        m += step
        while m > 12:
            y, m = y + 1, m - 12
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


# A model may deliver less than it asked for: run_history skips any as-of where an input is thin
# (executor.py "honest skip, not a fabricated point"). Honest per point — INVISIBLE in aggregate,
# because nothing ever compared delivered to requested. On 2026-07-14 reaction_function asked for 65
# monthly points, got 8, and shipped a chart captioned "through the tightening cycle". Nothing
# raised. It later RECOVERED silently via backfill — nobody could tell in either direction. That is
# the whole argument for measuring it: both numbers are already in hand here and one was thrown away.
_COVERAGE_FLOOR = 0.80

# Observations a transform must consume before its first value.
_WARMUP_MONTHS = {"yoy": 12, "yoy_diff": 12, "sahm": 15, "garch_vol": 3, "momentum": 12,
                  "roll_skew": 12, "roll_kurt": 12, "realized_vol": 1, "pct_change": 1}


def _instance_start(conn, m: dict) -> str | None:
    """The earliest as-of THIS instance's inputs can support: max over inputs of (first observation +
    transform warm-up).

    `history.start` is per MODEL, and a generic model's window is authored for its first instance —
    the US. phillips_curve asks from 1948; the euro did not exist until 1999. Measured against the
    US-shaped ask, EU delivers 313/937 = 33% and the coverage gate calls it STARVED. It is not
    starved: it is complete for its jurisdiction. Clamping the ask to what the instance can supply is
    what makes coverage mean the same thing for the Fed and the ECB — otherwise the gate refuses
    exactly the generic models it exists to protect, which is the FOMC-default failure inside the tool
    built to detect it.

    Returns None when nothing is known, in which case the model's authored start stands.
    """
    firsts = []
    with conn.cursor() as cur:
        for inp in m["spec"].inputs:
            if inp.source == "derived" or not inp.series_id:
                continue
            src = m["db_sources"].get(inp.series_id)
            if src:
                cur.execute("SELECT to_char(min(timestamp), 'YYYY-MM') FROM observations "
                            "WHERE series_id=%s AND source=%s", (inp.series_id, src))
            else:
                cur.execute("SELECT to_char(min(timestamp), 'YYYY-MM') FROM observations "
                            "WHERE series_id=%s", (inp.series_id,))
            row = cur.fetchone()
            if not row or not row[0]:
                continue
            n = int(row[0][:4]) * 12 + int(row[0][5:7]) - 1 + _WARMUP_MONTHS.get(inp.transform or "none", 0)
            firsts.append(f"{n // 12:04d}-{n % 12 + 1:02d}")
    return max(firsts) if firsts else None


def _clamp(dates: list[str], start: str | None) -> list[str]:
    """Drop as-of dates before the instance can support one. Never widens — an authored start that is
    later than the data allows is a deliberate editorial choice and stands."""
    return [d for d in dates if d[:7] >= start] if start else dates


def _coverage(requested: list[str], history: list) -> dict:
    n_req, n_got = len(requested), len(history)
    ratio = (n_got / n_req) if n_req else 0.0
    return {"requested": n_req, "delivered": n_got, "ratio": ratio,
            "starved": ratio < _COVERAGE_FLOOR,
            "first": history[0].as_of if history else None,
            "last": history[-1].as_of if history else None,
            "asked_from": requested[0] if requested else None}


def run_model(model_id: str, conn, instance: str | None = None) -> dict:
    m = _load_model(model_id, instance=instance)
    ex = Executor(_fetch_factory(conn, m["db_sources"]))
    dates = _dates(m["history"].get("start", "2021-01"), m["history"].get("end", "2026-05"),
                   m["history"].get("cadence", "monthly"))
    dates = _clamp(dates, _instance_start(conn, m))     # ask this instance for what it can give
    history = ex.run_history(m["spec"], dates)
    return {**m, "history": history, "latest": history[-1] if history else None,
            "dates": dates, "coverage": _coverage(dates, history)}


def render_selected(items: list, out_path: str, *, suptitle: str | None = None) -> str:
    """Compose one figure from selected charts that may span models: items = [(chart_spec, history)]."""
    n = len(items)
    ncol = 2 if n > 1 else 1
    nrow = (n + ncol - 1) // ncol
    fig = plt.figure(figsize=(8.2 * ncol, 5.0 * nrow))
    for i, (chart, history) in enumerate(items):
        ax = fig.add_subplot(nrow, ncol, i + 1)
        from_graph.render_chart(ax, chart, history, fig=fig)
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
