"""The `decision_brief` layout family — the default single-page infographic.

Shape (the flagship_fed_model form, generalised): headline + number-free thesis callout + a row of
KPI tiles (the author's salient executed numbers) + the persona's hero ACS charts + a "what the
models say" note + a provenance footer. Deterministic: built from the persona's executed run with no
LLM. Every KPI is a provenance-traced NumberObject; the tier-1 gate refuses anything else.
"""
from __future__ import annotations

from ..from_persona import chart_png, first_sentence, humanise, persona_material
from ..gate import emit
from ..schema import Block, InfographicSpec, Layout

_PALETTE = ["#4C6EA8", "#D55E00", "#009E73", "#B8C4CE", "#D98A00"]
_TONES = ["mid", "up", "dn", "mid"]


def spec_from_persona(persona_id: str, conn, *, n_tiles: int = 4, n_charts: int = 2) -> tuple[InfographicSpec, set[str]]:
    """Return (spec, valid_sources) — valid_sources is the set of executed output keys the gate
    checks every rendered number against."""
    mat = persona_material(persona_id, conn)
    p, numbers, salient = mat["p"], mat["numbers"], mat["salient"]

    # KPI tiles from the author's salient numbers, keeping only DIMENSIONED ones (a bare, unitless
    # value is usually a raw input — the model's OUTPUTS carry the units and the insight).
    dimensioned = [k for k in salient
                   if any(c in "%$×σ°" or c.isalpha() for c in numbers[k].rendered())]
    tiles: list[Block] = []
    for i, key in enumerate(dimensioned[:n_tiles]):
        field = key.split(".", 1)[1]
        tiles.append(Block(id=f"kpi{i}", type="kpi_tile", title=humanise(field),
                           numbers=[numbers[key]], tone=_TONES[i % len(_TONES)]))

    charts: list[Block] = []
    for mid, cid in p["stub_charts"]:
        if len(charts) >= n_charts:
            break
        png = chart_png(mat["runs"].get(mid, {}), cid)
        if png:
            charts.append(Block(id=f"ch{len(charts)}", type="chart_embed", title=cid, chart_png=png))

    thesis = Block(id="thesis", type="thesis_callout",
                   text=first_sentence(p.get("summary_template", "")))
    note = Block(id="note", type="note", title="How to read this",
                 text=(f"Grounded in {_spell(len(p['models']))} executed models "
                       f"({', '.join(p['models'])}). The narrative selects and explains; "
                       f"it authors no number — every figure is a model output."))
    source = Block(id="src", type="source",
                   text=(f"Sources: {', '.join(mat['sources']) or 'UMD'}. "
                         f"Grounded in: {', '.join(mat['papers']) or 'catalogued models'}. "
                         f"Executed as of {mat['as_of']}; rendering is deterministic code — "
                         f"no diffusion, no authored number."))

    spec = InfographicSpec(
        persona=p["name"], title=p["title"], deck=p.get("decision", ""),
        as_of=mat["as_of"], family="decision_brief",
        layout=Layout(accent=_PALETTE[0], palette=_PALETTE),
        blocks=[thesis, *tiles, *charts, note, source])
    return spec, set(numbers.keys())


def render_persona(persona_id: str, conn, out_png: str, **kw) -> str:
    spec, valid = spec_from_persona(persona_id, conn, **kw)
    return emit(spec, out_png, valid_sources=valid)


_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def _spell(n: int) -> str:
    return _WORDS.get(n, str(n))
