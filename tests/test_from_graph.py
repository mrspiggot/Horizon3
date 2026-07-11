"""Tests for the graph-driven renderer — deterministic, with stub ModelRuns (no DB, no Executor)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "PycharmProjects/unified_market_data/src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unified_market_data.analysis.executor import ModelRun  # noqa: E402
from unified_market_data.analysis.state import State  # noqa: E402
from render import from_graph  # noqa: E402


def _run(as_of, taylor, funds, cpi_level, gap):
    cpi = State(level=cpi_level, direction=0.1, acceleration=0.0, zscore=0.0, percentile=0.5,
                step=1, window=36, n=36, as_of=as_of)
    return ModelRun("reaction_function", inputs={"cpi": cpi, "policy": State(
        funds, 0, 0, 0, 0.5, 1, 12, 12, as_of), "gap": gap},
        outputs={"taylor_1993": taylor}, as_of=as_of)


HIST = [_run("2024-01-01", 4.0, 3.5, 2.8, 0.5),
        _run("2024-06-01", 4.5, 4.0, 3.0, 0.8),
        _run("2026-05-01", 4.9, 3.6, 3.1, 1.0)]


def test_val_resolves_outputs_inputs_and_scalars():
    r = HIST[-1]
    assert from_graph._val(r, "output:taylor_1993") == 4.9
    assert from_graph._val(r, "input:policy.level") == 3.6
    assert from_graph._val(r, "input:cpi.direction") == 0.1
    assert from_graph._val(r, "input:gap") == 1.0       # derived scalar
    assert from_graph._val(r, "as_of") == "2026-05-01"
    assert from_graph._val(r, 42) == 42                  # literal


def test_renders_all_four_kinds(tmp_path):
    specs = [
        {"id": "fan-vs-funds", "color_job": "categorical", "data_contract": {
            "kind": "series", "ylabel": "%", "series": [
                {"label": "Taylor '93", "from": "output:taylor_1993"},
                {"label": "funds", "from": "input:policy.level", "style": "dashed"}]}},
        {"id": "inputs", "data_contract": {"kind": "series", "series": [
            {"label": "cpi", "from": "input:cpi.level"}, {"label": "gap", "from": "input:gap"}]}},
        {"id": "snapshot", "color_job": "sequential", "data_contract": {
            "kind": "named_values", "labels": ["Taylor", "funds"],
            "values": ["output:taylor_1993", "input:policy.level"], "ref": "input:policy.level"}},
        {"id": "gap", "color_job": "diverging", "data_contract": {
            "kind": "gap_series", "minuend": "output:taylor_1993",
            "subtrahend": "input:policy.level", "label": "Taylor - funds"}},
    ]
    out = tmp_path / "stub.png"
    from_graph.render_model(HIST, specs, str(out), suptitle="stub")
    assert out.exists() and out.stat().st_size > 2000
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_empty_history_refused(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        from_graph.render_model([], [], str(tmp_path / "x.png"))
