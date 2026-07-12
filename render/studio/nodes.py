"""The Chart Studio agent nodes.

Each node is a pure function StudioState -> partial StudioState. LLM nodes use structured
output so results are validated pydantic objects (no brittle parsing) and inspectable in
LangSmith. The deterministic nodes (compile) render pixels. The design enforces CLAUDE.md #2:
the LLM sees only the DATA PROFILE (field names/types/ranges) and the executed interpretation
— never raw numbers — and emits an encoding referencing field names; the compiler injects the
real rows.
"""
from __future__ import annotations

import base64
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from .compile import compile_encoding
from .encoding import (Annotations, Channel, ChartEncoding, ColorJob, Encoding, FieldType,
                       Mark)
from .llm import VISION_MODEL, get_llm
from .state import StudioState


def _fallback_encoding(brief) -> ChartEncoding:
    """A guaranteed-renderable encoding derived from the data profile — used if the agent's
    chosen encoding won't compile (references a missing field, an unsupported combination, …).
    A line of the quantitative value over the temporal/ordinal axis, coloured by series."""
    fields = brief.profile.fields
    temporal = next((f.name for f in fields if f.dtype == "temporal"), None)
    quant = next((f.name for f in fields if f.dtype == "quantitative" and f.name != "order"), None)
    xcol = temporal or (brief.profile.series_field or (fields[0].name if fields else "x"))
    xtype = FieldType.temporal if temporal else FieldType.nominal
    enc = ChartEncoding(
        title=(brief.model_id.replace("_", " ").title()),
        message="fallback line of the executed series",
        mark=Mark.line, color_job=ColorJob.categorical,
        encoding=Encoding(
            x=Channel(field=xcol, type=xtype),
            y=Channel(field=(quant or "value"), type=FieldType.quantitative),
            detail=(Channel(field=brief.profile.series_field, type=FieldType.nominal)
                    if brief.profile.series_field else None)),
        annotations=Annotations(label_last=True),
        source_note=f"{brief.model_id} · {', '.join(brief.papers)}")
    return enc

# ── small schemas for the reasoning nodes ────────────────────────────────────────────────────


class Frame(BaseModel):
    message: str = Field("", description="The ONE thing the chart must say, one sentence, naming the communicative job (compare/trend/spread/relationship/part-to-whole/rank/divergence).")
    candidate_marks: list[str] = Field(default_factory=list, description="2–3 chart FORMS worth proposing for this message+data-shape, from: line, area, bar, grouped_bar, dumbbell, slope, point, connected_scatter, bubble, heatmap, ridgeline, waterfall. Ordered best-first. Avoid defaulting to line/bar unless the data genuinely calls for it.")
    reasoning: str = Field("", description="Why these forms fit the message and the number/shape of variables.")


class PanelVerdict(BaseModel):
    chosen_index: int = Field(0, description="0-based index of the winning candidate.")
    rationale: str = Field("", description="Consensus of the three experts: why this encoding carries the insight best (effectiveness + insight-carriage + differentiation vs a vanilla default).")


class VisualCritique(BaseModel):
    ok: bool | None = Field(None, description="True if the rendered chart is clean and reads clearly with no defects worth fixing. If omitted, inferred from whether defects were listed.")
    defects: list[str] = Field(default_factory=list, description="Concrete rendered-pixel problems: label collisions, occlusion, clipped/overshooting axes, unreadable spaghetti, a legend that duplicates direct labels, a near-empty panel, etc.")
    fixes: list[str] = Field(default_factory=list, description="Specific, encoding-level changes to fix each defect (e.g. 'set y scale.domain to [-1,6]', 'drop the legend, keep direct labels', 'switch color_job to diverging').")

    @model_validator(mode="after")
    def _derive_ok(self):
        if self.ok is None:
            self.ok = not self.defects
        return self


class Judgment(BaseModel):
    verdict: bool = Field(False, description="True = ships (expressive, effective, carries the insight, and is differentiated — not something a muppet with the FT could reproduce).")
    notes: str = Field("", description="One or two sentences justifying the verdict against those criteria.")


_MARKS = "line, area, stacked_area, bar, grouped_bar, dumbbell, slope, point, connected_scatter, bubble, heatmap, ridgeline, waterfall"


# ── nodes ────────────────────────────────────────────────────────────────────────────────────

