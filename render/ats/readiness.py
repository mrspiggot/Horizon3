"""The data-readiness gate — a candidate is only worth shortlisting if our estate can ground it NOW.

The firewall corollary: an article can only exist if its numbers exist. We probe the candidate's persona
with `persona_material` (the same executor the writer uses) and count the dimensioned salient numbers.
No such numbers ⇒ not groundable ⇒ excluded from ranking (logged, never force-written).
"""
from __future__ import annotations

from ..infographic.from_persona import persona_material
from . import vocab
from .schema import CandidateTrigger, ReadinessResult


def _probe_one(persona: str, conn, jur: str) -> ReadinessResult:
    try:
        mat = persona_material(persona, conn, instance=jur)
    except Exception as exc:
        return ReadinessResult(groundable=False, persona=persona, jurisdiction=jur,
                               note=str(exc).splitlines()[0][:80])
    numbers, salient = mat["numbers"], mat["salient"]
    dim = [k for k in salient if k in numbers
           and any(c in "%$×σ°" or c.isalpha() for c in numbers[k].rendered())]
    return ReadinessResult(groundable=len(dim) >= 1, persona=persona, jurisdiction=jur,
                           salient_count=len(dim), n_numbers=len(numbers), as_of=mat.get("as_of", ""))


def probe(persona: str, conn, jurisdiction: str | None = None) -> ReadinessResult:
    """Can our estate ground this persona NOW — in the candidate's OWN jurisdiction?

    A jurisdiction-bound trigger (a BoE decision, a euro-area HICP print) is probed on THAT
    jurisdiction's data — never on US data (the bug this replaces). A jurisdiction-AGNOSTIC trigger
    (zeitgeist theme, owner's paragraph) is probed across jurisdictions until one grounds it; it is
    groundable if ANY is, and we record that one. The probe order is rotated by the persona so no
    jurisdiction (least of all US) is systematically tried first — US is privileged nowhere.
    """
    if jurisdiction:
        return _probe_one(persona, conn, jurisdiction)
    jurs = [j["id"] for j in vocab.jurisdictions()]
    if jurs:
        off = sum(map(ord, persona)) % len(jurs)                # persona-seeded rotation, not US-first
        jurs = jurs[off:] + jurs[:off]
    first = None
    for j in jurs:
        r = _probe_one(persona, conn, j)
        first = first or r
        if r.groundable:                                        # short-circuit — bounded probing
            return r
    return first or ReadinessResult(groundable=False, persona=persona, note="no jurisdiction to probe")


def gate(cands: list[CandidateTrigger], conn) -> list[CandidateTrigger]:
    """Attach a ReadinessResult to each candidate (persona_material is memoised, so this is cheap).
    Each candidate is probed on its OWN jurisdiction (hard-rule #6): honestly excluded if its estate
    can't ground it, but on its own data — never convicted or saved by US numbers."""
    for c in cands:
        c.readiness = (probe(c.persona, conn, c.jurisdiction) if c.personas
                       else ReadinessResult(groundable=False, note="unmapped — no persona"))
    return cands
