"""Catalog -> render bridge: a model's declared `visualizations` render automatically.

Each catalog viz spec names a chart (form/color_job/dim + optional canonical `chart_type`). This
maps the spec to a `render.charts` primitive and composes the figure from the model's verified
outputs. Charts thus flow straight from the model's DECLARATION — never hand-authored per model
(the H2 afterthought failure, designed out).

`data_by_viz_id` supplies each viz's numbers already shaped to that chart_type's data contract (the
Executor's job); this module owns the DISPATCH + styling from the spec.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import yaml  # noqa: E402

from . import charts  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parents[1] / "catalog" / "models"


# --- chart_type -> renderer (each wrapper unpacks a data dict = the chart's data contract) --------
def _fan(ax, d, fig=None, **st):
    return charts.fan_chart(ax, d["x"], d["median"], d["bands"], mean=d.get("mean"),
                            forward=d.get("forward"), spot=d.get("spot"),
                            xticklabels=d.get("xticklabels"), **st)


def _heatmap(ax, d, fig=None, **st):
    return charts.probability_heatmap(ax, d["matrix"], d["xticklabels"], d["y_levels"],
                                      modal=d.get("modal"), mean=d.get("mean"),
                                      forward=d.get("forward"), fig=fig, **st)


def _surface3d(ax, d, fig=None, **st):
    return charts.vol_surface_3d(ax, d["moneyness"], d["ttes"], d["Z"], **st)


def _smile(ax, d, fig=None, **st):
    return charts.vol_smile(ax, d["smiles"], **st)


def _lines(ax, d, fig=None, **st):
    return charts.overlay_lines(ax, d["x"], d["series"], band=d.get("band"),
                                xticklabels=d.get("xticklabels"),
                                zero_line=d.get("zero_line", False), **st)


def _bar(ax, d, fig=None, color_job="diverging", **st):
    return charts.bar(ax, d["labels"], d["values"], color_job=color_job, ref=d.get("ref"), **st)


def _dumbbell(ax, d, fig=None, **st):
    return charts.dumbbell(ax, d["labels"], d["left"], d["right"], **st)


CHART_RENDERERS = {
    "fan": _fan, "heatmap": _heatmap, "surface3d": _surface3d, "smile": _smile,
    "lines": _lines, "bar": _bar, "dumbbell": _dumbbell,
}
NEEDS_3D = {"surface3d"}

# form/id keyword -> chart_type (used when a spec has no explicit `chart_type`). Order matters:
# specific forms before the generic "lines".
_INFER = [
    ("fan", ["fan"]),
    ("surface3d", ["3d surface", "3-d surface"]),
    ("smile", ["smile"]),
    ("heatmap", ["heatmap"]),
    ("dumbbell", ["dumbbell", "lollipop"]),
    ("bar", ["bar", " bars"]),
    ("scatter", ["scatter"]),
    ("stacked_area", ["stacked area"]),
    ("table", ["table"]),
    ("lines", ["time series", "over time", "lines", "curve", "term structure", "smiles by",
               "reliability", "density", "loading", "ridge"]),
]


def chart_type_of(spec: dict) -> str | None:
    if spec.get("chart_type"):
        return spec["chart_type"]
    text = (str(spec.get("form", "")) + " " + str(spec.get("id", ""))).lower()
    for ct, kws in _INFER:
        if any(k in text for k in kws):
            return ct
    return None


def renderable(spec: dict) -> bool:
    return chart_type_of(spec) in CHART_RENDERERS


def model_viz_specs(model_id: str) -> list[dict]:
    doc = yaml.safe_load((MODELS_DIR / f"{model_id}.yaml").read_text())
    return doc.get("visualizations", []) or []


def render_spec(ax, spec: dict, data: dict, *, fig=None, title=None):
    ct = chart_type_of(spec)
    r = CHART_RENDERERS.get(ct)
    if r is None:
        raise ValueError(f"no renderer for chart_type {ct!r} (viz {spec.get('id')})")
    st = {"title": title} if title else {}
    if ct == "bar":
        st["color_job"] = spec.get("color_job", "diverging")
    return r(ax, data, fig=fig, **st)


def render_model(model_id: str, data_by_viz_id: dict, out_path: str, *, suptitle=None) -> str:
    """Render every declared viz for `model_id` for which data + a renderer exist; compose one figure."""
    specs = [s for s in model_viz_specs(model_id)
             if s.get("id") in data_by_viz_id and renderable(s)]
    if not specs:
        raise ValueError(f"{model_id}: no renderable viz with supplied data")
    n = len(specs)
    fig = plt.figure(figsize=(7.6 * n, 6.2))
    for i, spec in enumerate(specs):
        ct = chart_type_of(spec)
        ax = fig.add_subplot(1, n, i + 1, projection="3d" if ct in NEEDS_3D else None)
        render_spec(ax, spec, data_by_viz_id[spec["id"]], fig=fig, title=spec.get("id"))
    if suptitle:
        fig.suptitle(suptitle, fontsize=10.5, y=1.0)
    fig.savefig(out_path, dpi=140, bbox_inches="tight", facecolor="white")
    return out_path