def framer(state: StudioState) -> dict:
    brief = state["brief"]
    llm = get_llm(temperature=0.2).with_structured_output(Frame)
    out: Frame = llm.invoke(
        "You are the framer in a data-visualization studio whose charts must beat what an FT/Economist "
        "journalist would produce. Start from the MESSAGE, not a chart you like. Given the executed "
        "insight and the data shape, state the single communicative job and the 2–3 forms that best carry "
        "it.\n\n" + brief.as_prompt() +
        f"\n\nAvailable marks: {_MARKS}.\n\n"
        "The brief states an INSIGHT TYPE and FORM GUIDANCE — treat them as the primary signal and "
        "propose the canonical forms for that type FIRST (relationship→connected_scatter/point; "
        "surface→heatmap/small-multiples; cross_section→curve/slope/dumbbell; decomposition→stacked_area/"
        "waterfall; distribution→ridgeline/violin/pearson; state_space→quadrant/momentum; trend→line/area "
        "only when it earns it). Then:\n"
        "FORM-CHOICE PRINCIPLES:\n"
        "- If the insight is a PART-TO-WHOLE / DECOMPOSITION — the fields SUM to a total, or the text says "
        "'split into', 'decomposed', 'X = A + B', 'compensation for … plus …' — lead with stacked_area (over "
        "time) or waterfall; a set of separate lines HIDES the composition and is wrong.\n"
        "- A relationship-with-a-time-path → connected_scatter; two values per item → dumbbell; two time "
        "points across items → slope; a whole cross-section over time → heatmap; a distribution moving over "
        "time → ridgeline.\n"
        "- A plain line/area is legitimate when the message really is one-or-few series over time — but only "
        "if it earns it: the DIFFERENTIATION then comes from the analytical framing (reference lines, "
        "thresholds, shaded regimes/recessions, direct labels, a sharp thesis headline), not the mark. Note "
        "that framing intent in `reasoning` so the proposer builds it."
    )
    return {"message": out.message, "candidate_marks": out.candidate_marks[:3]}


def proposer(state: StudioState) -> dict:
    brief = state["brief"]
    llm = get_llm(temperature=0.5).with_structured_output(ChartEncoding)
    candidates: list[ChartEncoding] = []
    for mark in state.get("candidate_marks", []) or ["line"]:
        try:
            enc: ChartEncoding = llm.invoke(
                "You are the proposer in a data-visualization studio. Emit a COMPLETE ChartEncoding for the "
                f"insight below using mark='{mark}'. Reference ONLY the field names in the data shape. "
                "Design it to carry the executed interpretation as its headline.\n"
                "ALWAYS add the editorial layer that separates craft from a muppet-with-the-FT — this is "
                "where a line/area earns its place: reference lines (zero, a model/rule line, a ±1σ or "
                "average threshold the reader measures against), dated event markers for the regimes that "
                "matter (crises, policy pivots), shaded regions where relevant, and selective DIRECT LABELS "
                "instead of a legend. Write a thesis `title`, a `subtitle`, a `message`, a `rationale` (why "
                "this beats a vanilla default), and a `source_note`. For a decomposition, colour by the "
                "component field so the parts stack to the total. "
                "CRITICAL: leave `data` EMPTY — the real rows are injected by the renderer; never author "
                "numbers.\n\n" + brief.as_prompt()
            )
            enc.data = []  # never trust the LLM with data
            candidates.append(enc)
        except Exception:
            continue
    return {"candidates": candidates}


def critic_panel(state: StudioState) -> dict:
    brief = state["brief"]
    cands = state.get("candidates", [])
    if not cands:
        raise ValueError("critic_panel: no candidates to judge")
    if len(cands) == 1:
        return {"chosen": cands[0], "critique_rationale": "single candidate"}
    listing = "\n\n".join(
        f"[{i}] mark={c.mark} title={c.title!r}\n    encoding={c.encoding.model_dump(exclude_none=True)}\n    rationale={c.rationale}"
        for i, c in enumerate(cands)
    )
    llm = get_llm(temperature=0.2).with_structured_output(PanelVerdict)
    v: PanelVerdict = llm.invoke(
        "You are a three-expert panel choosing the best visualization: (1) a perception/effectiveness "
        "expert (is it decoded fast and accurately? expressiveness/effectiveness, Mackinlay/Draco), (2) an "
        "insight-carriage expert (does the FORM make the executed interpretation obvious?), (3) a "
        "differentiation expert (is it beyond a vanilla line/bar a muppet with the FT could make?). Debate, "
        "then reach consensus.\n\n" + brief.as_prompt() +
        f"\n\nMESSAGE: {state.get('message')}\n\nCANDIDATES:\n{listing}"
    )
    idx = max(0, min(v.chosen_index, len(cands) - 1))
    return {"chosen": cands[idx], "critique_rationale": v.rationale}


