"""Role 4 — the Output table. Persist what the Executor produced, so something downstream can check it.

The engine (§06) is:

    Persona -> Model -> Inputs(§10 states) -> Executor -> [OUTPUT TABLE] -> Narrator + Renderers -> Judge

Everything to the right of the Output table is checked AGAINST it. Until now it did not exist:
`Executor.run_history` returned a list[ModelRun] that lived in memory for one article build and was
then discarded. So no component could verify anything — there was nothing to verify against. The
2026-07-14 batch shipped four claims contradicting their own charts and three numbers that were simply
wrong, and nothing was in a position to notice.

§06: "Every rendered number and every prose figure references a model_output_point — the audit trail
the Judge checks."

Two design points worth stating, because they are the reason this is useful rather than decorative:

  * THE WHOLE SERIES IS PERSISTED, not the latest scalar. "The most restrictive since the GFC" is a
    superlative over policy_stance's entire history; it cannot be adjudicated from one number. The
    output series IS the evidence. (~42k rows per full batch, ~3 MB, against an estate of 31.9M.)
  * REQUESTED AND DELIVERED ARE BOTH RECORDED. run_history silently skips any as-of where an input is
    thin. Storing only what was delivered would erase the evidence of a starved window — which is
    exactly how an 8-of-65 chart shipped captioned "through the tightening cycle".

This module WRITES; it does not decide. Refusal and adjudication belong to the render gate and the
Judge respectively.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import asdict, is_dataclass
from functools import lru_cache


@lru_cache(maxsize=1)
def _code_version() -> str:
    """The git sha of the executing tree — provenance for 'which code produced this number'."""
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return "unknown"


def _jsonable(x):
    if is_dataclass(x) and not isinstance(x, type):
        return asdict(x)
    return x


def _inputs_snapshot(spec) -> dict:
    """What each input actually bound to — the provenance a reader of the run needs to reproduce it."""
    out = {}
    for i in getattr(spec, "inputs", []) or []:
        out[i.id] = {"series_id": i.series_id, "source": i.source, "transform": i.transform,
                     "state": i.state, "context_window": i.context_window}
    return out


def record_run(conn, run: dict, *, instance: str | None = None) -> str | None:
    """Persist one executed model run + its full output series. Returns run_id (None if nothing ran).

    `run` is what render.graph_corpus.run_model returns.
    """
    history = run.get("history") or []
    meta = run.get("meta") or {}
    model_id = meta.get("model_id")
    if not model_id:
        return None

    cov = run.get("coverage") or {}
    hist_spec = meta.get("history") or {}
    inst = instance or run.get("instance")
    if not inst:
        raise ValueError(f"record_run: model {model_id!r} run carries no instance — "
                         f"refusing to persist it as US")
    run_id = str(uuid.uuid4())
    status = "failed" if not history else ("starved" if cov.get("starved") else "ok")

    spec = run.get("spec")
    spec_json = {"model_id": model_id, "name": meta.get("name"), "family": meta.get("family"),
                 "method": meta.get("method"), "grounded_in": meta.get("grounded_in"),
                 "equations": (meta.get("spec") or {}).get("equations"),
                 "implemented_by": (meta.get("execution") or {}).get("implemented_by"),
                 "outputs": meta.get("outputs")}

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO model_run (run_id, model_id, instance, as_of_start, as_of_end, cadence,
                                      requested, delivered, status, spec_json, params_json,
                                      inputs_snapshot, code_version)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (run_id, model_id, inst,
             (history[0].as_of[:10] if history else None),
             (history[-1].as_of[:10] if history else None),
             hist_spec.get("cadence", "monthly"),
             cov.get("requested"), cov.get("delivered"), status,
             json.dumps(spec_json, default=str),
             json.dumps((meta.get("spec") or {}).get("params") or {}, default=str),
             json.dumps(_inputs_snapshot(spec), default=str) if spec else None,
             _code_version()))

        units = {o.get("name"): o.get("unit") for o in (meta.get("outputs") or [])}
        rows = [(run_id, r.as_of[:10], name, (float(v) if v is not None else None), units.get(name))
                for r in history for name, v in (r.outputs or {}).items()]
        if rows:
            cur.executemany(
                "INSERT INTO model_output_point (run_id, as_of, name, value, unit) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", rows)
    conn.commit()
    return run_id


def output_series(conn, run_id: str, name: str) -> list[tuple]:
    """[(as_of, value)] for one output of one run — what the Judge adjudicates a shape claim against."""
    with conn.cursor() as cur:
        cur.execute("SELECT as_of, value FROM model_output_point WHERE run_id=%s AND name=%s "
                    "ORDER BY as_of", (run_id, name))
        return cur.fetchall()


def latest_run(conn, model_id: str, instance: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT run_id FROM model_run WHERE model_id=%s AND instance=%s "
                    "ORDER BY run_ts DESC LIMIT 1", (model_id, instance))
        row = cur.fetchone()
        return str(row[0]) if row else None
