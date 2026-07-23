"""The infographic acceptance layer, split correctly: the tier-1 GATE verifies FACTS deterministically
(numbers == fmt(data-val), provenance, structure); whether the PROSE is decisive or a shrug is a JUDGMENT
that belongs to an agent, not a regex blocklist. These lock that split after the `_HEDGE` regex convicted
the decisive line "Four published models, one reading of where policy stands" as a hedge.
"""
from __future__ import annotations

from render.infographic import editorial, gate
from render.infographic.schema import Block, InfographicSpec


def test_gate_no_longer_carries_an_editorial_phrase_blocklist():
    assert not hasattr(gate, "_HEDGE")                       # the convicting regex is gone
    src = open(gate.__file__).read()
    assert "one reading" not in src                          # no phrase blocklist remains in the fact-gate


def test_editorial_review_fails_open_without_a_model(monkeypatch):
    # an LLM outage (or the off-switch) must never block a render — the deterministic gate still guards facts.
    monkeypatch.setenv("HORIZON3_NO_EDITORIAL", "1")
    spec = InfographicSpec(persona="central_bank_policymaker", title="The ECB versus its own rulebook",
                           deck="Set the policy rate",
                           blocks=[Block(id="note", type="note",
                                         text="Four published models, one reading of where policy stands.")])
    out = editorial.review_and_repair(spec)
    assert out.blocks[0].text == "Four published models, one reading of where policy stands."


def test_editor_never_crosses_into_numbers_or_placeholders():
    # the guard that keeps wording (the LLM's job) and figures (the firewall's) apart
    assert editorial._NUMISH.search("the real policy rate is 1.2%")
    assert editorial._NUMISH.search("stance {reaction_function.policy}")
    assert not editorial._NUMISH.search("policy is running behind its own rulebook")


def test_reader_lines_are_exactly_the_editorial_surfaces():
    spec = InfographicSpec(persona="p", title="T", deck="D",
                           blocks=[Block(id="th", type="thesis_callout", text="Thesis."),
                                   Block(id="nt", type="note", text="The read."),
                                   Block(id="kpi", type="kpi_tile", title="Taylor 1993"),
                                   Block(id="src", type="source", text="Source: UMD.")])
    ids = {lid for lid, _ in editorial._reader_lines(spec)}
    assert ids == {"__title__", "__deck__", "th", "nt"}       # not the source or kpi blocks
