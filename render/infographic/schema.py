"""The AIS metadata IR — the load-bearing contract between verified numbers and render.

Every number that reaches the page is a ``NumberObject`` carrying its provenance (which executed
model output it came from, computed how, as of when). The layout LLM (later phases) designs the
``InfographicSpec`` — it selects blocks and arranges them — but it authors no value: the renderer can
only PLACE ``NumberObject``s, and the tier-1 gate refuses any rendered number that does not equal one.
This is the §12 "number-carrying schema between every stage" + Infogen's metadata, fused.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BlockType = Literal[
    "thesis_callout", "kpi_tile", "chart_embed", "ranked_table",
    "state_badge", "note", "source", "illustration_slot",
]


class NumberObject(BaseModel):
    """One provenance-traced number. The ONLY thing that may become a rendered figure."""
    name: str                       # short key, unique within its block (also the {placeholder})
    value: float
    unit: str = ""                  # "%", "pp", "bp", "σ", "×", "$", …
    source: str                     # "<model_id>.<output>" — must resolve to an executed output
    source_computation: str = ""    # how it was computed (the model's method)
    as_of: str = ""                 # date of the executed run
    fmt: str = "{:+.2f}"            # deterministic format — NOT an LLM choice

    def rendered(self) -> str:
        try:
            s = self.fmt.format(self.value)
        except Exception:
            s = str(self.value)
        return f"{s}{self.unit}" if self.unit and self.unit not in s else s


class GridSlot(BaseModel):
    row: int = 0
    col: int = 0
    rowspan: int = 1
    colspan: int = 1


class Block(BaseModel):
    """One cell of the page. Prose lives in ``text``/``title`` as templates whose ``{name}``
    placeholders are filled from ``numbers`` — so every figure on the page is a NumberObject."""
    id: str
    type: BlockType
    slot: GridSlot | None = None
    title: str = ""                 # heading / eyebrow (may hold {name} placeholders)
    text: str = ""                  # body template; {name} → the matching NumberObject
    tone: str = ""                  # "up" | "dn" | "mid" | "" — semantic accent for tiles/pills
    numbers: list[NumberObject] = Field(default_factory=list)
    chart_png: str | None = None    # base64 PNG for chart_embed (an ACS family / from_graph chart)
    rows: list[dict] = Field(default_factory=list)   # for ranked_table
    style: dict = Field(default_factory=dict)

    def num(self, name: str) -> NumberObject | None:
        return next((n for n in self.numbers if n.name == name), None)


class Layout(BaseModel):
    grid_cols: int = 12
    palette: list[str] = Field(default_factory=list)   # dataviz-validated hexes
    accent: str = "#4C6EA8"


class InfographicSpec(BaseModel):
    """Infogen 'metadata': what the LLM designs. It authors no value — only structure + selection."""
    persona: str
    title: str                      # the headline (number-free)
    deck: str = ""                  # sub-headline (number-free)
    source_footnote: str = ""
    as_of: str = ""
    family: Literal["decision_brief", "decomposition_hero", "regime_dashboard",
                    "cross_section_ladder"] = "decision_brief"
    layout: Layout = Field(default_factory=Layout)
    blocks: list[Block] = Field(default_factory=list)

    def all_numbers(self) -> list[NumberObject]:
        out: list[NumberObject] = []
        for b in self.blocks:
            out.extend(b.numbers)
        return out

    def blocks_of(self, *types: str) -> list[Block]:
        return [b for b in self.blocks if b.type in types]
