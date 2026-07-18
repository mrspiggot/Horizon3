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
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import yaml                      # noqa: E402

from .. import from_graph, graph_corpus  # noqa: E402
from ..selector.graph import select_models  # noqa: E402
from ..studio.families import decomposition as _dc  # noqa: E402
from ..studio.families import relationship as _rel  # noqa: E402
from ..studio.families import surface as _surf      # noqa: E402
from ..studio.families import timeseries as _ts     # noqa: E402
from .schema import NumberObject                     # noqa: E402

# authored data_contract.kind → the polished ACS structure-family renderer.
#
# Anything absent here falls through to the raw charts.py primitives, whose defaults were never
# meant to ship. Until 2026-07-16 this covered 5 of 9 kinds: `series` (45 charts) and `gap_series`
# (22) matched nothing, so 96 of 115 authored charts — 83% — rendered in stock matplotlib beside a
# polished dashboard. All eight editorial reviews independently reported that split as their chart
# complaint. It was this dict.
#
# Still unrouted: `named_values` (26) and `curve_snapshot` (3). named_values are the per-model
# "today" snapshots that writer.py's _is_snapshot drops before the writer ever sees them (see
# defects.yaml: wrong-chart-for-the-question) — routing them is pointless until that suppression is
# fixed. curve_snapshot is next; two of them are the best exhibits in the batch per the reviews.
_FAMILY = {"decomposition": "decomp", "stacked": "decomp",
           "scatter": "rel", "pearson": "rel", "heatmap": "surf",
           "series": "ts", "gap_series": "ts"}


def _blank_meta(spec) -> None:
    """Embed mode: drop the family chart's own subtitle/source/footer — the infographic frames it."""
    for f in ("subtitle", "source", "footer"):
        if hasattr(spec, f):
            setattr(spec, f, "")


def _refuse_if_starved(run: dict, chart_id: str) -> None:
    """The coverage gate, on the family path too.

    It was written into from_graph.render_chart — the RAW path — and then _FAMILY was widened so that
    73% of charts stopped going through the raw path. The gate got WEAKER as the rendering got better,
    and nothing said so: a full-estate sweep showed risk_premia_ff89 drawing 3 charts through the
    family at 19% coverage while the gate caught only the 4th, which happened to fall back to raw.
    A gate guarding a quarter of the surface is not a gate.

    Both render paths now refuse the same way, for the same reason: a starved window drawn as though
    it were a deliberate choice is the defect (7/8 reviews). The gap itself is an acquisition task —
    scripts/data_fitness.py turns the named reason into a plan.
    """
    cov = run.get("coverage") or {}
    if cov.get("starved"):
        raise ValueError(
            f"DATA STARVED — refusing to draw {chart_id!r}: asked for {cov['requested']} as-of dates "
            f"from {cov['asked_from']}, the executor delivered {cov['delivered']} "
            f"({cov['ratio']:.0%}, {cov['first']} → {cov['last']}). This chart would read as a "
            f"deliberate window. Run `python scripts/data_fitness.py` for the binding series.")


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
    # Gate BEFORE the try below — its `except Exception: return None` would turn a starvation refusal
    # into a silent fallback to the raw renderer, i.e. the starved chart ships anyway, unpolished.
    _refuse_if_starved(run, chart_id)
    model = run.get("meta") or {}
    out = os.path.join(tempfile.gettempdir(), f"ais_fam_{abs(hash((model.get('model_id'), chart_id)))}.png")
    try:
        if fam == "decomp":
            built = _dc.spec_from_run(model, run, chart_id)
            if not built:
                return None, insight
            df, spec = built; _blank_meta(spec); _dc.render_decomposition(df, spec, out)
        elif fam == "ts":
            built = _ts.spec_from_run(model, run, chart_id)
            if not built:
                return None, insight
            df, spec = built; _blank_meta(spec); _ts.render_timeseries(df, spec, out)
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


