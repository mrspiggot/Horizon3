"""Horizon3 deterministic rendering layer.

Verified numbers (a model's outputs) + a chart spec (a model's `visualizations` block) -> a polished
chart, by pure code. Reusable across every persona; the chart is Horizon3's differentiator.
"""
from . import charts, theme
from .charts import (
    fan_chart,
    overlay_lines,
    prob_ylim,
    probability_heatmap,
    vol_smile,
    vol_surface_3d,
)

__all__ = [
    "theme", "charts",
    "fan_chart", "probability_heatmap", "vol_surface_3d", "vol_smile", "overlay_lines", "prob_ylim",
]
