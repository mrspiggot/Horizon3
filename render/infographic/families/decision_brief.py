"""The `decision_brief` layout family — the default single-page infographic.

Shape (the flagship_fed_model form, generalised): headline + number-free thesis callout + a row of
KPI tiles (the author's salient executed numbers) + the persona's hero ACS charts + a "what the
models say" note + a provenance footer. Deterministic: built from the persona's executed run with no
LLM. Every KPI is a provenance-traced NumberObject; the tier-1 gate refuses anything else.
"""
from __future__ import annotations

from ..from_persona import (chart_png, clean_meaning, dashboard_read, dashboard_thesis,
                            dashboard_tile_keys, decisive, hero_charts, humanise, persona_material)
from ..gate import emit
from ..schema import Block, InfographicSpec, Layout

_PALETTE = ["#4C6EA8", "#D55E00", "#009E73", "#B8C4CE", "#D98A00"]
_TONES = ["mid", "up", "dn", "mid"]


def spec_from_persona(persona_id: str, conn, *, n_tiles: int = 4, n_charts: int = 1,
                      article: dict | None = None) -> tuple[InfographicSpec, set[str]]:
    """Return (spec, valid_sources) — valid_sources is the set of executed output keys the gate
    checks every rendered number against. When `article` is supplied, the thesis, the tiles and the
    read are derived from the FINISHED piece rather than the static template."""
    mat = persona_material(persona_id, conn)
    p, numbers, meanings = mat["p"], mat["numbers"], mat["meanings"]

    # KPI tiles: the numbers the PROSE cited (canonical), else the salient menu to the floor. Tile
    # headings come from the authored `meaning` (reader-facing), not the internal field id.
    tiles: list[Block] = []
    for i, key in enumerate(dashboard_tile_keys(mat, article, n=n_tiles)):
        heading = clean_meaning(meanings.get(key, ""), humanise(key.split(".", 1)[1]))
        tiles.append(Block(id=f"kpi{i}", type="kpi_tile", title=heading,
                           numbers=[numbers[key]], tone=_TONES[i % len(_TONES)]))

    # Hero chart(s): the best POLISHED ACS structure-family render available anywhere in the
    # persona's models; the chart's authored `insight` becomes an editorial caption.
    def _cap(insight: str) -> str:
        s = decisive(insight)
        return (s[:128] + "…") if len(s) > 128 else s

    charts: list[Block] = []
    for png, insight in hero_charts(p, mat["runs"], n=n_charts):
        charts.append(Block(id=f"ch{len(charts)}", type="chart_embed",
                            title=_cap(insight), chart_png=png))
    if not charts:                                          # fall back to a graph render of a stub
        for mid, cid in p["stub_charts"]:
            png = chart_png(mat["runs"].get(mid, {}), cid)
            if png:
                charts.append(Block(id="ch0", type="chart_embed", title=cid, chart_png=png))
                break

    thesis = Block(id="thesis", type="thesis_callout", text=dashboard_thesis(mat, article))
    # a real editorial takeaway — the finished article's closing read (reader copy, number-free)
    blocks = [thesis, *tiles, *charts]
    take = dashboard_read(mat, article)
    if take:
        blocks.append(Block(id="note", type="note", title="The read", text=take))
    # a clean, FT-style source line — no internal ids, no system doctrine
    src_line = f"Source: {', '.join(mat['source_labels']) or 'UMD'}."
    if mat["as_of"]:
        src_line += f"  Data as of {mat['as_of']}."
    blocks.append(Block(id="src", type="source", text=src_line))

    spec = InfographicSpec(
        persona=p["name"], title=p["title"], deck=p.get("decision", ""),
        as_of=mat["as_of"], family="decision_brief",
        layout=Layout(accent=_PALETTE[0], palette=_PALETTE),
        blocks=blocks)
    return spec, set(numbers.keys())


def render_persona(persona_id: str, conn, out_png: str, **kw) -> str:
    spec, valid = spec_from_persona(persona_id, conn, **kw)
    return emit(spec, out_png, valid_sources=valid)


_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def _spell(n: int) -> str:
    return _WORDS.get(n, str(n))
