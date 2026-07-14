"""The full-article writer — a ~1000–1200-word feature, grounded in the models, anti-slop by construction.

Where `article.build_gist` writes one firewall-guarded paragraph, this writes the whole piece: a
standfirst that FORESHADOWS what the reader will learn, 4–6 body sections that weave the persona's whole
model set (each anchored to a chart), and a close that sits with the genuine open risk. Every number is
still authored by execution — the LLM cites values only by {token}; the renderer injects the verified
`NumberObject.rendered()`; any figure that matches no executed value is caught and rewritten.

The quality bar is FT / Economist / WSJ, and the explicit anti-pattern is StoryScope (arXiv 2604.03136):
AI prose over-explains and moralizes, tells tidy single-track stories, stays vague instead of naming
episodes, writes as if no one is watching, forces tidy resolution, over-writes the senses. Three layers
push against that: the StoryScope rules live in the prompts, a deterministic `_slop_lint` catches the
worst tells, and an LLM editor scored on the StoryScope checklist runs a bounded revise loop.
"""
from __future__ import annotations

import base64
import difflib
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from .article import FAMILY, _fill_template
from .illustration import vangogh
from .infographic.agentic import _citable, _tokenize
from .infographic.families import decision_brief
from .infographic.from_persona import chart_png, chart_png_family, decisive, persona_material
from .infographic.gate import _LEAK
from .studio.llm import get_llm

_TOKLEFT = re.compile(r"\{n\d+\}")


def _invoke(llm, prompt: str, tries: int = 3):
    """Invoke a structured-output LLM, retrying on the intermittent parse failure where the model
    serializes a nested list as a string (a known .with_structured_output flake on long outputs)."""
    last = None
    for _ in range(tries):
        try:
            return llm.invoke(prompt)
        except Exception as exc:                            # ValidationError / parse error → re-ask
            last = exc
    raise last

# the worst AI-slop tells (StoryScope + the usual LLM crutches) — a deterministic pre-filter before the
# LLM critic. Widened from gate._HEDGE. Matched case-insensitively over the filled prose.
_SLOP = re.compile(
    r"\b(the (?:key )?takeaway|the lesson (?:here )?is|in conclusion|to sum up|it'?s worth noting|"
    r"at the end of the day|in a world where|one reading|it is important to note|needs? no introduction|"
    r"delve|tapestry|testament to|ever-evolving|navigat\w+ the complexit|in today'?s|"
    r"when it comes to|the bottom line|make no mistake|that said,? it'?s clear|"
    r"paints? a picture|speaks? volumes|the reality is|ultimately,|"
    # meta-scaffolding: narrating the article's own machinery instead of writing it (a clumsy AI tell —
    # address the reader about the SUBJECT, never describe 'this piece' or announce 'you will see')
    r"you will see|we will see|as we(?:'| wi)ll see|this piece|this article|the charts that follow|"
    r"the pivot of this|in the pages that follow|read on\b|as this piece|the sections that follow)\b",
    re.I)


# ── schemas ──────────────────────────────────────────────────────────────────────────────────────
class SectionPlan(BaseModel):
    heading: str = Field(description="a short, specific section heading (not generic)")
    thesis: str = Field(description="the single point this section makes, in one sentence")
    model_id: str = Field(description="which model this section is grounded in")
    chart_ids: list[str] = Field(default_factory=list, description="0-2 chart ids (exact) that illustrate this section")
    token_ids: list[str] = Field(default_factory=list, description="the {n} tokens whose figures this section will cite")


class Outline(BaseModel):
    headline: str = Field(description="the article headline — keep or sharpen the given title; number-free")
    standfirst: str = Field(description="30-40 word standfirst that FORESHADOWS what the reader will learn "
                                        "without giving away the conclusion; may cite one {n} token")
    pivot: str = Field(description="the SINGLE mechanism the whole article turns on, to flag up front so "
                                   "the piece flows (e.g. 'the Gilchrist-Zakrajšek decomposition: is the "
                                   "spread paying you for default risk, or for risk appetite?')")
    sections: list[SectionPlan] = Field(description="4-6 sections forming a narrative arc that WEAVES the models")
    open_close: str = Field(description="the unresolved risk/tension the piece should end on — NOT a tidy bow")


