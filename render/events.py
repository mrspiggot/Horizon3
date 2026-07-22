"""Macro event markers — dated anchors (GFC, COVID, market-specific pivots) drawn on time-series charts
and folded into each chart's insight, so the reader's eye and the prose point at the SAME moment.

DATA-driven and jurisdiction-aware: the markers live in `catalog/event_markers.yaml` (global set + a
per-jurisdiction set), read here. Only events INSIDE a chart's own data window are ever returned, so a
chart can never annotate a crisis its data does not span (the data-start firewall). Adding a market or an
event is a pure YAML edit — no code change, and never a US default.
"""
from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd
import yaml

_YAML = Path(__file__).resolve().parent.parent / "catalog" / "event_markers.yaml"


@functools.lru_cache(maxsize=1)
def _raw() -> dict:
    try:
        return yaml.safe_load(_YAML.read_text()) or {}
    except Exception:
        return {}


def events_for(instance: str | None, start, end) -> list[tuple[pd.Timestamp, str]]:
    """The (date, label) markers for `instance` that fall within [start, end], chronologically. Global
    events apply to every market; the jurisdiction's own are added. Empty list if none in window."""
    d = _raw()
    rows = list(d.get("global") or [])
    if instance:
        rows += list((d.get("by_jurisdiction") or {}).get(instance) or [])
    try:
        lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    except Exception:
        return []
    out: list[tuple[pd.Timestamp, str]] = []
    seen: set = set()
    for r in rows:
        try:
            ts = pd.Timestamp(str(r["date"]))
        except Exception:
            continue
        lbl = str(r.get("label", "")).strip()
        if lo <= ts <= hi and (ts, lbl) not in seen:
            seen.add((ts, lbl))
            out.append((ts, lbl))
    out.sort(key=lambda t: t[0])
    return out


def nearest_event(date, instance: str | None, start, end, *, within_days: int = 210):
    """The event label closest to `date` (within `within_days`), else None — for prose like 'crossed zero
    around the COVID shock'. Window-bounded like `events_for`."""
    evs = events_for(instance, start, end)
    if not evs:
        return None
    try:
        d = pd.Timestamp(date)
    except Exception:
        return None
    best, best_gap = None, None
    for ts, lbl in evs:
        gap = abs((d - ts).days)
        if gap <= within_days and (best_gap is None or gap < best_gap):
            best, best_gap = lbl, gap
    return best
