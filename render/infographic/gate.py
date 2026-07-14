"""Tier-1 acceptance gate — deterministic, no LLM, runs on every render.

This is the Horizon2 firewall. H2 drew its infographic with a diffusion model and OCR-checked the
garbled numbers after the fact. Here numbers are literal DOM text, so we verify by DOM inspection:
every ``.num`` span must equal ``fmt(data-val)`` and resolve to a real executed output; no number may
sit inside the illustration slot; the required blocks and units must be present. ``emit`` RAISES on
any violation — a defective infographic can never reach a human (the ACS lint-gate pattern).
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .render_html import html_to_png, render_html
from .schema import InfographicSpec

_DIGITS = re.compile(r"-?\d[\d,]*\.?\d*")
# a "data leak" in prose = a decimal or a unit-suffixed number (what a real figure looks like).
# Bare integers (counts) and 4-digit years are fine — this is the H2-class leak, not enumeration.
_LEAK = re.compile(r"\d+\.\d+|\d+\s?(?:%|pp|bp|bps|×|σ)")
# equivocation a real publication would never print — a decisive read, or none.
_HEDGE = re.compile(r"\b(one reading|one interpretation|one could argue|arguably|on balance|"
                    r"broadly speaking|it may be that|some would say)\b", re.I)


def _fmt(fmt: str, val: float, unit: str) -> str:
    try:
        s = fmt.format(val)
    except Exception:
        s = str(val)
    return f"{s}{unit}" if unit and unit not in s else s


def lint_infographic(spec: InfographicSpec, html: str,
                     valid_sources: set[str] | None = None) -> list[str]:
    """Return every craft/provenance violation. Empty ⇒ the page may ship."""
    p: list[str] = []

    # ── structure ──────────────────────────────────────────────────────────────
    if not spec.title.strip():
        p.append("headline (title) is empty")
    if not spec.blocks_of("thesis_callout"):
        p.append("no thesis_callout block")
    tiles = spec.blocks_of("kpi_tile")
    ladder_rungs = sum(len(b.numbers) for b in spec.blocks_of("ranked_table"))
    # the page needs a quantitative spine: ≥3 KPI tiles, OR a ranked table of ≥3 rungs (ladder family)
    if len(tiles) < 3 and ladder_rungs < 3:
        p.append(f"needs ≥3 KPI tiles or a ≥3-rung ranked table, has {len(tiles)} tiles / {ladder_rungs} rungs")
    if not spec.blocks_of("chart_embed"):
        p.append("no chart embedded")
    if not spec.blocks_of("source"):
        p.append("no source/provenance block")

    # ── every number is provenance-traced & dimensioned ────────────────────────
    for n in spec.all_numbers():
        if not n.source.strip():
            p.append(f"number {n.name!r} has no source")
        elif valid_sources is not None and n.source not in valid_sources:
            p.append(f"number {n.name!r} source {n.source!r} is not an executed output")
    for t in tiles:
        if not t.numbers:
            p.append(f"KPI tile {t.id!r} has no number")
        elif not any(c in "%$×σ°" or c.isalpha() for c in t.numbers[0].rendered()):
            p.append(f"KPI tile {t.id!r} hero number {t.numbers[0].rendered()!r} carries no unit/dimension")

    # ── DOM verification (the H2 test) ─────────────────────────────────────────
    soup = BeautifulSoup(html, "html.parser")
    spans = soup.select("span.num")
    # every NumberObject must be rendered at least once (no silent drop); a token cited twice is fine
    rendered_srcs = {s.get("data-src", "") for s in spans}
    for n in spec.all_numbers():
        if n.source not in rendered_srcs:
            p.append(f"NumberObject {n.source!r} was dropped (never rendered)")
    for s in spans:
        dv, fmt = s.get("data-val"), s.get("data-fmt", "{:+.2f}")
        src, txt = s.get("data-src", ""), s.get_text().strip()
        if dv is None:
            p.append(f"rendered number {txt!r} carries no data-val"); continue
        # recompute the numeric core purely from data-val + data-fmt, compare to the visible text
        try:
            core = fmt.format(float(dv))
        except Exception:
            p.append(f"rendered number {txt!r} has non-numeric data-val {dv!r}"); continue
        if core not in txt:
            p.append(f"rendered {txt!r} ≠ fmt(data-val)={core!r} — number/render mismatch")
        if not src.strip():
            p.append(f"rendered number {txt!r} has no data-src provenance")

    # ── no number may live inside the illustration slot (diffusion isolation) ──
    for illus in soup.select("[data-illustration]"):
        if illus.select("span.num") or _DIGITS.search(re.sub(r"\s", "", illus.get_text())):
            p.append("a number/digit appears inside the illustration slot (diffusion isolation broken)")

    # ── an unfilled {placeholder} means a template leaked to the page ─────────
    if "{" in soup.get_text() or "}" in soup.get_text():
        p.append("an unfilled {placeholder} template remains in the rendered page")

    # ── data numbers in prose that are NOT NumberObjects (the H2-class leak) ───
    for node in soup.select(".callout, .note p, .tile .s, .deck"):
        prose = "".join(t for t in node.find_all(string=True, recursive=True)
                        if not (t.parent and "num" in (t.parent.get("class") or [])))
        m = _LEAK.search(prose)
        if m:
            p.append(f"un-traced data number {m.group()!r} in prose (must be a NumberObject)")
        h = _HEDGE.search(prose)
        if h:
            p.append(f"equivocation {h.group()!r} in reader copy — make a call, not a shrug")
    return p


def emit(spec: InfographicSpec, out_png: str, valid_sources: set[str] | None = None) -> str:
    """Render → lint → rasterise. RAISES if the tier-1 gate finds any violation."""
    html = render_html(spec)
    problems = lint_infographic(spec, html, valid_sources)
    if problems:
        raise ValueError("AIS TIER-1 GATE FAILED — refusing to emit:\n  - " + "\n  - ".join(problems))
    return html_to_png(html, out_png)