class SectionDraft(BaseModel):
    heading: str
    prose: str = Field(description="the section body, flowing paragraphs; cite figures ONLY as {n} tokens")
    chart_ids: list[str] = Field(default_factory=list)


class Article(BaseModel):
    standfirst: str
    exec_summary: str = Field(description="the NARRATIVE executive summary — ~160-240 words of prose that "
                              "answers 'why should I read this?': an extended foreshadow that names the "
                              "article's central PIVOT up front, tells the reader what they will learn, and "
                              "DEFINES each key term/abbreviation once on first use (e.g. 'option-adjusted "
                              "spread, or OAS'). It sets up — and hands off to — the visual summary (the "
                              "infographic) that follows it. Cite figures only as {n} tokens.")
    sections: list[SectionDraft]


class Critique(BaseModel):
    ok: bool | None = None
    defects: list[str] = Field(default_factory=list,
                               description="concrete StoryScope/editorial failures: over-explaining or "
                               "moralizing, a tidy bow, vagueness where an episode should be named, no "
                               "foreshadow, purple/overwritten prose, generic filler, a weak lede")
    fixes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _derive(self):
        if self.ok is None:
            self.ok = not self.defects
        return self


# ── the brief ────────────────────────────────────────────────────────────────────────────────────
def _active_says(meta: dict, latest) -> list[str]:
    """The interpretations whose `when` guard is TRUE on the latest outputs — the model's live regime call."""
    if latest is None:
        return []
    out = dict(getattr(latest, "outputs", {}) or {})
    says = []
    for interp in (meta.get("interpretations") or []):
        when = interp.get("when")
        try:
            if when and eval(when, {"__builtins__": {}}, out):    # noqa: S307 — trusted catalog exprs, no builtins
                says.append(" ".join(str(interp.get("says", "")).split()))
        except Exception:
            continue
    return says


def _is_snapshot(c: dict) -> bool:
    """A static 'today' bar / named-values chart — redundant when a time series of the same data exists
    (the series shows the snapshot AND its change; the bar only the snapshot)."""
    dc = c.get("data_contract", {}) or {}
    return dc.get("kind") in {"named_values", "bar"} or c.get("chart_type") in {"bar", "named_values"}


def build_brief(mat: dict, *, limit: int = 24) -> dict:
    """Everything the planner/writer sees: the token menu, and per model its name, grounding, method,
    outputs, chart insights, and live regime call. Plus a chart index for id resolution."""
    toks, menu = _citable(mat, limit=limit)
    models, chart_index = [], {}
    for mid in mat["p"].get("models", []):
        run = mat["runs"].get(mid) or {}
        meta = run.get("meta") or {}
        if not meta:
            continue
        sp = meta.get("spec") or {}
        equations = sp.get("equations", "") if isinstance(sp, dict) else ""
        raw = run.get("charts") or []
        rich = [c for c in raw if not _is_snapshot(c)]
        keep = rich if rich else raw                       # keep the static snapshot only if nothing richer
        charts = []
        for c in keep:
            cid, ins = c.get("id", ""), " ".join((c.get("insight") or "").split())
            if cid:
                charts.append((cid, ins))
                chart_index[cid] = {"model_id": mid, "insight": ins}
        outs = "; ".join(f"{o['name']} ({o.get('unit','')}) — {o.get('meaning','')}"
                         for o in (meta.get("outputs") or []))
        models.append({
            "id": mid, "name": meta.get("name", mid),
            "grounded_in": ", ".join(meta.get("grounded_in") or []),
            "method": meta.get("method_note", "") or equations,
            "outputs": outs, "charts": charts,
            "regime": _active_says(meta, run.get("latest")),
        })
    return {"mat": mat, "toks": toks, "menu": menu, "models": models,
            "chart_index": chart_index, "papers": mat.get("papers", []), "as_of": mat.get("as_of", "")}


