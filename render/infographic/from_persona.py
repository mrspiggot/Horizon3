"""Bridge: a persona's executed models → the raw material an infographic is built from.

Returns provenance-traced ``NumberObject``s (every executed output + input level, keyed
``model_id.field``), the author's salient ordering (parsed from the persona's summary_template
placeholders), the hero charts as base64 PNGs, and the papers/data-sources for the provenance
footer. Reuses ``graph_corpus.run_model`` and ``from_graph.render_chart`` — no new number logic.
"""
from __future__ import annotations

import base64
import io
import os
import re
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import yaml                      # noqa: E402

from .. import from_graph, graph_corpus  # noqa: E402
from ..studio.families import decomposition as _dc  # noqa: E402
from ..studio.families import relationship as _rel  # noqa: E402
from ..studio.families import surface as _surf      # noqa: E402
from .schema import NumberObject                     # noqa: E402

# authored data_contract.kind → the polished ACS structure-family renderer
_FAMILY = {"decomposition": "decomp", "stacked": "decomp",
           "scatter": "rel", "pearson": "rel", "heatmap": "surf"}


def _blank_meta(spec) -> None:
    """Embed mode: drop the family chart's own subtitle/source/footer — the infographic frames it."""
    for f in ("subtitle", "source", "footer"):
        if hasattr(spec, f):
            setattr(spec, f, "")


def chart_png_family(run: dict, chart_id: str) -> tuple[str | None, str]:
    """Render a persona chart through its POLISHED ACS structure-family (decomposition / surface /
    relationship) in embed mode. Returns (base64_png, insight_caption); (None, insight) to fall back."""
    chart = next((c for c in (run.get("charts") or []) if c.get("id") == chart_id), None)
    if chart is None:
        return None, ""
    insight = " ".join((chart.get("insight") or "").split())
    fam = _FAMILY.get((chart.get("data_contract", {}) or {}).get("kind", ""))
    if not fam or not run.get("history"):
        return None, insight
    model = run.get("meta") or {}
    out = os.path.join(tempfile.gettempdir(), f"ais_fam_{abs(hash((model.get('model_id'), chart_id)))}.png")
    try:
        if fam == "decomp":
            built = _dc.spec_from_run(model, run, chart_id)
            if not built:
                return None, insight
            df, spec = built; _blank_meta(spec); _dc.render_decomposition(df, spec, out)
        elif fam == "rel":
            built = _rel.spec_from_run(model, run, chart_id)
            if not built:
                return None, insight
            df, spec = built; _blank_meta(spec); _rel.render_relationship(df, spec, out)
        else:  # surf
            built = _surf.spec_from_run(model, run, chart_id)
            if not built:
                return None, insight
            dates, mat, spec = built; _blank_meta(spec); _surf.render_surface(dates, mat, spec, out)
        b = base64.b64encode(Path(out).read_bytes()).decode()
        return b, insight
    except Exception:
        return None, insight
    finally:
        try:
            os.remove(out)
        except OSError:
            pass

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


_SOURCE_LABEL = {
    "fred": "FRED", "nyfed_acm": "NY Fed ACM term-structure model",
    "nyfed_hlw": "NY Fed (Holston–Laubach–Williams)", "fed_ebp": "Federal Reserve (GZ / EBP)",
    "boe": "Bank of England", "yahoo": "Yahoo Finance", "ecb": "ECB", "cftc": "CFTC",
}


def clean_meaning(meaning: str, fallback: str = "") -> str:
    """A short, reader-facing tile heading from an output's authored `meaning`.
    Falls back to the humanised field id when the meaning is too long to sit cleanly."""
    m = re.sub(r"\s+", " ", re.split(r"[—(;,]", meaning or "", 1)[0].strip())
    if not m:
        return fallback
    if len(m) <= 26:
        return m
    return fallback or (m[:24].rsplit(" ", 1)[0] + "…")


# hedges a real publication would never print — strip them so the read is a CALL, not a shrug
_HEDGE_PREFIX = re.compile(r"^.*?\b(reading|reads|trade|interpretation|take|models?)\b[^:]*:\s*", re.I)
_HEDGE_WORD = re.compile(
    r"\b(arguably|perhaps|somewhat|broadly|on balance|it may be(?: that)?|one could argue|"
    r"tends to|seems to|appears to)\b[,]?\s*", re.I)


def decisive(s: str) -> str:
    """Turn a hedged sentence into a declarative call (drop 'One reading:' etc.)."""
    s = _HEDGE_PREFIX.sub("", s or "").strip()
    s = _HEDGE_WORD.sub("", s).strip()
    return (s[:1].upper() + s[1:]) if s else s


def reader_takeaway(summary: str) -> str:
    """The exec summary's closing read as a DECISIVE, number-free call — no equivocation."""
    sents = re.split(r"(?<=[.!?])\s+", " ".join((summary or "").split()))
    for s in reversed(sents):
        s = s.strip()
        if s and not re.search(r"\{|\d+\.\d+|\d+\s?(?:%|pp|bp|×|σ)", s):
            return decisive(s)
    return ""


def persona_material(persona_id: str, conn) -> dict:
    p = yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"][persona_id]
    runs: dict[str, dict] = {}
    numbers: dict[str, NumberObject] = {}
    meanings: dict[str, str] = {}
    model_names: list[str] = []
    papers, sources = set(), set()
    for mid in p["models"]:
        run = graph_corpus.run_model(mid, conn)
        runs[mid] = run
        latest = run["latest"]
        if latest is None:
            continue
        as_of = str(latest.as_of)[:10]
        meta = run.get("meta") or {}
        if meta.get("name"):
            model_names.append(meta["name"])
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
            meanings[f"{mid}.{name}"] = outs.get(name, {}).get("meaning", "")
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
    source_labels = sorted({_SOURCE_LABEL.get(s, s) for s in sources})
    return {"id": persona_id, "p": p, "runs": runs, "numbers": numbers, "meanings": meanings,
            "salient": salient, "papers": sorted(papers), "sources": sorted(sources),
            "source_labels": source_labels, "model_names": model_names,
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


def hero_charts(p: dict, runs: dict, n: int = 1) -> list[tuple[str, str]]:
    """The best polished charts for a persona: family-routing charts, the author's stub picks first,
    then any other family chart across the models. Returns [(base64_png, insight_caption), …]."""
    seen: set[tuple] = set()
    candidates: list[tuple[str, str]] = []
    for mid, cid in p.get("stub_charts", []):              # author's picks first
        candidates.append((mid, cid)); seen.add((mid, cid))
    for mid in p.get("models", []):                        # then any other model chart
        for c in (runs.get(mid, {}).get("charts") or []):
            if (mid, c["id"]) not in seen:
                candidates.append((mid, c["id"])); seen.add((mid, c["id"]))
    out: list[tuple[str, str]] = []
    for mid, cid in candidates:
        if len(out) >= n:
            break
        png, cap = chart_png_family(runs.get(mid, {}), cid)
        if png:
            out.append((png, cap))
    return out


def first_sentence(text: str) -> str:
    """The first clean, number-free sentence — a reader-ready thesis opener."""
    sents = re.split(r"(?<=[.!?])\s+", " ".join((text or "").split()))
    for s in sents:
        s = s.strip()
        if s and "{" not in s and not re.search(r"\d+\.\d+|\d+\s?(?:%|pp|bp|×|σ)", s):
            return s[:240]
    return (sents[0][:240] if sents else "")