_UNKNOWN_UNITS: set[str] = set()


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
    if not u:
        return "", "{:.2f}"
    # AN UNKNOWN UNIT MUST NOT BE GLUED TO THE DIGITS. `NumberObject.rendered()` is f"{s}{unit}", so
    # the old `return u, "{:.2f}"` fallthrough printed the catalog's raw yaml string against the
    # number: "1.05V/U", "0.05rate", "0.23x1000", "0.40net fraction", "0.35β1". "1.07V/U" reached a
    # reader in the economist_forecaster article — the one that scored 7.2, the joint highest.
    #
    # 9 of the catalog's 19 authored units have no branch above. Only `V/U` was reachable until
    # `salient` was widened to every executed number (:291), which took it from 1 to 6. A space is
    # the minimum honest rendering and keeps the value citable; refusing instead would drop the
    # number from the menu, which is the silent loss this whole file keeps relearning not to do.
    #
    # It is still a catalog defect: "rate", "x1000" and "net fraction" are notes, not units. Say so
    # once per unit — a fallthrough nobody hears is how "1.07V/U" shipped.
    if u not in _UNKNOWN_UNITS:
        _UNKNOWN_UNITS.add(u)
        print(f"UNIT NOT NORMALISED — {u!r} has no branch in _norm_unit; rendering as '<value> {u}'. "
              f"Add a branch or fix the catalog's `unit:`.", file=sys.stderr)
    return f" {u}", "{:.2f}"


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


# ── the dashboard, derived from the FINISHED article (C) ──────────────────────────────────────────
# The infographic used to be built from the hand-typed `summary_template` and the raw salient menu,
# never from the prose the writer redrafted — so its thesis, its "THE READ" line and its tiles were
# fossils of a prior draft in every regeneration (the CB dashboard said "CPI elevated, rising" while
# the body argued inflation was low and falling). These derive the same three things from the article
# when it is supplied, and fall back to the template only when it is not.
def _dimensioned_keys(numbers: dict, keys) -> list[str]:
    return [k for k in keys if k in numbers
            and any(c in "%$×σ°" or c.isalpha() for c in numbers[k].rendered())]


def dashboard_thesis(mat: dict, article: dict | None) -> str:
    if article and article.get("exec_summary"):
        s = first_sentence(article["exec_summary"])
        if s:
            return s
    return first_sentence(mat["p"].get("summary_template", ""))


def dashboard_read(mat: dict, article: dict | None) -> str:
    if article and article.get("exec_summary"):
        r = reader_takeaway(article["exec_summary"])
        if r:
            return r
    return reader_takeaway(mat["p"].get("summary_template", ""))


def dashboard_tile_keys(mat: dict, article: dict | None, n: int = 4, floor: int = 3) -> list[str]:
    """The KPI tiles: the canonical numbers the PROSE actually cited, so no tile can show a figure the
    body never used; back-filled from the salient menu only to reach the floor."""
    numbers, canon = mat["numbers"], mat.get("canon", {})
    keys: list[str] = []
    for k in (article or {}).get("cited_keys", []) or []:
        rep = canon.get(k, k)
        if rep in numbers and rep not in keys:
            keys.append(rep)
    keys = _dimensioned_keys(numbers, keys)
    for k in mat["salient"]:                              # back-fill to the floor, in salient order
        if len(keys) >= max(n, floor):
            break
        if k not in keys and _dimensioned_keys(numbers, [k]):
            keys.append(k)
    return keys[:n]


