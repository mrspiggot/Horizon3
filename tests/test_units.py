"""_norm_unit must never glue a raw catalog unit onto the digits.

`NumberObject.rendered()` is `f"{s}{unit}"`. The old fallthrough returned the yaml string unchanged,
so `unit: V/U` printed as "1.05V/U" — and "1.07V/U" reached a reader in the economist_forecaster
article, the one that scored 7.2, the joint highest. Nine of the catalog's nineteen authored units
have no branch; widening `salient` to every executed number took the reachable ones from 1 to 6.
"""
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from render.infographic.from_persona import _norm_unit  # noqa: E402
from render.infographic.schema import NumberObject  # noqa: E402


def _catalog_units() -> set[str]:
    units = set()
    for f in (REPO / "catalog" / "graph").glob("*.yaml"):
        d = yaml.safe_load(f.read_text())
        if not isinstance(d, dict):
            continue
        for o in d.get("outputs") or []:
            if o.get("unit"):
                units.add(o["unit"])
    return units


def _render(unit: str, value: float = 1.05) -> str:
    u, fmt = _norm_unit(unit)
    return NumberObject(name="n", value=value, unit=u, fmt=fmt, source="s",
                        source_computation="c", as_of="2026-01-01").rendered()


# Units the codebase deliberately glues — "+1.05pp", "1.05%", "+1.05σ", "1.1×". `_render_for_prose`
# states the rule: "tight units (%, pp, bp, σ) stay glued". Anything NOT in this set fell through
# _norm_unit and must carry its own separator.
_TIGHT = {"%", "pp", "bp", "pts", "σ", "×", ""}


def test_every_catalog_unit_is_either_tight_or_separated():
    # The defect: `V/U` had no branch, so rendered() glued it — "1.05V/U".
    for unit in sorted(_catalog_units()):
        display, _fmt = _norm_unit(unit)
        assert display in _TIGHT or display.startswith(" "), (
            f"unit {unit!r} -> display {display!r}: neither a known tight unit nor separated; "
            f"it renders as {_render(unit)!r}")


def test_the_shipped_defect_specifically():
    # "1.07V/U" is in the shipped economist_forecaster article.
    assert _render("V/U", 1.07) == "1.07 V/U"


def test_unknown_units_render_with_a_separator():
    for unit, expect in [("V/U-1", "1.05 V/U-1"), ("rate", "1.05 rate"),
                         ("x1000", "1.05 x1000"), ("net fraction", "1.05 net fraction")]:
        assert _render(unit) == expect, unit


def test_known_units_are_unchanged():
    assert _render("%") == "1.05%"
    assert _render("pp") == "+1.05pp"
    assert _render("$") == "$1.05"
    assert _render("ratio") == "1.1×"
    assert _render("prob") == "105%"


def test_an_unknown_unit_stays_citable():
    # Refusing would drop the number from _citable's menu (agentic.py:61 keeps only renderings with
    # %$×σ° or a letter) — a silent loss. It must render, and it must be legible.
    r = _render("net fraction")
    assert any(c in "%$×σ°" or c.isalpha() for c in r)