def _brief_text(brief: dict) -> str:
    lines = ["THE EVIDENCE (every figure is executed on real data; cite ONLY via the {n} tokens):", ""]
    lines.append("Citable figures:")
    lines.append(brief["menu"])
    lines.append("")
    for m in brief["models"]:
        lines.append(f"■ MODEL: {m['name']}  [grounded in: {m['grounded_in'] or 'n/a'}]")
        if m["method"]:
            lines.append(f"   method: {m['method']}")
        if m["outputs"]:
            lines.append(f"   outputs: {m['outputs']}")
        for cid, ins in m["charts"]:
            lines.append(f"   chart «{cid}» — {ins}")
        for s in m["regime"]:
            lines.append(f"   ► LIVE REGIME CALL: {s}")
        lines.append("")
    return "\n".join(lines)


# ── the StoryScope voice (shared by planner + writer) ──────────────────────────────────────────────
_VOICE = (
    "Write to the standard of the Financial Times, The Economist or the Wall Street Journal — proper "
    "journalism, not AI filler. Heed these hard rules (they are the difference between a real piece and "
    "generated slop):\n"
    "  • INFER, don't explain. Never state the moral or 'the takeaway'; never tell the reader what to "
    "think. Lay out the evidence and trust the reader to draw the conclusion.\n"
    "  • FORESHADOW then delay. Open with a hook that promises what the reader will understand by the "
    "end; do not resolve it in the first paragraph. Build tension across the piece.\n"
    "  • Name the SPECIFIC episodes the data shows (2008, 2011, 2020, 2022, the taper tantrum, COVID) — "
    "specificity is the mark of a human writer; vague allusion is the mark of a machine.\n"
    "  • Address the reader where it earns its place ('you are being paid…'). Do not write as if no one "
    "is watching.\n"
    "  • End on the genuine unresolved risk, NOT a tidy bow. Sit with the ambiguity.\n"
    "  • Plain and concrete over ornate. No purple metaphor, no bodily/sensory overwriting, no throat-"
    "clearing ('it is worth noting', 'in today's market', 'make no mistake').\n"
    "  • CITE FIGURES ONLY as the {n} tokens provided, written exactly. Never type, invent, round, or "
    "derive a number of your own.")


def plan_arc(brief: dict, feedback: str = "") -> Outline:
    p = brief["mat"]["p"]
    llm = get_llm(max_tokens=4096).with_structured_output(Outline)
    prompt = (
        f"You are the section editor planning a ~1000-1200 word feature for a {p['name']}. "
        f"The decision it informs: {p.get('decision','')}. Working title: \"{p['title']}\".\n\n"
        f"{_brief_text(brief)}\n\n"
        "First decide the PIVOT — the single mechanism the whole piece turns on — and plan for it to be "
        "flagged UP FRONT (in the standfirst and the executive summary) so the article flows: tell the "
        "reader what you are going to tell them, then tell them. Then plan the article as a NARRATIVE ARC "
        "that WEAVES these models into one thesis — foreshadow, develop across 4-6 sections, turn on the "
        "sharpest finding, end on the open risk. Do NOT write one tidy section per model in list order; "
        "braid them. Assign each section the exact chart id(s) that illustrate it and the {n} tokens it "
        "will cite. CHART CHOICE MATTERS: prefer the chart that shows the most. When a point is about a "
        "CROSS-SECTION of levels (a curve, a quality ladder, a term structure), place the chart that shows "
        "BOTH the levels AND how they have moved — a now-vs-prior comparison ('now vs 3 months ago') or "
        "the cross-section through time — in preference to a lone derived spread or a single static "
        "snapshot; a snapshot that only shows today's levels is redundant with such a chart and must not "
        "displace it. One strong chart per point.\n\n" + _VOICE
        + (f"\n\nYour previous plan was rejected. Fix: {feedback}" if feedback else ""))
    return _invoke(llm, prompt)


