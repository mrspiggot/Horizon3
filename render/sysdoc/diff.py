"""Manifest → manifest architecture changelog.

Compares two manifest dicts (committed vs freshly built, or two versions) and reports
what changed. Separates *code/architecture* changes (graphs, ats, schemas, catalog —
what the drift-gate cares about) from *data* changes (the spine census, which shifts
with UMD data, not code).
"""
from __future__ import annotations


def _by(seq, key):
    return {item[key]: item for item in seq}


def _edge_set(graph):
    return {(e["source"], e["target"], bool(e.get("conditional", False))) for e in graph.get("edges", [])}


def _graph_lines(old, new):
    lines = []
    og, ng = _by(old.get("graphs", []), "name"), _by(new.get("graphs", []), "name")
    for name in sorted(set(og) | set(ng)):
        if name not in og:
            lines.append(f"+ graph `{name}` added")
            continue
        if name not in ng:
            lines.append(f"- graph `{name}` removed")
            continue
        o, n = og[name], ng[name]
        on, nn = _by(o["nodes"], "id"), _by(n["nodes"], "id")
        for nid in sorted(set(nn) - set(on)):
            lines.append(f"  [{name}] + node `{nid}` ({nn[nid]['kind']})")
        for nid in sorted(set(on) - set(nn)):
            lines.append(f"  [{name}] - node `{nid}`")
        for nid in sorted(set(on) & set(nn)):
            if on[nid]["kind"] != nn[nid]["kind"]:
                lines.append(f"  [{name}] ~ node `{nid}` kind {on[nid]['kind']} → {nn[nid]['kind']}")
            if on[nid].get("schemas") != nn[nid].get("schemas"):
                lines.append(f"  [{name}] ~ node `{nid}` schema {on[nid].get('schemas')} → {nn[nid].get('schemas')}")
            if bool(on[nid].get("is_gate")) != bool(nn[nid].get("is_gate")):
                lines.append(f"  [{name}] ~ node `{nid}` gate {on[nid].get('is_gate')} → {nn[nid].get('is_gate')}")
        oe, ne = _edge_set(o), _edge_set(n)
        for s, t, c in sorted(ne - oe):
            lines.append(f"  [{name}] + edge {s} {'-.->' if c else '-->'} {t}")
        for s, t, c in sorted(oe - ne):
            lines.append(f"  [{name}] - edge {s} {'-.->' if c else '-->'} {t}")
    return lines


def _ats_lines(old, new):
    o, n = old.get("ats", {}).get("stages", []), new.get("ats", {}).get("stages", [])
    return [f"  [ats] stages {o} → {n}"] if o != n else []


def _schema_lines(old, new):
    lines = []
    os_, ns = _by(old.get("schemas", []), "name"), _by(new.get("schemas", []), "name")
    for name in sorted(set(ns) - set(os_)):
        lines.append(f"+ schema `{name}` ({ns[name]['module']})")
    for name in sorted(set(os_) - set(ns)):
        lines.append(f"- schema `{name}`")
    for name in sorted(set(os_) & set(ns)):
        of = {f["name"] for f in os_[name]["fields"]}
        nf = {f["name"] for f in ns[name]["fields"]}
        for f in sorted(nf - of):
            lines.append(f"  [{name}] + field `{f}`")
        for f in sorted(of - nf):
            lines.append(f"  [{name}] - field `{f}`")
    return lines


def _catalog_lines(old, new):
    lines = []
    oc, nc = old.get("catalog", {}), new.get("catalog", {})
    for k in ("graph_models", "design_models", "personas"):
        if oc.get(k) != nc.get(k):
            lines.append(f"  catalog.{k}: {oc.get(k)} → {nc.get(k)}")
    return lines


def _spine_lines(old, new):
    lines = []
    os_, ns = old.get("spine", {}), new.get("spine", {})
    if not (os_.get("online") and ns.get("online")):
        return lines  # can't compare a census we didn't run
    for k in ("executable_models", "proven_cells"):
        if os_.get(k) != ns.get(k):
            lines.append(f"  spine.{k}: {os_.get(k)} → {ns.get(k)}")
    for k in ("labels", "rel_types"):
        added = set(ns.get(k, [])) - set(os_.get(k, []))
        removed = set(os_.get(k, [])) - set(ns.get(k, []))
        for v in sorted(added):
            lines.append(f"  + spine {k[:-1]} `{v}`")
        for v in sorted(removed):
            lines.append(f"  - spine {k[:-1]} `{v}`")
    return lines


def diff_manifests(old: dict, new: dict) -> dict:
    """Returns {code_changed, code_lines, spine_lines, version} for the gate + changelog."""
    code_lines = (_graph_lines(old, new) + _ats_lines(old, new)
                  + _schema_lines(old, new) + _catalog_lines(old, new))
    spine_lines = _spine_lines(old, new)
    ov, nv = old.get("version", {}), new.get("version", {})
    return {
        "code_changed": bool(code_lines),
        "code_lines": code_lines,
        "spine_lines": spine_lines,
        "version": f"{ov.get('git_sha','?')} → {nv.get('git_sha','?')}",
    }