def compile_node(state: StudioState) -> dict:
    brief = state["brief"]
    enc = state["chosen"].model_copy(deep=True)
    enc.data = brief.rows                    # inject the real numbers deterministically
    out_dir = state.get("out_dir", "/tmp")
    png = str(Path(out_dir) / "studio_chart.png")
    try:
        compile_encoding(enc, png)
    except Exception as exc:
        # The chosen encoding won't render (missing field, bad combo). Don't kill the run —
        # fall back to a guaranteed-renderable line so the critic/judge still get a chart, and
        # record why so the next revision can recover.
        fb = _fallback_encoding(brief)
        fb.data = brief.rows
        compile_encoding(fb, png)
        enc = fb
        return {"png_path": png, "chosen": enc, "iterations": state.get("iterations", 0) + 1,
                "visual_feedback": f"[compile fell back to a safe line: {type(exc).__name__}: {str(exc)[:120]}]"}
    return {"png_path": png, "chosen": enc, "iterations": state.get("iterations", 0) + 1}


def multimodal_critique(state: StudioState) -> dict:
    png = state["png_path"]
    b64 = base64.b64encode(Path(png).read_bytes()).decode()
    llm = get_llm(model=VISION_MODEL, temperature=0.1).with_structured_output(VisualCritique)
    msg = [{"role": "user", "content": [
        {"type": "text", "text":
            "You are the visual critic. LOOK at this rendered chart and judge it as printed pixels — not the "
            "idea, the execution. The chart must say: " + str(state.get("message")) + ". Flag concrete defects "
            "(label collisions, occlusion, clipped or overshooting axes, unreadable spaghetti, a redundant "
            "legend, a near-empty panel) and give specific encoding-level fixes. If it is clean and reads well, "
            "set ok=true."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]}]
    c: VisualCritique = llm.invoke(msg)
    fb = "" if c.ok else "Defects: " + "; ".join(c.defects) + "\nFixes: " + "; ".join(c.fixes)
    return {"visual_ok": c.ok, "visual_feedback": fb}


def reviser(state: StudioState) -> dict:
    """Apply the visual critic's fixes by editing the chosen encoding (re-emit, data-free)."""
    brief = state["brief"]
    cur = state["chosen"].model_copy(deep=True)
    cur.data = []
    llm = get_llm(temperature=0.2).with_structured_output(ChartEncoding)
    try:
        enc: ChartEncoding = llm.invoke(
            "Revise this ChartEncoding to fix the visual defects the critic found. Keep the mark and message "
            "unless a defect requires changing them; make the specific fixes. Reference ONLY fields that "
            "exist in the data shape. Leave `data` EMPTY.\n\n"
            f"CURRENT ENCODING:\n{cur.model_dump(exclude_none=True)}\n\n"
            f"CRITIC FEEDBACK:\n{state.get('visual_feedback')}\n\n{brief.as_prompt()}"
        )
        enc.data = []
        return {"chosen": enc}
    except Exception:
        # A failed revision must not kill the run — keep the current chart and move to the judge.
        return {"visual_ok": True}


def judge(state: StudioState) -> dict:
    brief = state["brief"]
    llm = get_llm(model=VISION_MODEL, temperature=0.1).with_structured_output(Judgment)
    b64 = base64.b64encode(Path(state["png_path"]).read_bytes()).decode()
    j: Judgment = llm.invoke([{"role": "user", "content": [
        {"type": "text", "text":
            "You are the final judge. Does this chart SHIP? Criteria: (1) expressive — faithful to the data; "
            "(2) effective — decoded fast and accurately; (3) it carries the executed insight as its headline; "
            "(4) differentiated. IMPORTANT on (4): differentiation is a property of the WHOLE artifact — the "
            "analytical framing, reference lines, regime/event annotations, thesis headline and the model "
            "behind it — NOT merely whether the mark is exotic. A line or area SHIPS when the form genuinely "
            "fits the message AND it is enriched with framing a muppet-with-the-FT would not add (a threshold "
            "the reader measures against, recession/crisis shading, a decomposition that reveals structure). "
            "FAIL it when: the form mis-serves the insight (e.g. a part-to-whole drawn as separate lines "
            "instead of stacked), it is a bare undifferentiated plot, labels collide, or it reads as generic. "
            "The insight it must carry:\n" + brief.interpretation + "\nMessage: " + str(state.get("message"))},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]}])
    return {"judge_pass": j.verdict, "judge_notes": j.notes}