def write_article(brief: dict, outline: Outline, feedback: str = "") -> Article:
    p = brief["mat"]["p"]
    llm = get_llm(max_tokens=8192).with_structured_output(Article)
    plan = "\n".join(
        [f"HEADLINE: {outline.headline}", f"STANDFIRST (foreshadow): {outline.standfirst}",
         f"PIVOT (flag this up front): {outline.pivot}",
         f"END ON (open risk): {outline.open_close}", "", "SECTIONS:"]
        + [f"  {i+1}. «{s.heading}» — {s.thesis}  [charts: {', '.join(s.chart_ids) or 'none'}; "
           f"cite: {', '.join(s.token_ids) or 'none'}]" for i, s in enumerate(outline.sections)])
    prompt = (
        f"You are a {p['name']} writing the full feature to the plan below. Target 1000-1200 words total.\n"
        "STRUCTURE, in order:\n"
        "  1. STANDFIRST — the sharp foreshadowing hook (given).\n"
        "  2. EXECUTIVE SUMMARY — ~160-240 words of narrative prose that earns the reader's next ten "
        "minutes. Establish the stakes and the PIVOT, and DEFINE each key term/abbreviation once on first "
        "use (e.g. 'the option-adjusted spread, or OAS', 'high yield (HY)'), using the abbreviation "
        "thereafter. Foreshadow with FLAIR, the way an FT or Economist nut-graf does — through a confident, "
        "specific claim and the tension in it, so the promise of what's coming is IMPLICIT. Do NOT recite a "
        "table of contents. FORBIDDEN, because they are the clumsy mechanical tell an editor would cut: "
        "'you will see…', 'this piece/article', 'the pivot of this piece', 'the charts that follow', "
        "'start with the…', and any sentence that narrates the article's own structure. Address the reader "
        "about the SUBJECT ('you are being paid…'), never about the document.\n"
        "  3. SECTIONS — the detail: flowing paragraphs (not bullets), each grounded in its model and "
        "interpreting its chart(s) in words. INTERPRET every chart you point at — say what the reader "
        "should see in it and why it matters; never name a chart without reading it.\n\n"
        f"{_brief_text(brief)}\n\n{plan}\n\n" + _VOICE
        + "\n\nReturn the standfirst, the executive summary, and each section's heading + prose. Cite "
        "figures ONLY as the {n} number tokens — the ONLY braces permitted in your prose. Do NOT insert "
        "figure numbers, footnote markers, or {chart} references; to point at a chart, name it in plain "
        "words. The charts are placed for you from the plan."
        + (f"\n\nYour previous draft was rejected. Fix exactly this: {feedback}" if feedback else ""))
    return _invoke(llm, prompt)


# ── firewall + slop lint ───────────────────────────────────────────────────────────────────────────
def _finalize_text(text: str, toks: dict) -> tuple[str, str | None]:
    """Tokenise any typed value that matches an executed number, leak-check the non-token remainder, then
    substitute verified values. Returns (filled_text, leak_or_None)."""
    t = _tokenize(text, toks)
    stripped = _TOKLEFT.sub(" ", t)
    leak = _LEAK.search(stripped)
    for tok, no in toks.items():
        t = t.replace("{" + tok + "}", no.rendered())
    return t, (leak.group() if leak else None)


def _finalize_article(article: Article, toks: dict) -> tuple[str, str, str, list[SectionDraft], str | None]:
    """Fill the standfirst + exec summary + every section; return
    (full_text, standfirst, exec_summary, filled_sections, first_leak)."""
    leaks: list[str] = []
    sf, lk = _finalize_text(article.standfirst, toks)
    if lk:
        leaks.append(lk)
    ex, lk = _finalize_text(article.exec_summary, toks)
    if lk:
        leaks.append(lk)
    filled_sections = []
    for s in article.sections:
        prose, lk = _finalize_text(s.prose, toks)
        if lk:
            leaks.append(lk)
        filled_sections.append(SectionDraft(heading=s.heading, prose=prose, chart_ids=s.chart_ids))
    full = sf + "\n\n" + ex + "\n\n" + "\n\n".join(f"{s.heading}\n{s.prose}" for s in filled_sections)
    unfilled = _TOKLEFT.search(full)
    leak = (unfilled.group() if unfilled else None) or (leaks[0] if leaks else None)
    return full, sf, ex, filled_sections, leak


