"""Bridge an executed model insight into what the Studio agents reason over.

The agents must NOT see raw numbers to fabricate from (CLAUDE.md #2). So we split an insight
into two objects:
- `DataFrameProfile` — the SCHEMA + summary stats + field roles of the long-form data table.
  This is what the framer/proposer/critic see. Field names, types, cardinality, ranges, the
  temporal span — enough to choose a form, nothing to invent.
- the raw `rows` (long-form records) — kept aside and injected by the compiler at render time.

`InsightBrief` couples the profile with the human-meaningful context: the persona, the
decision, the model + papers, and the executed interpretation text ("output X > threshold ⇒
Z"). The agents design a chart that carries THIS interpretation over THIS data shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class FieldProfile:
    name: str
    dtype: str                      # temporal | quantitative | nominal
    n_unique: int
    example: Any = None
    vmin: float | None = None
    vmax: float | None = None
    span: str | None = None         # for temporal: "2021-01 → 2026-07"


@dataclass
class DataFrameProfile:
    n_rows: int
    fields: list[FieldProfile]
    n_series: int                   # distinct identity groups (the `detail` cardinality)
    series_field: str | None        # the field that identifies a series, if any
    note: str = ""

    def as_prompt(self) -> str:
        lines = [f"{self.n_rows} rows; {self.n_series} series"
                 + (f" keyed by '{self.series_field}'" if self.series_field else "") + "."]
        for f in self.fields:
            desc = f"  - {f.name} ({f.dtype}, {f.n_unique} distinct"
            if f.dtype == "quantitative" and f.vmin is not None:
                desc += f", range {f.vmin:.3g}…{f.vmax:.3g}"
            if f.span:
                desc += f", {f.span}"
            desc += ")"
            lines.append(desc)
        if self.note:
            lines.append(f"note: {self.note}")
        return "\n".join(lines)


# The insight taxonomy — what KIND of thing the chart says. The bridge classifies each insight
# from the authored data_contract; the framer maps the type to its canonical differentiated forms.
INSIGHT_TYPES = {
    "relationship": "how one variable moves AGAINST another (a scatter / connected-scatter, not two lines over time)",
    "cross_section": "a whole cross-section at one or a few moments (a curve / small multiples / dumbbell across items)",
    "surface": "a cross-section evolving over time (an item × time heatmap / surface)",
    "decomposition": "a total split into parts that sum to it (a stacked area / waterfall)",
    "distribution": "the SHAPE of a distribution — spread, skew, tails (a ridgeline / violin / Pearson diagram)",
    "state_space": "the §10 STATE — level + direction + acceleration + z-score + percentile (a quadrant / momentum map)",
    "trend": "one or a few series genuinely over time (a line/area — legitimate, but it must EARN it with framing)",
}


@dataclass
class CitableFact:
    """One computed figure a chart's analysis produced, to register as an executed (citable) number so
    the narrator may state it and the grounding judge accepts it. Numbers here are EXECUTED — the
    clustering/regression ran on the data — so they are legitimate figures, not LLM inventions."""
    label: str                      # human label for the citable menu
    value: float
    source: str                     # "<model_id>.<derived>" — provenance
    unit: str = ""
    fmt: str = "{:+.2f}"


@dataclass
class ChartInsight:
    """The computed findings a chart's OWN analysis produced — regimes + per-regime slopes, a pooled
    fit, a centroid path, PCA loadings, feature importances — i.e. the structure the reader SEES in the
    picture. Threaded into the prose brief so the narrator tells THIS chart's story from executed
    values instead of a textbook prior. Family-agnostic: every family returns this same shape."""
    kind: str                                          # 'regime' | 'pca' | 'cluster' | …
    headline: str = ""                                 # one-line computed summary
    findings: list[str] = field(default_factory=list)  # bullet readings, each grounded in computed values
    citable: list[CitableFact] = field(default_factory=list)  # distinctive figures to register as tokens
    facts: dict = field(default_factory=dict)          # structured values (for the judge / downstream)

    def narration(self) -> str:
        head = (self.headline or "").strip()
        body = "\n".join(f"       – {f}" for f in self.findings)
        if head and body:
            return f"{head}\n{body}"
        return head or body


@dataclass
class InsightBrief:
    persona: str                    # e.g. "Central-bank policymaker"
    decision: str                   # the decision the chart informs
    model_id: str
    papers: list[str]
    interpretation: str             # the executed reading — what the outputs MEAN
    profile: DataFrameProfile
    insight_type: str = "trend"     # one of INSIGHT_TYPES — what KIND of chart this is
    form_hint: str = ""             # the canonical forms + why (from the bridge's structural read)
    rows: list[dict] = field(default_factory=list)   # the raw data — NOT shown to the LLM
    instance: str = ""              # the jurisdiction this run is for — drives market-correct event markers

    def as_prompt(self) -> str:
        it = self.insight_type
        it_desc = INSIGHT_TYPES.get(it, "")
        return (
            f"PERSONA: {self.persona}\n"
            f"DECISION: {self.decision}\n"
            f"MODEL: {self.model_id}  (grounded in: {', '.join(self.papers) or 'n/a'})\n"
            f"INSIGHT TYPE: {it} — {it_desc}\n"
            + (f"FORM GUIDANCE: {self.form_hint}\n" if self.form_hint else "")
            + f"EXECUTED INTERPRETATION (what the numbers mean — narrate, don't invent):\n"
            f"  {self.interpretation}\n"
            f"DATA SHAPE (design the chart for THIS; reference these field names):\n"
            f"{self.profile.as_prompt()}"
        )


def profile_rows(rows: list[dict], *, series_field: str | None = None, note: str = "") -> DataFrameProfile:
    """Characterise a long-form table into a schema profile (no raw values leak beyond examples)."""
    df = pd.DataFrame(rows)
    fps: list[FieldProfile] = []
    for col in df.columns:
        s = df[col]
        # infer role
        if pd.api.types.is_numeric_dtype(s):
            dtype = "quantitative"
        else:
            parsed = pd.to_datetime(s, errors="coerce")
            dtype = "temporal" if parsed.notna().mean() > 0.8 else "nominal"
        fp = FieldProfile(name=col, dtype=dtype, n_unique=int(s.nunique()), example=s.iloc[0] if len(s) else None)
        if dtype == "quantitative":
            fp.vmin, fp.vmax = float(s.min()), float(s.max())
        elif dtype == "temporal":
            p = pd.to_datetime(s, errors="coerce")
            fp.span = f"{str(p.min())[:7]} → {str(p.max())[:7]}"
        fps.append(fp)
    # guess the series field: a nominal field with modest cardinality
    if series_field is None:
        cands = [f for f in fps if f.dtype == "nominal" and 1 < f.n_unique <= 12]
        series_field = cands[0].name if cands else None
    n_series = int(df[series_field].nunique()) if series_field and series_field in df else 1
    return DataFrameProfile(n_rows=len(df), fields=fps, n_series=n_series,
                            series_field=series_field, note=note)
