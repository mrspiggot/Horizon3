"""The `decomposition_hero` layout family — lead with the decomposition, KPIs ARE its legs.

Shape: headline + number-free thesis + a big decomposition chart as the hero + the decomposition's
own legs surfaced as KPI tiles (each component, plus the net total) + a "the read" note + provenance.
Where `decision_brief` picks the author's salient numbers, this family is disciplined by the model's
*structure*: the tiles are exactly the components that sum to the net — the "why is X where it is,
broken into its parts" story. Applies to any persona carrying a `kind:decomposition` chart (rates,
treasurer, credit). Deterministic; every leg is a provenance-traced NumberObject.
"""
from __future__ import annotations

import yaml

from ..from_persona import (GRAPH_DIR, chart_png_family, clean_meaning, decisive, first_sentence,
                            humanise, persona_material, reader_takeaway)
from ..gate import emit
from ..schema import Block, InfographicSpec, Layout

_PALETTE = ["#4C6EA8", "#D55E00", "#009E73", "#B8C4CE", "#D98A00"]
# authored decomposition-leg tone → our tile accent (warm legs = a cost/risk add, cool = the base)
_TONE = {"warm": "dn", "amber": "dn", "hot": "dn", "cool": "", "cold": "", "neutral": "mid"}


def _field(ref: str) -> str:  # "output:risk_free_pct" / "input:foo.level" → "risk_free_pct"
    return ref.split(":", 1)[-1].split(".", 1)[0]


def _find_decomposition(mat: dict) -> tuple[str, dict] | None:
    """First (model_id, decomposition-chart) across the persona's models."""
    for mid in mat["p"].get("models", []):
        for c in (mat["runs"].get(mid, {}).get("charts") or []):
            if (c.get("data_contract", {}) or {}).get("kind") == "decomposition":
                return mid, c
    return None


def spec_from_persona(persona_id: str, conn) -> tuple[InfographicSpec, set[str]]:
    mat = persona_material(persona_id, conn)
    p, numbers, meanings = mat["p"], mat["numbers"], mat["meanings"]
    found = _find_decomposition(mat)
    if not found:
        raise ValueError(f"{persona_id}: no decomposition model — not a decomposition_hero persona")
    mid, chart = found
    dc = chart["data_contract"]

    def _tile(leg: dict, tone: str) -> Block | None:
        key = f"{mid}.{_field(leg['from'])}"
        if key not in numbers:
            return None
        heading = clean_meaning(leg.get("label", ""), humanise(key.split(".", 1)[1]))
        return Block(id=f"leg_{key}", type="kpi_tile", title=heading,
                     numbers=[numbers[key]], tone=tone)

    # tiles: the NET total first (the headline the legs sum to), then each component leg
    tiles: list[Block] = []
    net_tile = _tile(dc["net"], "mid")
    if net_tile:
        tiles.append(net_tile)
    for leg in dc.get("components", []):
        t = _tile(leg, _TONE.get(leg.get("tone", ""), ""))
        if t:
            tiles.append(t)
    if len(tiles) < 3:
        raise ValueError(f"{persona_id}: decomposition has <3 resolvable legs")

    # hero: the polished decomposition chart itself, its authored insight as the caption
    png, insight = chart_png_family(mat["runs"][mid], chart["id"])
    if not png:
        raise ValueError(f"{persona_id}: decomposition chart {chart['id']!r} did not render")
    cap = decisive(" ".join(insight.split()))
    charts = [Block(id="hero", type="chart_embed", title=(cap[:128] + "…") if len(cap) > 128 else cap,
                    chart_png=png)]

    thesis = Block(id="thesis", type="thesis_callout",
                   text=first_sentence(p.get("summary_template", "")))
    blocks = [thesis, *tiles, *charts]
    take = reader_takeaway(p.get("summary_template", ""))
    if take:
        blocks.append(Block(id="note", type="note", title="The read", text=take))
    src_line = f"Source: {', '.join(mat['source_labels']) or 'UMD'}."
    if mat["as_of"]:
        src_line += f"  Data as of {mat['as_of']}."
    blocks.append(Block(id="src", type="source", text=src_line))

    spec = InfographicSpec(
        persona=p["name"], title=p["title"], deck=p.get("decision", ""),
        as_of=mat["as_of"], family="decomposition_hero",
        layout=Layout(accent=_PALETTE[0], palette=_PALETTE),
        blocks=blocks)
    return spec, set(numbers.keys())


def render_persona(persona_id: str, conn, out_png: str) -> str:
    spec, valid = spec_from_persona(persona_id, conn)
    return emit(spec, out_png, valid_sources=valid)
