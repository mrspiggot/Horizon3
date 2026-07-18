"""The `cross_section_ladder` layout family — rank one quantity across a set of entities.

Shape: headline + number-free thesis + a RANKED TABLE that is the hero (every rung of the cross-section
ranked) + the cross-section heatmap as the supporting chart + a "the read" note + provenance. The
discipline that makes it a coherent ladder and not a mixed bag: it ranks only the outputs of the
persona's ONE *cross-section* model — the model whose chart is a `heatmap` — because those outputs are
the same quantity measured across entities (IG/EM/HY spreads, the commodity complex, the term-premium
term structure, the vol curve, the FCI subindices). Ranking a default probability next to a credit
spread just because both read "%" is exactly the incoherence this refuses. Applies to any persona
carrying a heatmap/cross-section model. Deterministic; every rung is a provenance-traced NumberObject.
"""
from __future__ import annotations

import re
from collections import Counter

from ..from_persona import (chart_png_family, dashboard_read, dashboard_thesis, decisive, humanise,
                            persona_material)
from ..gate import emit
from ..schema import Block, InfographicSpec, Layout

_PALETTE = ["#4C6EA8", "#D55E00", "#009E73", "#B8C4CE", "#D98A00"]
_UNITS = ("%", "σ", "×", "$", "pp", "bp")


def _sig(rendered: str) -> str:
    for u in _UNITS:
        if u in rendered:
            return u
    return ""


def _rung_label(meaning: str, field: str) -> str:
    m = re.sub(r"\s+", " ", re.split(r"[—(;]", meaning or "", 1)[0].strip())
    if not m:
        return humanise(field)
    return m if len(m) <= 46 else humanise(field)


def _cross_section(mat: dict) -> tuple[str, str] | None:
    """(model_id, heatmap-chart-id) for the persona's cross-section model, or None."""
    for mid in mat["p"].get("models", []):
        for c in (mat["runs"].get(mid, {}).get("charts") or []):
            if (c.get("data_contract", {}) or {}).get("kind") == "heatmap":
                return mid, c["id"]
    return None


def spec_from_persona(persona_id: str, conn, *, min_rungs: int = 3,
                      article: dict | None = None) -> tuple[InfographicSpec, set[str]]:
    mat = persona_material(persona_id, conn)
    p, numbers, meanings = mat["p"], mat["numbers"], mat["meanings"]
    xs = _cross_section(mat)
    if not xs:
        raise ValueError(f"{persona_id}: no cross-section (heatmap) model — not a ladder persona")
    mid, chart_id = xs

    # the rungs: this ONE model's outputs, restricted to the dominant unit so the ranking is coherent
    keys = [k for k in numbers if k.startswith(f"{mid}.")
            and any(c in "%$×σ°" or c.isalpha() for c in numbers[k].rendered())]
    if not keys:
        raise ValueError(f"{persona_id}: cross-section model {mid!r} has no dimensioned outputs")
    dom_unit = Counter(_sig(numbers[k].rendered()) for k in keys).most_common(1)[0][0]
    rung_keys = sorted((k for k in keys if _sig(numbers[k].rendered()) == dom_unit),
                       key=lambda k: numbers[k].value, reverse=True)
    if len(rung_keys) < min_rungs:
        raise ValueError(f"{persona_id}: only {len(rung_keys)} '{dom_unit}' rungs (needs ≥{min_rungs})")

    rows = [{"label": _rung_label(meanings.get(k, ""), k.split(".", 1)[1]), "name": numbers[k].name}
            for k in rung_keys]
    ladder = Block(id="ladder", type="ranked_table",
                   title=f"The cross-section, ranked ({dom_unit})",
                   rows=rows, numbers=[numbers[k] for k in rung_keys])

    png, insight = chart_png_family(mat["runs"][mid], chart_id)
    if not png:
        raise ValueError(f"{persona_id}: cross-section heatmap {chart_id!r} did not render")
    cap = decisive(" ".join(insight.split()))
    chart = Block(id="ch0", type="chart_embed",
                  title=(cap[:128] + "…") if len(cap) > 128 else cap, chart_png=png)

    thesis = Block(id="thesis", type="thesis_callout", text=dashboard_thesis(mat, article))
    blocks = [thesis, ladder, chart]
    take = dashboard_read(mat, article)
    if take:
        blocks.append(Block(id="note", type="note", title="The read", text=take))
    src_line = f"Source: {', '.join(mat['source_labels']) or 'UMD'}."
    if mat["as_of"]:
        src_line += f"  Data as of {mat['as_of']}."
    blocks.append(Block(id="src", type="source", text=src_line))

    spec = InfographicSpec(
        persona=p["name"], title=p["title"], deck=p.get("decision", ""),
        as_of=mat["as_of"], family="cross_section_ladder",
        layout=Layout(accent=_PALETTE[0], palette=_PALETTE),
        blocks=blocks)
    return spec, set(numbers.keys())


def render_persona(persona_id: str, conn, out_png: str, **kw) -> str:
    spec, valid = spec_from_persona(persona_id, conn, **kw)
    return emit(spec, out_png, valid_sources=valid)