def _slop_lint(text: str) -> list[str]:
    return sorted({m.group(0) for m in _SLOP.finditer(text)})


# ── further reading: resolve grounding slugs → real citations (title + summary + url) ───────────────
_REG_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "registry.yaml"


@lru_cache(maxsize=1)
def _registry() -> dict:
    try:
        return {p["id"]: p for p in yaml.safe_load(_REG_PATH.read_text()).get("papers", [])}
    except Exception:
        return {}


def _resolve_papers(slugs: list[str]) -> list[dict]:
    """Grounding slugs → reader-facing citations {title, byline, summary, url} from the corpus registry."""
    reg, out = _registry(), []
    for s in slugs:
        p = reg.get(s)
        if not p:
            continue
        authors = p.get("authors") or []
        byline = (", ".join(authors[:2]) + (" et al." if len(authors) > 2 else "")) if authors else ""
        why = " ".join(str(p.get("why", "")).split())
        summary = re.split(r"(?<=[.;])\s", why)[0] if why else ""       # first sentence only
        out.append({"title": p.get("title", s), "byline": byline, "summary": summary,
                    "url": p.get("url", "")})
    return out


def _add_hyperlink(paragraph, url: str, text: str):
    """A real clickable hyperlink run (python-docx has no native helper)."""
    from docx.oxml.ns import qn
    from docx.oxml.shared import OxmlElement
    r_id = paragraph.part.relate_to(
        url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True)
    link = OxmlElement("w:hyperlink"); link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r"); rpr = OxmlElement("w:rPr")
    col = OxmlElement("w:color"); col.set(qn("w:val"), "0563C1"); rpr.append(col)
    und = OxmlElement("w:u"); und.set(qn("w:val"), "single"); rpr.append(und)
    run.append(rpr)
    t = OxmlElement("w:t"); t.text = text; run.append(t)
    link.append(run); paragraph._p.append(link)


def _strip_stray(text: str) -> str:
    """Final safety net: remove any leftover {…} marker (e.g. an invented figure ref) and tidy spacing —
    so a broken placeholder can never ship even if the writer keeps re-inserting them."""
    text = re.sub(r"\s*\{[^}]*\}", "", text)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\s+([.,;:])", r"\1", text)).strip()


def critique_article(full_text: str, title: str) -> Critique:
    llm = get_llm(max_tokens=2048).with_structured_output(Critique)
    prompt = (
        f"You are a demanding FT/Economist editor reviewing this feature draft (headline: \"{title}\"). "
        "Judge it ONLY against the marks of real journalism vs AI slop. FAIL it for any of: (1) it "
        "over-explains or moralizes / states 'the takeaway' / tells the reader what to think; (2) it "
        "resolves into a tidy bow instead of ending on a real open risk; (3) it is vague where it should "
        "name a specific episode (2008/2020/etc.); (4) the standfirst does not foreshadow, or the lede "
        "resolves everything at once; (5) purple or overwritten prose, bodily/sensory padding; (6) generic "
        "filler, throat-clearing, or a section that merely restates a number without a point; (7) the "
        "foreshadowing is PROSAIC or MECHANICAL — a table-of-contents recital ('you will see X, you will "
        "see Y'), or it narrates the article's own structure ('this piece', 'the charts that follow'), "
        "instead of the confident, implicit nut-graf foreshadowing a top paper would run. If it reads "
        "like a real desk strategist wrote it — specific, confident, arced, honest about the open risk — "
        "set ok=true. Give concrete fixes.\n\nDRAFT:\n" + full_text[:9000])
    return _invoke(llm, prompt)


