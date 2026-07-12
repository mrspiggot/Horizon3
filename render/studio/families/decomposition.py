"""The DECOMPOSITION structure-family: a model whose inputs COMBINE into its output.

A model of the form  output = c1 + c2 + … + cn  (signed contributions) always renders
the same way — signed contribution bands that sum to a net line, against an optional
reference line. This module is:

  * ``render_decomposition``  — the one deterministic renderer (no LLM, no diffusion),
  * ``lint_decomposition``    — the craft contract; a violation BLOCKS the render, so a
                                mislabelled axis / missing unit / undisclosed clip can
                                NEVER reach a human (Horizon2's failure mode),
  * ``spec_from_run``         — the catalog glue: turn an *authored* ``kind: decomposition``
                                chart + an *executed* ModelRun into a spec, generically.

Every value comes from the executed run; this module authors none. It is the first of the
four structure-families (decomposition / relationship / surface / state-space); the others
follow the same shape — one renderer + one lint each.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from ..from_model import _parse_ref, _value

INK, GRID = "#16161d", "#d7d7de"
_HALO = [pe.Stroke(linewidth=3.4, foreground="white"), pe.Normal()]
_UNIT_HINTS = ("%", "pp", "bp", "index", "$", "ratio", "σ", "z-", "prob")

# tone → colourblind-safe hue. Base/context is recessive slate; accents are Okabe-Ito.
_TONE = {"neutral": "#B8C4CE", "base": "#B8C4CE", "cool": "#4C6EA8", "warm": "#D55E00",
         "green": "#009E73", "amber": "#D98A00", "violet": "#8B6BB1"}
_TONE_ORDER = ["#B8C4CE", "#D55E00", "#009E73", "#4C6EA8", "#D98A00", "#8B6BB1"]


# ───────────────────────────────────────────────────────────────────────── spec
@dataclass
class Component:
    key: str
    label: str
    color: str


@dataclass
class DecompSpec:
    title: str
    subtitle: str
    xlabel: str
    ylabel: str
    components: list[Component]        # signed contributions that SUM to net_key
    net_key: str
    net_label: str
    actual_key: str | None
    actual_label: str | None
    source: str
    footer: str
    ylim: tuple[float, float]
    tick_years: int
    callouts: list[dict] = field(default_factory=list)    # {xy:(ts,y), xytext:(ts,y), text}
    end_labels: list[dict] = field(default_factory=list)   # {key, text, dy}
    clip_disclosed: bool = False


# ─────────────────────────────────────────────────────────────── generic helpers
def _envelopes(df: pd.DataFrame, spec: DecompSpec):
    pos = np.zeros(len(df)); neg = np.zeros(len(df))
    for c in spec.components:
        v = df[c.key].to_numpy(dtype=float)
        pos = pos + np.clip(v, 0, None)
        neg = neg + np.clip(v, None, 0)
    lines = [df[spec.net_key].to_numpy(dtype=float)]
    if spec.actual_key:
        lines.append(df[spec.actual_key].to_numpy(dtype=float))
    return pos, neg, np.maximum.reduce([pos] + lines), np.minimum.reduce([neg] + lines)


def _best_legend_corner(df: pd.DataFrame, spec: DecompSpec):
    """Auto-place the legend in the emptiest corner — one heuristic that generalises."""
    _, _, hi, lo = _envelopes(df, spec)
    n = len(df); h = n // 2
    cands = []
    for side, sl in (("left", slice(0, h)), ("right", slice(h, n))):
        cands.append((spec.ylim[1] - hi[sl].max(), f"upper {side}", side, "upper"))
        cands.append((lo[sl].min() - spec.ylim[0], f"lower {side}", side, "lower"))
    cands.sort(reverse=True)
    _, loc, side, vpos = cands[0]
    return loc, (0.010 if side == "left" else 0.990, 0.985 if vpos == "upper" else 0.02)


def lint_decomposition(spec: DecompSpec, df: pd.DataFrame) -> list[str]:
    """The deterministic craft contract. Any returned problem BLOCKS the render."""
    p = []
    if not spec.xlabel.strip():
        p.append("x-axis label is empty")
    if not spec.ylabel.strip():
        p.append("y-axis label is empty")
    if not any(u in spec.ylabel for u in _UNIT_HINTS):
        p.append(f"y-axis label states no unit: {spec.ylabel!r}")
    if len(spec.components) < 2:
        p.append("a decomposition needs ≥2 components (else it is a plain series)")
    for c in list(spec.components) + [Component(spec.net_key, spec.net_label, INK)]:
        if c.key not in df.columns:
            p.append(f"component/net {c.key!r} not present in the data")
    if any(c.key in df.columns for c in spec.components) and spec.net_key in df.columns:
        _, _, hi, lo = _envelopes(df, spec)
        net = df[spec.net_key].to_numpy(dtype=float)
        if net.max() > spec.ylim[1] + 1e-6 or net.min() < spec.ylim[0] - 1e-6:
            p.append("the net (model-output) line is clipped by ylim — always fatal")
        if (hi.max() > spec.ylim[1] + 1e-6 or lo.min() < spec.ylim[0] - 1e-6) and not spec.clip_disclosed:
            p.append("a contribution band is clipped but clip_disclosed=False (undisclosed masking)")
    return p


def render_decomposition(df: pd.DataFrame, spec: DecompSpec, out: str) -> str:
    problems = lint_decomposition(spec, df)
    if problems:
        raise ValueError("CRAFT LINT FAILED — refusing to render:\n  - " + "\n  - ".join(problems))

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "axes.edgecolor": "#8a8a93", "text.color": INK, "axes.labelcolor": INK,
        "xtick.color": "#55555c", "ytick.color": "#55555c",
    })
    fig, ax = plt.subplots(figsize=(13.2, 7.4), dpi=200)
    fig.subplots_adjust(left=0.075, right=0.885, top=0.80, bottom=0.135)
    t = df.index

    pos_base = np.zeros(len(df)); neg_base = np.zeros(len(df))
    for c in spec.components:
        v = df[c.key].to_numpy(dtype=float)
        pos = np.clip(v, 0, None); neg = np.clip(v, None, 0)
        ax.fill_between(t, pos_base, pos_base + pos, color=c.color, lw=0, zorder=2)
        ax.fill_between(t, neg_base, neg_base + neg, color=c.color, lw=0, zorder=2)
        pos_base = pos_base + pos; neg_base = neg_base + neg
    ax.axhline(0, color="#6b6b73", lw=1.0, zorder=3)

    ax.plot(t, df[spec.net_key], color=INK, lw=2.2, ls=(0, (5, 2)), zorder=5, path_effects=_HALO)
    if spec.actual_key:
        ax.plot(t, df[spec.actual_key], color=INK, lw=2.6, zorder=6, path_effects=_HALO)

    for el in spec.end_labels:
        ax.annotate(el["text"], (t[-1], df[el["key"]].iloc[-1]), xytext=(8, el.get("dy", 0)),
                    textcoords="offset points", fontsize=10.5, fontweight="bold", color=INK,
                    va="center", annotation_clip=False)

    bbox = dict(boxstyle="round,pad=0.35", fc="white", ec="#c8c8d0", lw=0.8, alpha=0.94)
    for co in spec.callouts:
        ax.annotate(co["text"], xy=co["xy"], xytext=co["xytext"], fontsize=9.3, color=INK, bbox=bbox,
                    ha="left", va="center", zorder=8, annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", color="#9a9aa2", lw=1.0))

    ax.set_ylim(*spec.ylim); ax.set_xlim(t[0], t[-1])
    ax.yaxis.grid(True, color=GRID, lw=0.8, zorder=0); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_ylabel(spec.ylabel, fontsize=11.5); ax.set_xlabel(spec.xlabel, fontsize=11.5)
    ax.xaxis.set_major_locator(mdates.YearLocator(spec.tick_years))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(labelsize=10)

    fig.text(0.075, 0.945, spec.title, fontsize=19, fontweight="bold", color=INK)
    fig.text(0.075, 0.885, spec.subtitle, fontsize=11.2, color="#4a4a52", linespacing=1.35)

    handles = [Patch(fc=c.color, label=c.label) for c in spec.components]
    handles.append(Line2D([], [], color=INK, lw=2.2, ls=(0, (5, 2)), label=spec.net_label))
    if spec.actual_key:
        handles.append(Line2D([], [], color=INK, lw=2.6, label=spec.actual_label))
    loc, anchor = _best_legend_corner(df, spec)
    leg = ax.legend(handles=handles, loc=loc, bbox_to_anchor=anchor, fontsize=9.8, frameon=True,
                    framealpha=0.92, edgecolor="#d7d7de", handlelength=1.7, labelspacing=0.72,
                    title="each band = one input the model reads", title_fontsize=9.6, alignment="left")
    leg.get_frame().set_facecolor("white"); leg.get_title().set_color("#4a4a52")

    fig.text(0.075, 0.038, spec.source, fontsize=8.2, color="#8a8a93")
    fig.text(0.075, 0.012, spec.footer, fontsize=8.2, color="#8a8a93", style="italic")
    fig.savefig(out, dpi=200, facecolor="white"); plt.close(fig)
    return out


# ───────────────────────────────────────────────────── catalog → spec (the glue)
def _tone_color(tone: str | None, i: int) -> str:
    if tone and tone in _TONE:
        return _TONE[tone]
    return _TONE_ORDER[i % len(_TONE_ORDER)]


def spec_from_run(model: dict, run: dict, chart_id: str,
                  persona_name: str = "") -> tuple[pd.DataFrame, DecompSpec] | None:
    """Build (df, DecompSpec) from an authored ``kind: decomposition`` chart + executed run.

    This is where generalisation lives: any model whose executor emits summable component
    outputs gets a rich, lint-clean decomposition chart with zero bespoke plotting code.
    """
    chart = next((c for c in run.get("charts", []) if c.get("id") == chart_id), None)
    history = run.get("history") or []
    if chart is None or not history:
        return None
    dc = chart.get("data_contract", {}) or {}
    if dc.get("kind") != "decomposition":
        return None

    comps = [(c["label"], _parse_ref(c["from"]), c.get("tone")) for c in dc.get("components", [])]
    comps = [(lab, rf, tone) for lab, rf, tone in comps if rf]
    net_ref = _parse_ref((dc.get("net") or {}).get("from", ""))
    ref = dc.get("reference") or {}
    ref_ref = _parse_ref(ref.get("from", "")) if ref else None
    if len(comps) < 2 or not net_ref:
        return None

    rows = []
    for r in history:
        row = {"date": pd.Timestamp(str(r.as_of)[:10])}
        for lab, rf, _ in comps:
            row[lab] = _value(r, *rf)
        row["__net__"] = _value(r, *net_ref)
        if ref_ref:
            row["__ref__"] = _value(r, *ref_ref)
        rows.append(row)
    df = pd.DataFrame(rows).set_index("date")
    need = [lab for lab, _, _ in comps] + ["__net__"]
    df = df.dropna(subset=need).astype(float, errors="ignore")
    if len(df) < 3:
        return None

    components = [Component(lab, lab, _tone_color(tone, i)) for i, (lab, _, tone) in enumerate(comps)]

    # y-limits: authored, else auto from the signed envelope with padding
    spec_stub = DecompSpec("", "", "Year", dc.get("ylabel", ""), components, "__net__", "", None, None,
                           "", "", (0, 1), 2)
    _, _, hi, lo = _envelopes(df, spec_stub)
    if dc.get("ylim"):
        ylim = tuple(dc["ylim"]); clip = bool(dc.get("clip_disclosed", False))
    else:
        pad = 0.08 * (hi.max() - lo.min() + 1e-9)
        ylim = (float(lo.min() - pad), float(hi.max() + pad)); clip = False

    span_years = (df.index[-1] - df.index[0]).days / 365.25
    unit = dc.get("unit") or (model.get("outputs", [{}])[0].get("unit", "%"))

    end_labels = []
    net_last = df["__net__"].iloc[-1]
    end_labels.append({"key": "__net__", "text": f"{_short(dc['net']['label'])}\n{net_last:.1f}{unit if unit=='%' else ''}",
                       "dy": 10 if not ref_ref else 12})
    if ref_ref:
        ref_last = df["__ref__"].iloc[-1]
        end_labels.append({"key": "__ref__", "text": f"{_short(ref['label'])}\n{ref_last:.1f}{unit if unit=='%' else ''}",
                           "dy": -12})

    callouts = []
    for co in dc.get("callouts", []) or []:
        callouts.append({"text": co["text"],
                         "xy": (pd.Timestamp(co["at"]), co["to_y"]),
                         "xytext": (pd.Timestamp(co["from"]), co["from_y"])})

    spec = DecompSpec(
        title=dc.get("title") or chart_id,
        subtitle=dc.get("subtitle", ""),
        xlabel="Year", ylabel=dc.get("ylabel", ""),
        components=components, net_key="__net__", net_label=(dc.get("net") or {}).get("label", "model output"),
        actual_key="__ref__" if ref_ref else None, actual_label=ref.get("label") if ref_ref else None,
        source=dc.get("source", f"Model: {model.get('name', model.get('model_id',''))}. "
                                f"Source: {', '.join(sorted({i.get('db_source','') for i in model.get('inputs', []) if i.get('db_source')}))}."),
        footer=dc.get("footer", "Every value is executed on data — nothing on this chart is authored by the model."),
        ylim=ylim, tick_years=(2 if span_years > 14 else 1), clip_disclosed=clip,
        end_labels=end_labels, callouts=callouts,
    )
    return df, spec


def _short(label: str) -> str:
    """A compact end-label token from a full legend label."""
    label = label.split("(")[0].strip()
    return label if len(label) <= 20 else label[:19] + "…"
