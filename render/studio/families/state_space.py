"""The STATE-SPACE structure-family: the §10 principle made visual.

Every input is a STATE, not a level (assessment §10): its level, its direction/speed, its
acceleration, and where the level sits in its own history. This family plots a set of
variables in that state space at once — a regime quadrant of level-extremity (z-score, x)
against momentum (standardised 3-month change, y). The four quadrants read as regimes:
hot & heating, hot but cooling, cold but warming, cold & cooling.

One lint refuses axes without units (both are in σ), fewer than three variables, or missing
quadrant guidance — a scatter of unlabelled dots (the failure that shipped once) cannot pass.
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patheffects as pe

INK = "#16161d"
_HALO = [pe.Stroke(linewidth=2.4, foreground="white"), pe.Normal()]


@dataclass
class StatePoint:
    label: str
    x: float          # level z-score (σ vs own history)
    y: float          # momentum: 3m change / series σ
    accel: float      # sign → accelerating / decelerating
    reading: str      # one-line §10 reading


@dataclass
class StateSpaceSpec:
    title: str
    subtitle: str
    xlabel: str
    ylabel: str
    source: str
    footer: str
    quadrants: dict = field(default_factory=lambda: {
        "tr": "HOT & HEATING", "br": "HOT, COOLING", "tl": "COLD, WARMING", "bl": "COLD & COOLING"})


def _reader_safe(s: str) -> str:
    """Strip internal notation that must never reach a reader — assessment section refs (§10) and code
    identifiers (state_tuple). The v6 review caught '§10 STATE / §10 state_tuple' in a dashboard scatter."""
    s = re.sub(r"§\s*\d+\s*", "", s or "")
    s = re.sub(r"\bstate_tuple\b", "state", s, flags=re.I)
    return re.sub(r"\s{2,}", " ", s).strip()


def lint_state_space(spec: StateSpaceSpec, points: list[StatePoint]) -> list[str]:
    p = []
    for axis, lbl in (("x", spec.xlabel), ("y", spec.ylabel)):
        if not lbl.strip():
            p.append(f"{axis}-axis label is empty")
        elif not any(u in lbl for u in ("σ", "sigma", "z-", "score", "%", "pp")):
            p.append(f"{axis}-axis label states no unit: {lbl!r}")
    if len([pt for pt in points if np.isfinite(pt.x) and np.isfinite(pt.y)]) < 3:
        p.append("fewer than 3 finite state points — not a regime map")
    if len(spec.quadrants) < 4:
        p.append("quadrant guidance missing (an unlabelled scatter is forbidden)")
    return p


def render_state_space(points: list[StatePoint], spec: StateSpaceSpec, out: str) -> str:
    problems = lint_state_space(spec, points)
    if problems:
        raise ValueError("CRAFT LINT FAILED — refusing to render:\n  - " + "\n  - ".join(problems))
    pts = [pt for pt in points if np.isfinite(pt.x) and np.isfinite(pt.y)]

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "axes.edgecolor": "#8a8a93", "text.color": INK, "axes.labelcolor": INK,
        "xtick.color": "#55555c", "ytick.color": "#55555c",
    })
    fig, (ax, axk) = plt.subplots(1, 2, figsize=(13.8, 8.4), dpi=200,
                                  gridspec_kw={"width_ratios": [1.95, 1.0]})
    fig.subplots_adjust(left=0.072, right=0.985, top=0.80, bottom=0.095, wspace=0.04)

    xm = max(2.6, max(abs(pt.x) for pt in pts) * 1.28)
    ym = max(2.2, max(abs(pt.y) for pt in pts) * 1.35)
    ax.set_xlim(-xm, xm); ax.set_ylim(-ym, ym)

    # quadrant tints (warm right = elevated vs history, cool left = depressed) + corner guidance
    ax.axhspan(0, ym, xmin=0.5, xmax=1.0, color="#D55E00", alpha=0.05, zorder=0)
    ax.axhspan(-ym, 0, xmin=0.5, xmax=1.0, color="#D98A00", alpha=0.05, zorder=0)
    ax.axhspan(0, ym, xmin=0.0, xmax=0.5, color="#4C6EA8", alpha=0.05, zorder=0)
    ax.axhspan(-ym, 0, xmin=0.0, xmax=0.5, color="#7089b0", alpha=0.05, zorder=0)
    ax.axhline(0, color="#6b6b73", lw=1.0, ls=(0, (4, 3)), zorder=1)
    ax.axvline(0, color="#6b6b73", lw=1.0, ls=(0, (4, 3)), zorder=1)
    corners = {"tr": (0.985, 0.975, "right", "top"), "br": (0.985, 0.02, "right", "bottom"),
               "tl": (0.015, 0.975, "left", "top"), "bl": (0.015, 0.02, "left", "bottom")}
    for key, (fx, fy, ha, va) in corners.items():
        ax.text(fx, fy, spec.quadrants.get(key, ""), transform=ax.transAxes, fontsize=10.5,
                fontweight="bold", color="#9a9aa2", ha=ha, va=va, zorder=1)

    # numbered markers (labels live in the side key — avoids the label pile-up)
    for i, pt in enumerate(pts, 1):
        acc = "#D55E00" if pt.accel > 0 else "#4C6EA8"
        ax.scatter([pt.x], [pt.y], s=310, color=acc, edgecolor="white", linewidth=1.4, zorder=5)
        ax.text(pt.x, pt.y, str(i), color="white", fontsize=9.5, fontweight="bold",
                ha="center", va="center", zorder=6)

    ax.grid(True, color="#e4e4ea", lw=0.7, zorder=0); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_xlabel(spec.xlabel, fontsize=11.5); ax.set_ylabel(spec.ylabel, fontsize=11.5)
    ax.tick_params(labelsize=10)

    # ── side key ──────────────────────────────────────────────────────────────────
    axk.axis("off"); axk.set_xlim(0, 1); axk.set_ylim(0, 1)
    n = len(pts)
    axk.text(0.0, 0.985, f"the {n} inputs, read as states", fontsize=10.5, fontweight="bold",
             color="#4a4a52", va="top")
    y = 0.92
    dy = min(0.108, 0.86 / max(n, 1))
    for i, pt in enumerate(pts, 1):
        acc = "#D55E00" if pt.accel > 0 else "#4C6EA8"
        axk.scatter([0.03], [y], s=250, color=acc, edgecolor="white", linewidth=1.2,
                    transform=axk.transAxes, clip_on=False)
        axk.text(0.03, y, str(i), color="white", fontsize=8.6, fontweight="bold",
                 ha="center", va="center", transform=axk.transAxes)
        axk.text(0.10, y + 0.012, pt.label, fontsize=9.8, fontweight="bold", color=INK, va="center")
        axk.text(0.10, y - 0.028, _reader_safe(pt.reading), fontsize=8.6, color="#6a6a72", va="center")
        y -= dy
    axk.scatter([0.03], [0.02], s=120, color="#D55E00", transform=axk.transAxes, clip_on=False)
    axk.scatter([0.42], [0.02], s=120, color="#4C6EA8", transform=axk.transAxes, clip_on=False)
    axk.text(0.07, 0.02, "accelerating", fontsize=8.6, color="#6a6a72", va="center")
    axk.text(0.46, 0.02, "decelerating", fontsize=8.6, color="#6a6a72", va="center")

    fig.text(0.072, 0.945, _reader_safe(spec.title), fontsize=18, fontweight="bold", color=INK)
    sub = "\n".join(textwrap.wrap(_reader_safe(spec.subtitle), width=118)[:2])
    fig.text(0.072, 0.875, sub, fontsize=10.8, color="#4a4a52", linespacing=1.32, va="top")
    fig.text(0.072, 0.028, spec.source, fontsize=8.2, color="#8a8a93")
    fig.text(0.072, 0.008, spec.footer, fontsize=8.2, color="#8a8a93", style="italic")

    fig.savefig(out, dpi=200, facecolor="white"); plt.close(fig)
    return out
