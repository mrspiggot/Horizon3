"""The chart ENCODING grammar — the contract the Chart Studio agents reason in.

This is Horizon3's answer to "what chart for this insight and this data shape?" being a
*reasoning* problem, not a lookup table. The agents (framer → proposer → critic panel)
deliberate and emit a `ChartEncoding`: a declarative, Vega-Lite-inspired description of a
visualization — mark + channel encodings + transforms + annotations — grounded in the
Mackinlay/Draco expressiveness+effectiveness tradition. A deterministic compiler
(`compile.py`) turns a `ChartEncoding` into matplotlib (rendering stays code; no diffusion
model touches a numeric artifact — CLAUDE.md hard-rule #3).

Design notes:
- The grammar deliberately carries an editorial vocabulary beyond line/bar — connected
  scatter, dumbbell, slope, ridgeline, small multiples — so the proposer can pick the FORM
  the message needs (the anti-"vanilla" fix). See references/choosing-a-form.
- `data` is a long-form table (rows of records) the executed insight is flattened into, so
  the same grammar serves any model output. Fields are referenced by name.
- Everything is JSON-serialisable (pydantic) so it round-trips through an LLM tool call and
  is inspectable/loggable in LangSmith.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Mark(str, Enum):
    """The visual form. The communicative *job* (compare / trend / spread / relationship /
    part-to-whole / flow / rank) picks the mark — chosen by the agents, never defaulted."""
    line = "line"                     # trend over time, 1+ series
    area = "area"                     # trend + magnitude; signed fill via `baseline`
    stacked_area = "stacked_area"     # part-to-whole over time
    bar = "bar"                       # comparison across categories
    grouped_bar = "grouped_bar"       # comparison across 2 categories
    dumbbell = "dumbbell"             # two values per item (before/after, actual/target) — divergence at a glance
    slope = "slope"                   # two time points, many items — who rose/fell
    point = "point"                   # scatter — a relationship
    connected_scatter = "connected_scatter"  # a relationship WITH a time path (the loop)
    bubble = "bubble"                 # scatter + size (3rd var)
    heatmap = "heatmap"               # a whole cross-section (item × time / surface)
    ridgeline = "ridgeline"           # a distribution moving over time (faceted densities)
    waterfall = "waterfall"           # how a total is built up / decomposed


class FieldType(str, Enum):
    quantitative = "quantitative"     # a number (continuous)
    temporal = "temporal"             # a date/time
    nominal = "nominal"               # an unordered category (identity)
    ordinal = "ordinal"               # an ordered category


class Scale(BaseModel):
    zero: bool | None = Field(None, description="Force the axis to include zero (bars: yes; trend lines: usually no).")
    type: Literal["linear", "log", "symlog"] = "linear"
    domain: list[float] | None = Field(None, description="Explicit [min, max]; omit to auto-fit.")
    nice: bool = True


class Channel(BaseModel):
    """One visual channel bound to a data field. Absent optional channels are simply unused."""
    field: str = Field(..., description="Column name in the encoding's `data` table.")
    type: FieldType
    title: str | None = None
    scale: Scale | None = None
    aggregate: Literal["sum", "mean", "min", "max", "count"] | None = None
    legend: bool = True


class Encoding(BaseModel):
    """The channel bindings. x/y are the positional axes; the rest are optional secondary channels."""
    x: Channel | None = None
    y: Channel | None = None
    color: Channel | None = Field(None, description="Categorical → identity (fixed-order hues); quantitative → sequential; signed → diverging.")
    size: Channel | None = None
    detail: Channel | None = Field(None, description="Grouping field that splits marks into series WITHOUT its own legend colour (e.g. the entity in a connected scatter).")
    facet: Channel | None = Field(None, description="Small-multiples: one panel per value of this field.")
    text: Channel | None = Field(None, description="Direct-label field (selective labels beat a legend).")


class RefLine(BaseModel):
    """A reference line/curve the reader measures against (zero, a Taylor rule, a parity line)."""
    orient: Literal["x", "y", "diagonal", "custom"] = "y"
    value: float | None = Field(None, description="For orient x/y: the axis intercept.")
    slope: float | None = Field(None, description="For diagonal: y = slope*x + intercept.")
    intercept: float | None = None
    label: str | None = None
    shade_below: bool = Field(False, description="Shade the region below the line (e.g. 'behind the curve').")


class EventMarker(BaseModel):
    """A dated annotation on a temporal axis (a crisis, a policy pivot) — the editorial layer."""
    at: str = Field(..., description="ISO date or x-value to anchor to.")
    label: str
    series: str | None = Field(None, description="Optional: anchor to a specific series' point.")


class Annotations(BaseModel):
    ref_lines: list[RefLine] = Field(default_factory=list)
    events: list[EventMarker] = Field(default_factory=list)
    label_last: bool = Field(True, description="Label the last point of each series directly (vs a legend).")


class ColorJob(str, Enum):
    """Which of the four color jobs applies — drives the palette the compiler pulls (dataviz skill)."""
    categorical = "categorical"       # identity — fixed-order hues, never cycled
    sequential = "sequential"         # magnitude — one hue light→dark
    diverging = "diverging"           # polarity — two hues + neutral midpoint at zero
    status = "status"                 # good/warn/critical — reserved, never a "series 4"


class ChartEncoding(BaseModel):
    """A complete, renderable chart specification — the unit the Studio produces and critiques.

    `message` names the ONE thing the chart says (the framer's job); `rationale` records WHY
    this mark/encoding was chosen over alternatives (the critic panel's consensus) — both are
    kept for the judge, the article prose, and LangSmith traceability.
    """
    title: str
    subtitle: str | None = None
    message: str = Field(..., description="The single communicative job, one sentence (compare/trend/spread/relationship/rank/part-to-whole).")
    mark: Mark
    encoding: Encoding
    color_job: ColorJob = ColorJob.categorical
    annotations: Annotations = Field(default_factory=Annotations)
    source_note: str | None = Field(None, description="Provenance line, e.g. model + papers + as-of date.")
    rationale: str | None = Field(None, description="Why this form/encoding carries the insight better than the alternatives.")
    # The data the chart renders: a long-form list of record dicts. Kept out of the LLM's
    # reasoning context (only the schema/profile is shown); injected by the compiler at render.
    data: list[dict[str, Any]] = Field(default_factory=list, description="Long-form rows; every value from an executed model output — the LLM never authors a number.")

    model_config = {"use_enum_values": True}