# ── docx assembly ──────────────────────────────────────────────────────────────────────────────────
def _resolve_chart_id(cid: str, chart_index: dict) -> str | None:
    """Map a planner's chart reference to a real chart id — exact, else substring, else closest match.
    The planner sometimes paraphrases the id ('the funding stack' vs the exact title); recover it rather
    than silently drop the chart (which left one persona chartless)."""
    if cid in chart_index:
        return cid
    low = (cid or "").lower().strip()
    if low:
        for k in chart_index:
            kl = k.lower()
            if low == kl or (len(low) > 6 and (low in kl or kl in low)):
                return k
    m = difflib.get_close_matches(cid, list(chart_index), n=1, cutoff=0.55)
    return m[0] if m else None


def _render_charts(brief: dict, chart_ids: list[str], out_dir: Path) -> dict[str, tuple[Path, str]]:
    """Render each referenced chart once → {chart_id: (png_path, caption)}."""
    runs = brief["mat"]["runs"]
    out: dict[str, tuple[Path, str]] = {}
    for i, cid in enumerate(dict.fromkeys(chart_ids)):
        info = brief["chart_index"].get(cid)
        if not info:
            continue
        run = runs.get(info["model_id"]) or {}
        b64, cap = chart_png_family(run, cid)
        if not b64:
            b64 = chart_png(run, cid)
            cap = decisive(info.get("insight", "") or cid)
        if b64:
            pth = out_dir / f"chart_{i}.png"
            pth.write_bytes(base64.b64decode(b64))
            out[cid] = (pth, (cap or info.get("insight", ""))[:160])
    return out


def _assemble_docx(path: Path, p: dict, mat: dict, headline: str, standfirst: str, exec_summary: str,
                   sections: list[SectionDraft], charts: dict, ill_png: Path, infog_png: Path | None) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt

    def _fig(png: Path, caption: str = "", width: float = 6.5) -> None:
        doc.add_picture(str(png), width=Inches(width))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        if caption:
            c = doc.add_paragraph(caption)
            try:
                c.style = doc.styles["Caption"]
            except KeyError:
                pass
            c.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc = Document()
    doc.add_heading(headline, level=0)
    sf = doc.add_paragraph()
    r = sf.add_run(standfirst); r.italic = True; r.font.size = Pt(13)
    dl = doc.add_paragraph()
    dl.add_run(f"{p['name']}.  Data as of {mat.get('as_of','')}.").italic = True

    _fig(ill_png)                                          # the Van Gogh header

    # the DUAL executive summary: narrative prose, then the infographic as the visual summary
    for para in [x for x in exec_summary.split("\n") if x.strip()]:
        doc.add_paragraph(para.strip())
    if infog_png and Path(infog_png).exists():
        _fig(infog_png, "The whole picture at a glance — every reading, priced and traced.")

    for s in sections:
        doc.add_heading(s.heading, level=2)
        for para in [x for x in s.prose.split("\n") if x.strip()]:
            doc.add_paragraph(para.strip())
        for cid in s.chart_ids:
            if cid in charts:
                cp, cap = charts[cid]
                _fig(cp, cap, width=6.0)

    resolved = _resolve_papers(mat.get("papers", []))
    if resolved:
        doc.add_heading("Further reading", level=2)
        for r in resolved:
            para = doc.add_paragraph(style="List Bullet")
            if r["url"]:
                _add_hyperlink(para, r["url"], r["title"])
            else:
                para.add_run(r["title"]).bold = True
            tail = " — " + (f"{r['byline']}. " if r["byline"] else "") + (r["summary"] or "")
            para.add_run(tail)

    foot = doc.add_paragraph()
    fr = foot.add_run(f"Source: {', '.join(mat.get('source_labels', [])) or 'UMD'}. "
                      f"Models: {', '.join(mat.get('model_names', []))}. Every figure is executed on data; "
                      f"the prose is authored, the numbers are not.")
    fr.font.size = Pt(8); fr.italic = True
    doc.save(str(path))


