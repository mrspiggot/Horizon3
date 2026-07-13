"""Bridge: a persona's executed models → the raw material an infographic is built from.

Returns provenance-traced ``NumberObject``s (every executed output + input level, keyed
``model_id.field``), the author's salient ordering (parsed from the persona's summary_template
placeholders), the hero charts as base64 PNGs, and the papers/data-sources for the provenance
footer. Reuses ``graph_corpus.run_model`` and ``from_graph.render_chart`` — no new number logic.
"""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import yaml                      # noqa: E402

from .. import from_graph, graph_corpus  # noqa: E402
from .schema import NumberObject          # noqa: E402

GRAPH_DIR = Path(__file__).resolve().parents[2] / "catalog" / "graph"
_PLACE = re.compile(r"\{([a-z0-9_]+)\.([a-z0-9_]+)\}")


_EXPAND = {"tp": "term-premium", "oas": "OAS", "ig": "IG", "hy": "HY", "em": "EM", "gz": "GZ",
           "vrp": "variance-risk-premium", "ebp": "excess bond premium", "pd": "default prob",
           "cpi": "CPI", "pce": "PCE", "rf": "risk-free", "erp": "ERP", "nfci": "NFCI",
           "sahm": "Sahm", "def": "default", "gdp": "GDP"}


def humanise(field: str) -> str:
    f = re.sub(r"_(pct|pp|bp|prob|pts|z|exante|expost|usd)$", "", field)
    toks = [_EXPAND.get(t, t) for t in f.split("_") if t]
    s = " ".join(toks).strip()
    return s[:1].upper() + s[1:] if s else field


def _norm_unit(u: str) -> tuple[str, str]:
    """(display_unit, fmt) — $ goes into the fmt (prefix) so the gate still verifies core==fmt(val)."""
    u = (u or "").strip()
    if "$" in u or u == "USD":              # "$", "$/bbl", "USD" → $ prefix
        return "", "${:,.2f}"
    if u == "%":
        return "%", "{:.2f}"
    if u in ("pp", "bp", "pts"):
        return u, "{:+.2f}"
    if u in ("sigma", "σ", "z", "z-score", "zscore"):
        return "σ", "{:+.2f}"
    if u in ("0..1", "prob", "share", "0/1"):
        return "", "{:.0%}"
    if u in ("x", "×", "ratio"):
        return "×", "{:.1f}"
    if u in ("index", "pt", "pts", "points"):
        return "", "{:.1f}"
    return u, "{:.2f}"


def persona_material(persona_id: str, conn) -> dict:
    p = yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"][persona_id]
    runs: dict[str, dict] = {}
    numbers: dict[str, NumberObject] = {}
    papers, sources = set(), set()
    for mid in p["models"]:
        run = graph_corpus.run_model(mid, conn)
        runs[mid] = run
        latest = run["latest"]
        if latest is None:
            continue
        as_of = str(latest.as_of)[:10]
        meta = run.get("meta") or {}
        outs = {o["name"]: o for o in (meta.get("outputs") or [])}
        sp = meta.get("spec")
        comp = (sp.get("equations", "") if isinstance(sp, dict) else getattr(sp, "equations", "")) \
            or meta.get("method_note", "") or ""
        comp = " ".join(str(comp).split())[:140]
        for name, val in latest.outputs.items():
            if not isinstance(val, (int, float)):
                continue
            unit, fmt = _norm_unit(outs.get(name, {}).get("unit", ""))
            numbers[f"{mid}.{name}"] = NumberObject(
                name=f"{mid}.{name}", value=float(val), unit=unit, fmt=fmt,
                source=f"{mid}.{name}", source_computation=comp, as_of=as_of)
        for iid, obj in latest.inputs.items():
            lvl = getattr(obj, "level", obj)
            key = f"{mid}.{iid}"
            if isinstance(lvl, (int, float)) and key not in numbers:   # OUTPUT wins on a name collision
                numbers[key] = NumberObject(
                    name=key, value=float(lvl), unit="", fmt="{:.2f}",
                    source=key, source_computation="input level", as_of=as_of)
        papers.update(meta.get("grounded_in") or [])
        sources.update(i["db_source"] for i in (meta.get("inputs") or []) if i.get("db_source"))
    salient: list[str] = []
    for m in _PLACE.finditer(p.get("summary_template", "")):
        k = f"{m.group(1)}.{m.group(2)}"
        if k in numbers and k not in salient:
            salient.append(k)
    return {"id": persona_id, "p": p, "runs": runs, "numbers": numbers, "salient": salient,
            "papers": sorted(papers), "sources": sorted(sources),
            "as_of": max((n.as_of for n in numbers.values()), default="")}


def chart_png(run: dict, chart_id: str, figsize=(6.4, 3.9)) -> str | None:
    chart = next((c for c in (run.get("charts") or []) if c.get("id") == chart_id), None)
    if chart is None or not run.get("history"):
        return None
    fig, ax = plt.subplots(figsize=figsize, dpi=150)
    try:
        from_graph.render_chart(ax, chart, run["history"], fig=fig)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None
    finally:
        plt.close(fig)


def first_sentence(text: str) -> str:
    t = " ".join((text or "").split())
    i = t.find(". ")
    return (t[:i + 1] if i > 0 else t)[:240]