def _concept_registry(numbers: dict, meanings: dict, *, template_keys=(), runs=None
                      ) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Group executed numbers by CONCEPT so ONE value represents each everywhere (D).

    Two models can emit the same concept — `implied_vol_pct` from both variance_risk_premium and
    garch_volatility, an all-in cost from two funding models. Keyed `model_id.field` they look
    distinct, so the prose, the tiles, and the template each pick a different one and the article
    shows 15.57 in one place and 16.73 in another. Same concept ⇔ SAME UNIT and (same humanised field
    OR same meaning clause); the unit gate stops two different quantities merging on a coincidental
    word. Returns (concepts, canon): concepts maps a stable concept id → its member keys; canon maps
    every member key → the ONE representative every surface should cite.
    """
    runs = runs or {}
    parent = {k: k for k in numbers}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_field: dict[str, str] = {}
    by_meaning: dict[str, str] = {}
    for k in numbers:
        field, unit = k.split(".", 1)[1], (numbers[k].unit or "")
        fsig = f"{humanise(field).lower()}|{unit}"
        union(k, by_field.setdefault(fsig, k))
        mcl = clean_meaning(meanings.get(k, "") or "").lower().strip()
        if len(mcl) >= 6:                                  # a clause specific enough to trust as identity
            union(k, by_meaning.setdefault(f"{mcl}|{unit}", k))

    # Fuzzy cross-model identity: two same-unit numbers whose meaning clauses strongly overlap are one
    # concept even when field names AND clauses differ — funding_quality.ig_all_in_pct ("all-in IG
    # funding cost") ≡ funding_cost.all_in_pct ("all-in fixed IG funding cost"), the 5.86-vs-5.05 that
    # survived three review rounds. The threshold sits ABOVE the IG-vs-HY case (one differing token,
    # ~0.6) so genuinely distinct quantities stay apart; every merge is logged for the human read.
    _STOP = {"the", "of", "and", "for", "its", "per", "vs", "versus"}

    def _content(key: str) -> set[str]:
        # the leading meaning clause, NOT length-truncated (clean_meaning caps at 26 chars for display,
        # which would drop the very words that establish identity — "…funding cost").
        m = re.split(r"[—;(]", (meanings.get(key, "") or "").lower(), maxsplit=1)[0]
        return {w for w in re.findall(r"[a-z][a-z-]+", m) if w not in _STOP}

    content = {k: (_content(k), numbers[k].unit or "") for k in numbers}
    ks = list(numbers)
    for i in range(len(ks)):
        ti, ui = content[ks[i]]
        if len(ti) < 2:
            continue
        for j in range(i + 1, len(ks)):
            tj, uj = content[ks[j]]
            if ui != uj or len(tj) < 2:
                continue
            inter = ti & tj
            if len(inter) >= 2 and len(inter) / len(ti | tj) >= 0.75:
                union(ks[i], ks[j])

    groups: dict[str, list[str]] = {}
    for k in numbers:
        groups.setdefault(find(k), []).append(k)

    tset = set(template_keys)

    def _score(k: str) -> tuple:
        # canonical preference: a template-cited number (the human's explicit pick) wins; then the
        # concept's "home" model (its id/name carries the concept noun); then the longest history.
        mid, field = k.split(".", 1)
        meta = (runs.get(mid) or {}).get("meta") or {}
        name = (meta.get("name") or "").lower()
        nouns = [w for w in humanise(field).lower().split() if len(w) > 3]
        home = any(w in mid.lower() or w in name for w in nouns)
        hist = len((runs.get(mid) or {}).get("history") or [])
        return (k in tset, home, hist)

    concepts: dict[str, list[str]] = {}
    canon: dict[str, str] = {}
    for members in groups.values():
        rep = sorted(members, key=lambda k: (_score(k), k))[-1]
        concepts[min(members)] = members
        for k in members:
            canon[k] = rep
    return concepts, canon


_MATERIAL_CACHE: dict[str, dict] = {}


def persona_material(persona_id: str, conn, *, use_cache: bool = True, select: bool = True) -> dict:
    """Executed material for a persona. Process-level memoised by persona_id (the data is fixed for a
    run) so multi-family harnesses don't re-execute every model four times; pass use_cache=False to
    force a fresh execution.

    `select` runs §06 role 2: the models come from a query over the PROVEN executable spine rather
    than from the hand-typed list in personas.yaml. That list stays as the floor — if selection
    produces nothing usable it is used, loudly. Pass select=False to pin the hardcoded set (harnesses
    that compare renderings need the models held still).
    """
    if use_cache and persona_id in _MATERIAL_CACHE:
        return _MATERIAL_CACHE[persona_id]
    p = yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"][persona_id]
    model_ids, why = list(p["models"]), {}
    if select:
        try:
            sel = select_models(persona_id, p.get("decision", ""), list(p["models"]))
            model_ids, why = sel["selected"], sel.get("reasons", {})
            added = [m for m in model_ids if m not in p["models"]]
            dropped = [m for m in p["models"] if m not in model_ids]
            print(f"ROLE 2 — {persona_id}: {len(model_ids)} models"
                  + (f" | +{', '.join(added)}" if added else "")
                  + (f" | -{', '.join(dropped)}" if dropped else " | (the hardcoded set)"))
        except Exception as exc:
            # Selection is an improvement, not a dependency. If the spine is unseeded or Neo4j is
            # down, the article must still be written from the hand-authored list — but never
            # silently, or a degraded run looks exactly like a healthy one.
            print(f"ROLE 2 UNAVAILABLE — {persona_id}: {type(exc).__name__}: {str(exc)[:80]}; "
                  f"using the hardcoded models", file=sys.stderr)
    runs: dict[str, dict] = {}
    numbers: dict[str, NumberObject] = {}
    meanings: dict[str, str] = {}
    model_names: list[str] = []
    papers, sources = set(), set()
    for mid in model_ids:
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
    # THE CITABLE MENU. `salient` is what `_citable` turns into the {n} tokens — the ONLY numbers the
    # writer is allowed to put in front of a reader.
    #
    # It used to be exactly the placeholders in `summary_template`: a hand-typed YAML string whose job
    # is to render a one-line summary. It was never meant to gate the article's evidence, and it did.
    # On 2026-07-17 every article's figure count equalled its persona's placeholder count — 9/9 for
    # the central banker, 8/8 for the vol trader, 4 for the commodity analyst, which is why that piece
    # cited 3 figures in 1,743 words and every reviewer called it thin. Role 2 then handed the
    # commodity analyst 6 models and 26 more executed numbers, and the menu stayed at 3: the models
    # ran, produced their outputs, and the writer was forbidden to mention them.
    #
    # The template's picks LEAD, because they encode a human's judgement about which number matters
    # most for this decision, and that judgement is worth keeping. Everything else the selected models
    # actually produced follows, and `_citable`'s limit caps the whole thing. A hand-typed list may
    # order the evidence; it may not be the evidence.
    # ── one concept → one citable number (D) ─────────────────────────────────────────────────────
    # Collapse same-concept duplicates BEFORE building the menu, so the writer, the tiles and the
    # narrator are each offered exactly one {n} per concept — the prose can no longer cite two
    # implied-vols, and a tile can no longer disagree with the body. `numbers` keeps every key (the
    # gate and provenance still resolve every source); only the citable ORDER is deduped.
    template_keys = {f"{m.group(1)}.{m.group(2)}" for m in _PLACE.finditer(p.get("summary_template", ""))}
    concepts, canon = _concept_registry(numbers, meanings, template_keys=template_keys, runs=runs)
    for cid, members in concepts.items():
        if len(members) > 1:
            print(f"CONCEPT — {persona_id}: {' = '.join(members)} → cite {canon[members[0]]}", file=sys.stderr)

    salient: list[str] = []
    seen_concepts: set[str] = set()

    def _push(k: str) -> None:
        rep = canon.get(k, k)
        if rep in numbers and rep not in seen_concepts:
            seen_concepts.add(rep)
            salient.append(rep)                            # cite the canonical member, not the alias

    for m in _PLACE.finditer(p.get("summary_template", "")):   # the template's picks still LEAD the order
        _push(f"{m.group(1)}.{m.group(2)}")
    for k in numbers:
        _push(k)
    source_labels = sorted({_SOURCE_LABEL.get(s, s) for s in sources})
    # `p["models"]` must be the models we ACTUALLY RAN, not the YAML's list — everything downstream
    # (build_brief, the exhibit contract, the data-window firewall) iterates it, so leaving the
    # hardcoded list here would compute a selection and then quietly ignore it.
    mat = {"id": persona_id, "p": {**p, "models": model_ids}, "runs": runs, "numbers": numbers,
           "meanings": meanings, "selection_why": why, "concepts": concepts, "canon": canon,
           "salient": salient, "papers": sorted(papers), "sources": sorted(sources),
           "source_labels": source_labels, "model_names": model_names,
           "as_of": max((n.as_of for n in numbers.values()), default="")}
    if use_cache:
        _MATERIAL_CACHE[persona_id] = mat
    return mat


def chart_png(run: dict, chart_id: str, figsize=(6.4, 3.9)) -> str | None:
    chart = next((c for c in (run.get("charts") or []) if c.get("id") == chart_id), None)
    if chart is None or not run.get("history"):
        return None
    fig, ax = plt.subplots(figsize=figsize, dpi=150)
    try:
        from_graph.render_chart(ax, chart, run["history"], fig=fig, coverage=run.get("coverage"))
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:
        # A refusal that nobody hears is not a gate. This bare except returning None is why a chart
        # could vanish, or fall back to the raw renderer, with no trace — the same silence that let
        # an 8-of-65 window ship as though it were a choice. Every refusal is now named on stderr,
        # and a coverage refusal is re-raised: the article build must FAIL rather than quietly omit
        # the exhibit its prose is about to describe.
        print(f"CHART REFUSED — {chart_id!r}: {exc}", file=sys.stderr)
        if isinstance(exc, ValueError) and "DATA STARVED" in str(exc):
            raise
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
