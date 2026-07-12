"""The Chart Studio — an agentic subsystem that decides HOW to visualise an executed insight.

Chart choice (given the number and shape of the variables AND the story being told) is a
reasoning problem, not a lookup table. A LangGraph agent graph deliberates and emits a
`ChartEncoding` (the grammar the agents reason in); a deterministic compiler renders it to
matplotlib, and a multimodal critic inspects the rendered pixels and revises. Grounded in the
2025–26 literature (Data-to-Dashboard's two-stage insight→chart debate, PlotGen's multimodal
feedback loop, the Mackinlay→Draco expressiveness/effectiveness tradition — all in
knowledge/). Rendering stays deterministic code; the LLM never authors a number.

Public surface:
- `ChartEncoding` (encoding.py) — the declarative chart spec the agents produce.
- `compile_encoding` (compile.py) — ChartEncoding → PNG, deterministic.
- `run_studio` (graph.py) — the agent graph: insight → best chart.  [added incrementally]
"""
from .compile import compile_encoding
from .encoding import ChartEncoding

__all__ = ["ChartEncoding", "compile_encoding"]
