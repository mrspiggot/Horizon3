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


@dataclass
class InsightBrief:
    persona: str                    # e.g. "Central-bank policymaker"
    decision: str                   # the decision the chart informs
    model_id: str
    papers: list[str]
    interpretation: str             # the executed reading — what the outputs MEAN
    profile: DataFrameProfile
    rows: list[dict] = field(default_factory=list)   # the raw data — NOT shown to the LLM

    def as_prompt(self) -> str:
        return (
            f"PERSONA: {self.persona}\n"
            f"DECISION: {self.decision}\n"
            f"MODEL: {self.model_id}  (grounded in: {', '.join(self.papers) or 'n/a'})\n"
            f"EXECUTED INTERPRETATION (what the numbers mean — narrate, don't invent):\n"
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
