"""The release-calendar builder — deterministic fitter + projector, and the cross-jurisdiction guarantee.

No network: the fitter/projector are pure, and the build test drives off a controlled fixture taxonomy
(anchors/rule only — no UMD, no FRED). The point being proved is hard-rule #6 (generic, not FOMC): the
funnel produces releases for EVERY jurisdiction in the fixture, US among N, and an undiscoverable
release is written blank + `confidence: unknown` (hard-rule #2/#5: never a guessed date).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_release_calendar as brc  # noqa: E402

WD = brc.WEEKDAYS


# ── fitter: recovers the right recurrence family from observed history ─────────────────────────────────
def _series(rule: brc.Cadence, months: list[tuple[int, int]]) -> list[date]:
    return [d for (y, m) in months if (d := rule.apply(y, m))]


def test_fits_nth_weekday_first_friday():
    # Nonfarm-payrolls shape: the 1st Friday of each month.
    truth = brc.Cadence("nth_weekday", {"n": 1, "weekday": WD["fri"]})
    dates = _series(truth, [(2025, m) for m in range(1, 11)])
    rule, frac = brc.fit_cadence(dates)
    assert rule.family == "nth_weekday" and rule.params == {"n": 1, "weekday": WD["fri"]}
    assert frac == 1.0


def test_fits_third_wednesday_when_weekday_is_consistent():
    # An all-Wednesday release must never be labelled with an adjacent weekday (the calendar-coincidence
    # trap): the weekday filter forces a Wednesday rule.
    truth = brc.Cadence("nth_weekday", {"n": 3, "weekday": WD["wed"]})
    dates = _series(truth, [(2025, m) for m in range(1, 11)])
    rule, frac = brc.fit_cadence(dates)
    assert rule.family == "nth_weekday" and rule.params["weekday"] == WD["wed"]
    assert rule.params["n"] == 3 and frac == 1.0


def test_fits_last_working_day():
    truth = brc.Cadence("last_working_day")
    dates = _series(truth, [(2025, m) for m in range(1, 11)])
    rule, frac = brc.fit_cadence(dates)
    assert rule.family == "last_working_day" and frac == 1.0


def test_infers_quarterly_months_generically():
    # A release firing Feb/May/Aug/Nov (Japan GDP) is pinned to those months — no month privileged.
    dates = [date(2025, 2, 13), date(2025, 5, 14), date(2025, 8, 15), date(2025, 11, 14),
             date(2026, 2, 13)]
    assert brc._infer_months(dates) == (2, 5, 8, 11)
    rule, _ = brc.fit_cadence(dates)
    assert rule.months == (2, 5, 8, 11)
    # projection only lands in those months
    proj = brc.project(rule, date(2026, 3, 1), months=12)
    assert all(d.month in (2, 5, 8, 11) for d in proj)


def test_too_few_dates_is_unfittable():
    rule, frac = brc.fit_cadence([date(2025, 1, 3), date(2025, 2, 7)])
    assert rule is None and frac == 0.0


# ── projector: deterministic, forward, from as_of ──────────────────────────────────────────────────────
def test_projection_is_forward_and_on_rule():
    rule = brc.Cadence("nth_weekday", {"n": 1, "weekday": WD["fri"]})
    proj = brc.project(rule, date(2026, 7, 23), months=3)
    assert proj == [date(2026, 8, 7), date(2026, 9, 4), date(2026, 10, 2)]
    assert all(d >= date(2026, 7, 23) for d in proj)


# ── build: cross-jurisdiction by construction + the honest-unknown path ────────────────────────────────
_FIXTURE = """
releases:
  - id: us_cpi
    jurisdiction: US
    name: "US CPI"
    domain: inflation
    tier: 1
    discovery: {via: rule, cadence: "fixed_dom: 12", source: "test"}
  - id: eu_hicp
    jurisdiction: EU
    name: "Euro-area HICP flash"
    domain: inflation
    tier: 1
    discovery: {via: rule, cadence: "last_working_day", source: "test"}
  - id: gb_cpi
    jurisdiction: GB
    name: "UK CPI"
    domain: inflation
    tier: 1
    discovery:
      via: anchors
      source: "test"
      dates: ["2025-10-15", "2025-11-19", "2025-12-17", "2026-01-21", "2026-02-18", "2026-03-18"]
  - id: jp_cpi
    jurisdiction: JP
    name: "Japan CPI"
    domain: inflation
    tier: 1
    discovery: {via: rule, cadence: "fixed_dom: 19", source: "test"}
  - id: jp_unknown
    jurisdiction: JP
    name: "Undiscoverable release"
    domain: growth
    tier: 2
"""


def _build_fixture(tmp_path):
    tax = tmp_path / "release_taxonomy.yaml"
    tax.write_text(_FIXTURE)
    ctx = brc.BuildContext(as_of=date(2026, 7, 23), months=9)
    return {r["id"]: r for r in brc.build(ctx, taxonomy_path=tax)}


def test_build_is_cross_jurisdiction(tmp_path):
    recs = _build_fixture(tmp_path)
    resolved = {r["jurisdiction"] for r in recs.values() if r["confidence"] != "unknown"}
    assert {"US", "EU", "GB", "JP"} <= resolved            # every region produces a real candidate
    for jid in ("us_cpi", "eu_hicp", "gb_cpi", "jp_cpi"):
        assert recs[jid]["upcoming"], f"{jid} produced no forward dates"
        assert recs[jid]["jurisdiction"] == jid.split("_")[0].upper()


def test_undiscoverable_release_is_blank_and_flagged(tmp_path):
    recs = _build_fixture(tmp_path)
    u = recs["jp_unknown"]
    assert u["confidence"] == "unknown" and u["upcoming"] == [] and u["cadence"] == ""
    assert "not established" in u["provenance"]            # honest, never a guessed date


def test_no_us_default_release_carries_its_own_jurisdiction(tmp_path):
    recs = _build_fixture(tmp_path)
    assert recs["gb_cpi"]["jurisdiction"] == "GB"
    assert recs["jp_cpi"]["jurisdiction"] == "JP"
    # US is one row of N, not a fallback stamped onto others
    assert {r["jurisdiction"] for r in recs.values()} == {"US", "EU", "GB", "JP"}