# ── the orchestrator ───────────────────────────────────────────────────────────────────────────────
def build_article_full(persona_id: str, conn, out_dir, *, backend: str = "auto", max_iter: int = 3) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mat = persona_material(persona_id, conn)
    p = mat["p"]
    brief = build_brief(mat)
    outline = plan_arc(brief)

    def _place_charts(secs: list[SectionDraft]) -> None:
        """Chart placement is the PLANNER's call (it saw the chart index); resolve its ids (fuzzily —
        it sometimes paraphrases) and attach them to the written sections by order. The writer's own
        chart_ids are ignored. A safety net guarantees no article ships chartless."""
        ci = brief["chart_index"]
        for i, s in enumerate(secs):
            ids = outline.sections[i].chart_ids if i < len(outline.sections) else s.chart_ids
            resolved: list[str] = []
            for c in ids:
                r = _resolve_chart_id(c, ci)
                if r and r not in resolved:
                    resolved.append(r)
            s.chart_ids = resolved
        if sum(len(s.chart_ids) for s in secs) == 0 and ci:   # never chartless: spread a few
            for i, s in enumerate(secs):
                if i < len(ci):
                    s.chart_ids = [list(ci)[i]]

    feedback, reasons, crit_ok = "", [], False
    filled_sections, headline = [], outline.headline
    standfirst, exec_summary, full_text = outline.standfirst, "", ""
    for it in range(max_iter):
        article = write_article(brief, outline, feedback=feedback)
        full_text, standfirst, exec_summary, filled_sections, leak = _finalize_article(article, brief["toks"])
        slop = _slop_lint(full_text)
        stray = re.search(r"\{[^}]*\}", full_text)          # an invented figure marker / bad token
        if leak or slop or stray:
            bits = []
            if leak:
                bits.append(f"REMOVE the untraced figure '{leak}' — cite only the listed {{n}} tokens.")
            if stray:
                bits.append("REMOVE every {…} marker from the prose — do not number or footnote the "
                            "charts; name a chart in words. The only braces allowed are the number tokens.")
            if slop:
                bits.append("DELETE these AI-slop phrases and rewrite the sentence plainly: "
                            + ", ".join(f"'{s}'" for s in slop))
            feedback = " ".join(bits)
            reasons.append(f"iter{it}: {'leak ' if leak else ''}{'stray ' if stray else ''}{'slop' if slop else ''}".strip())
            continue
        crit = critique_article(full_text, headline)
        if crit.ok:
            crit_ok = True
            break
        feedback = "; ".join(crit.fixes or crit.defects)
        reasons.append(f"iter{it}: critic {len(crit.defects)} defects")

    # final safety: strip any residual marker so nothing broken ships; place charts from the plan
    standfirst = _strip_stray(standfirst)
    exec_summary = _strip_stray(exec_summary)
    for s in filled_sections:
        s.prose = _strip_stray(s.prose)
    _place_charts(filled_sections)

    # illustration (art-director from the article's own finding), infographic, charts
    finding = _fill_template(mat)
    ill_b64, ill_meta = vangogh.illustration_png(
        finding, title=p["title"], decision=p.get("decision", ""),
        cache_key=f"{persona_id}|article", backend=backend)
    ill_png = out_dir / "illustration.png"; ill_png.write_bytes(base64.b64decode(ill_b64))

    infog_png = out_dir / "infographic.png"
    fam = FAMILY.get(persona_id, decision_brief)
    try:
        fam.render_persona(persona_id, conn, str(infog_png))
    except Exception as exc:
        reasons.append(f"infographic→decision_brief: {str(exc).splitlines()[0][:70]}")
        try:
            decision_brief.render_persona(persona_id, conn, str(infog_png))
        except Exception:
            infog_png = None

    all_chart_ids = [cid for s in filled_sections for cid in s.chart_ids]
    charts = _render_charts(brief, all_chart_ids, out_dir)

    docx_path = out_dir / "article.docx"
    _assemble_docx(docx_path, p, mat, headline, standfirst, exec_summary, filled_sections, charts,
                   ill_png, infog_png)
    words = len(full_text.split())
    return {"persona": persona_id, "ok": True, "docx_path": str(docx_path), "headline": headline,
            "standfirst": standfirst, "sections": len(filled_sections), "words": words,
            "critic_ok": crit_ok, "n_charts": len(charts), "caption": ill_meta.get("caption", ""),
            "full_text": full_text, "reasons": reasons}
