"""The AIS agentic narration + critic layer (P2).

Lifts the infographic from "polished template" to "authored flagship": an LLM narrator writes the
thesis and the read as decisive prose, and the multimodal critic reviews the rendered pixels. The
firewall holds — the narrator may CITE numbers only by token ({n0}); the renderer injects the
verified value, and the tier-1 gate refuses any raw digit or hedge. Two-tier acceptance (PlotGen +
§12): deterministic tier-1 FIRST (numeric-equality / provenance / no-equivocation, our DOM check is
stronger than a VLM de-render), then the vision critic for layout/lexical/aesthetics.

Reuses render/studio/llm.py (get_llm, VISION_MODEL, LangSmith) — one LLM module for both subsystems.
"""
from __future__ import annotations

import base64
import io
import re

from pydantic import BaseModel, Field, model_validator

from ..studio.llm import VISION_MODEL, get_llm
from .from_persona import clean_meaning, hero_charts, humanise, persona_material
from .gate import lint_infographic
from .render_html import html_to_png, render_html
from .schema import Block, InfographicSpec, Layout, NumberObject

_TOKEN = re.compile(r"\{(n\d+)\}")
_PALETTE = ["#4C6EA8", "#D55E00", "#009E73", "#B8C4CE", "#D98A00"]
_TONES = ["mid", "up", "dn", "mid"]


class Narration(BaseModel):
    thesis: str = Field(description="ONE decisive headline sentence (the standfirst). Use the exact figures from the list. No hedging.")
    read: str = Field(description="One or two sentences — the decisive call to act on, citing the exact figures. Make a call.")


class Critique(BaseModel):
    ok: bool | None = None
    defects: list[str] = Field(default_factory=list, description="concrete rendered-page problems: overflow, collision, weak/vague copy, a hedge, an unreadable chart, a tile that doesn't fit")
    fixes: list[str] = Field(default_factory=list, description="specific fixes")

    @model_validator(mode="after")
    def _derive(self):
        if self.ok is None:
            self.ok = not self.defects
        return self


def _img_b64(path: str, max_px: int = 2000) -> str:
    from PIL import Image
    img = Image.open(path)
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _citable(mat: dict, limit: int = 8) -> tuple[dict[str, NumberObject], str]:
    """Token → NumberObject menu of the persona's salient, dimensioned executed numbers."""
    keys = [k for k in mat["salient"]
            if any(c in "%$×σ°" or c.isalpha() for c in mat["numbers"][k].rendered())][:limit]
    toks, lines = {}, []
    for i, k in enumerate(keys):
        tok = f"n{i}"
        toks[tok] = mat["numbers"][k].model_copy(update={"name": tok})
        label = clean_meaning(mat["meanings"].get(k, ""), humanise(k.split(".", 1)[1]))
        lines.append(f"  {{{tok}}}  {label} = {mat['numbers'][k].rendered()}")
    return toks, "\n".join(lines)


def narrate(mat: dict, toks: dict, menu: str, feedback: str = "") -> Narration:
    p = mat["p"]
    llm = get_llm().with_structured_output(Narration)
    prompt = (
        f"You are a {p['name']} writing for a market-research client to FT / Economist / WSJ standard. "
        f"Your decision: {p.get('decision', '')}. The piece is headlined: \"{p['title']}\".\n\n"
        f"The executed model numbers you may cite (use the token in braces — NEVER type a digit yourself):\n"
        f"{menu}\n\n"
        "Write two things:\n"
        "  THESIS — one sentence: the single decisive claim, the standfirst a strategist would open with.\n"
        "  READ  — one or two sentences: the call the reader acts on.\n\n"
        "Rules, non-negotiable:\n"
        "  • Make a CALL. No 'one reading', no 'arguably', no 'on balance', no hedging of any kind.\n"
        "  • Cite ONLY figures from the list above, written EXACTLY as shown (e.g. 14%, 0.65pp, $66.69). "
        "Do not invent, round, or restate any number that is not in the list.\n"
        "  • Specific, confident, plain — the voice of a desk strategist, not an AI assistant.\n"
        + (f"\nYour previous draft was rejected. Fix exactly this: {feedback}" if feedback else ""))
    return llm.invoke(prompt)


def _tokenize(text: str, toks: dict) -> str:
    """Convert any figure that matches an executed value into its {token} — the firewall. A number
    that matches nothing stays raw and the tier-1 gate rejects it (hallucination guard)."""
    for tok, no in sorted(toks.items(), key=lambda kv: -len(kv[1].rendered())):
        for variant in (no.rendered(), no.rendered().lstrip("+")):
            if variant and variant in text:
                text = text.replace(variant, "{" + tok + "}")
    return text


