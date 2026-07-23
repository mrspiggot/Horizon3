"""The ATS release harvester is cross-jurisdiction by construction — the regression guard for the
US-centrism that once sat at the mouth of the funnel (harvest._fred_releases: FRED-only, jurisdiction
hardcoded "US"). Hermetic: drives `_data_releases` off a fixture calendar, no DB / UMD / LLM.
"""
from __future__ import annotations

from datetime import date

import pytest

from render.ats import harvest, vocab
from render.ats.harvest import HarvestContext

_FIXTURE = """
generated: "2026-07-20"
horizon_months: 9
releases:
  - {id: us_cpi, jurisdiction: US, name: "Consumer Price Index (CPI)", category: inflation,
     domain: inflation, tier: 1, cadence: "x", upcoming: ["2026-07-25"], confidence: high, provenance: p}
  - {id: eu_hicp, jurisdiction: EU, name: "HICP flash estimate", category: inflation,
     domain: inflation, tier: 1, cadence: "x", upcoming: ["2026-07-24"], confidence: medium, provenance: p}
  - {id: gb_cpi, jurisdiction: GB, name: "UK CPI", category: inflation,
     domain: inflation, tier: 1, cadence: "x", upcoming: ["2026-07-26"], confidence: high, provenance: p}
  - {id: jp_boj, jurisdiction: JP, name: "BoJ policy-rate decision", category: rates,
     domain: rates, tier: 1, cadence: "x", upcoming: ["2026-07-28"], confidence: high, provenance: p}
"""


@pytest.fixture()
def calendar(tmp_path, monkeypatch):
    f = tmp_path / "release_calendar.yaml"
    f.write_text(_FIXTURE)
    monkeypatch.setattr(harvest, "_RELEASE_CALENDAR", f)
    return HarvestContext(as_of=date(2026, 7, 20), lookahead_days=14)


def test_releases_span_every_jurisdiction(calendar):
    cands = harvest._data_releases(calendar, exclude_rate_keys=set())
    jurs = {c.jurisdiction for c in cands}
    assert jurs == {"US", "EU", "GB", "JP"}          # cross-jurisdiction by construction
    assert jurs != {"US"}                              # never US-only


def test_titles_are_data_driven_not_us_literal(calendar):
    cands = harvest._data_releases(calendar, exclude_rate_keys=set())
    for c in cands:
        assert not c.title.startswith("US ")           # the old `f"US {name}"` is gone
    reader = {c.jurisdiction: c.title for c in cands}
    # each title names the jurisdiction's OWN central bank, read live from jurisdictions.yaml vocab
    assert "the Fed" in reader["US"]
    assert "the ECB" in reader["EU"]
    assert "the Bank of England" in reader["GB"]


def test_cb_decisions_are_deduped_against_cb_meetings(calendar):
    # a rates release whose (jurisdiction, date) was already emitted as a decision by _cb_meetings is
    # skipped — reconciled with UMD, never double-counted.
    key = {("JP", date(2026, 7, 28))}
    cands = harvest._data_releases(calendar, exclude_rate_keys=key)
    assert "JP" not in {c.jurisdiction for c in cands}
    assert {c.jurisdiction for c in cands} == {"US", "EU", "GB"}


def test_out_of_window_release_is_dropped(calendar):
    # lookahead is 14 days from 2026-07-20 → 2026-08-03; a later date must not surface.
    ctx = HarvestContext(as_of=date(2026, 7, 20), lookahead_days=2)   # only through 2026-07-22
    cands = harvest._data_releases(ctx, exclude_rate_keys=set())
    assert cands == []                                 # all fixture dates are 24–28 Jul, beyond +2d


def test_probe_signature_takes_a_jurisdiction():
    # the readiness gate must be able to probe a candidate's OWN jurisdiction (not instance="US").
    import inspect

    from render.ats import readiness
    assert "jurisdiction" in inspect.signature(readiness.probe).parameters


def test_jurisdiction_vocab_is_read_live_for_each_region():
    assert vocab.jurisdiction_vocab("GB").get("cb_the") == "the Bank of England"
    assert vocab.jurisdiction_vocab("JP").get("cb_the") == "the Bank of Japan"
    assert vocab.jurisdiction_vocab("ZZ") == {}         # unknown ⇒ {}, no default