def critique(png: str, title: str, thesis: str, read: str) -> Critique:
    llm = get_llm(model=VISION_MODEL).with_structured_output(Critique)
    b64 = _img_b64(png)
    msg = [{"role": "user", "content": [
        {"type": "text", "text":
            "You are the editor of a market-research desk reviewing this rendered client infographic "
            f"(headline: \"{title}\"). Judge ONLY what this page controls — the COPY and the PAGE LAYOUT. "
            "Do NOT critique the embedded chart's internals (its axis units, colorbar, tick spacing) — "
            "that is handled elsewhere; treat the chart as a given image.\n"
            "Fail the page for: (1) COPY — the thesis is not a DECISIVE claim, or the read is not an actual "
            "CALL to act (any hedging, conditional escape-hatch, vagueness, internal contradiction, or "
            "generic filler is a defect); (2) LAYOUT — text overflow, collision, a KPI value clipped or "
            "misaligned, the page looking like a template rather than a made thing. "
            "Give concrete, actionable fixes to the COPY. If the copy is a confident call and the layout is "
            "clean, set ok=true.\n"
            f"Thesis as written: {thesis}\nRead as written: {read}"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]}]
    return llm.invoke(msg)


def _cited(text: str, toks: dict) -> list[NumberObject]:
    return [toks[t] for t in dict.fromkeys(_TOKEN.findall(text)) if t in toks]


def build_spec(mat: dict, nar: Narration, toks: dict) -> tuple[InfographicSpec, set[str]]:
    p, numbers = mat["p"], mat["numbers"]
    dimensioned = [k for k in mat["salient"]
                   if any(c in "%$×σ°" or c.isalpha() for c in numbers[k].rendered())]
    tiles = [Block(id=f"kpi{i}", type="kpi_tile",
                   title=clean_meaning(mat["meanings"].get(k, ""), humanise(k.split(".", 1)[1])),
                   numbers=[numbers[k]], tone=_TONES[i % len(_TONES)])
             for i, k in enumerate(dimensioned[:4])]
    charts = [Block(id="ch0", type="chart_embed", title="", chart_png=png)
              for png, _cap in hero_charts(p, mat["runs"], n=1)]
    thesis_t, read_t = _tokenize(nar.thesis, toks), _tokenize(nar.read, toks)
    thesis = Block(id="thesis", type="thesis_callout", text=thesis_t, numbers=_cited(thesis_t, toks))
    read = Block(id="read", type="note", title="The read", text=read_t, numbers=_cited(read_t, toks))
    source = Block(id="src", type="source",
                   text=(f"Source: {', '.join(mat['source_labels']) or 'UMD'}."
                         + (f"  Data as of {mat['as_of']}." if mat["as_of"] else "")))
    spec = InfographicSpec(persona=p["name"], title=p["title"], deck=p.get("decision", ""),
                           as_of=mat["as_of"], family="decision_brief",
                           layout=Layout(accent=_PALETTE[0], palette=_PALETTE),
                           blocks=[thesis, *tiles, *charts, read, source])
    return spec, set(numbers.keys())


def run_agentic(persona_id: str, conn, out_png: str, *, max_iter: int = 3) -> dict:
    """Narrate → render → tier-1 gate → vision critic → revise, bounded. Returns a result dict."""
    mat = persona_material(persona_id, conn)
    toks, menu = _citable(mat)
    nar = narrate(mat, toks, menu)
    feedback, iters = "", 0
    while True:
        iters += 1
        spec, valid = build_spec(mat, nar, toks)
        html = render_html(spec)
        problems = lint_infographic(spec, html, valid)          # tier-1: deterministic firewall
        if problems and iters < max_iter:                       # LLM typed a digit / hedged / bad token
            nar = narrate(mat, toks, menu, feedback="; ".join(problems)); continue
        if problems:                                            # out of budget → refuse (never ship bad)
            return {"persona": persona_id, "ok": False, "stage": "tier1", "problems": problems, "iters": iters}
        html_to_png(html, out_png)
        crit = critique(out_png, spec.title, nar.thesis, nar.read)   # tier-2: multimodal
        if crit.ok or iters >= max_iter:
            return {"persona": persona_id, "ok": True, "png": out_png, "iters": iters,
                    "thesis": nar.thesis, "read": nar.read, "critic_ok": crit.ok, "defects": crit.defects}
        nar = narrate(mat, toks, menu, feedback="; ".join(crit.fixes or crit.defects))
