#!/usr/bin/env python
"""Build an APPROXIMATE forward economic-release calendar, learned from history.

    build_release_calendar.py [--months N] [--preview] [--no-write]

Reads the owned taxonomy (`catalog/release_taxonomy.yaml`) — the master list of recurring data
releases and policy events for every jurisdiction, each with a `discovery:` hint saying WHERE its
dates come from — and writes the generated schedule (`catalog/release_calendar.yaml`) that the ATS
harvester (`render/ats/harvest.py`) consumes. Week-resolution (±a few days) is the design point: this
decides WHICH article to publish in a given week, not an intraday alert.

Honesty (CLAUDE.md hard-rule #2, extended: the engine never INVENTS a date; hard-rule #5: bad data is
refused at the boundary, never faked):
  - every projected date is either read from a real source (UMD scheduled list, FRED, or observed
    agency dates recorded in the taxonomy with provenance) or projected by DETERMINISTIC calendar
    arithmetic from a rule fitted to / declared from that real history;
  - a release whose cadence cannot be established is written with an EMPTY date list and
    `confidence: unknown` — left blank and flagged, never guessed;
  - the builder iterates jurisdictions generically from the taxonomy. US is one row of N, never a
    default or a template. Adding a jurisdiction or a release is a data edit, not a code change.

Discovery `via` adapters (each fails soft — an unreachable source ⇒ that release is `unknown`):
  cb_calendar  central-bank rate decisions, imported from UMD cb_meeting_calendars (the single source
               of truth; reconciled, never duplicated).
  anchors      real observed release dates gathered from the issuing agency's calendar (recorded in
               the taxonomy with a `source:` URL); the fitter derives the recurrence rule and projects.
  rule         an explicit, documented recurrence rule (e.g. Nonfarm Payrolls = 1st Friday) where a
               clean history could not be fetched; projected deterministically.
  fred         the FRED releases/dates API (live, re-runnable) for US releases FRED serves; with an
               optional `fallback:` (an anchors/rule block) so the release still resolves offline.
"""
from __future__ import annotations

import argparse
import calendar
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "catalog"
TAXONOMY = CATALOG / "release_taxonomy.yaml"
OUT = CATALOG / "release_calendar.yaml"

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
WD_NAMES = {v: k for k, v in WEEKDAYS.items()}
_FIT_TOL = 2          # days of slack when matching a rule to observed history (holidays nudge releases)


# ── calendar arithmetic (pure) ───────────────────────────────────────────────────────────────────────
def _nth_weekday(y: int, m: int, n: int, wd: int) -> date | None:
    """The n-th `wd` of month (y, m). n=-1 ⇒ the LAST such weekday. None if n-th does not exist."""
    if n == -1:
        d = date(y, m, calendar.monthrange(y, m)[1])
        while d.weekday() != wd:
            d -= timedelta(days=1)
        return d
    first = date(y, m, 1)
    day = 1 + (wd - first.weekday()) % 7 + (n - 1) * 7
    return date(y, m, day) if day <= calendar.monthrange(y, m)[1] else None


def _last_working_day(y: int, m: int) -> date:
    d = date(y, m, calendar.monthrange(y, m)[1])
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _fixed_dom(y: int, m: int, day: int) -> date:
    """The given day-of-month, snapped to the nearest working day (Sat→Fri, Sun→Mon)."""
    day = min(day, calendar.monthrange(y, m)[1])
    d = date(y, m, day)
    if d.weekday() == 5:
        d -= timedelta(days=1)
    elif d.weekday() == 6:
        d += timedelta(days=1)
    return d


def _occurrence(d: date) -> int:
    return (d.day - 1) // 7 + 1


def _is_last_weekday(d: date) -> bool:
    return d.day + 7 > calendar.monthrange(d.year, d.month)[1]


# ── cadence: a fitted or declared recurrence rule ──────────────────────────────────────────────────────
@dataclass
class Cadence:
    family: str                       # nth_weekday | last_working_day | fixed_dom
    params: dict = field(default_factory=dict)
    months: tuple[int, ...] | None = None   # None ⇒ every month; else the (quarterly/…) months it fires in

    def apply(self, y: int, m: int) -> date | None:
        if self.months is not None and m not in self.months:
            return None
        if self.family == "nth_weekday":
            return _nth_weekday(y, m, self.params["n"], self.params["weekday"])
        if self.family == "last_working_day":
            return _last_working_day(y, m)
        if self.family == "fixed_dom":
            return _fixed_dom(y, m, self.params["day"])
        return None

    def _scope(self) -> str:
        if self.months is None:
            return "monthly"
        names = ",".join(calendar.month_abbr[m] for m in sorted(self.months))
        return f"quarterly [{names}]" if len(self.months) == 4 else f"[{names}]"

    def human(self) -> str:
        if self.family == "nth_weekday":
            n, wd = self.params["n"], WD_NAMES[self.params["weekday"]]
            which = "last" if n == -1 else f"{n}"
            return f"nth_weekday: {{n: {which}, weekday: {wd}}} ({self._scope()})"
        if self.family == "last_working_day":
            return f"last_working_day of month ({self._scope()})"
        if self.family == "fixed_dom":
            return f"fixed_dom: {{day: {self.params['day']}}} nearest working day ({self._scope()})"
        return ""


def _infer_months(dates: list[date]) -> tuple[int, ...] | None:
    """A release firing in ≤6 distinct months over its history is periodic (quarterly/semiannual) —
    pin it to those months; otherwise treat it as monthly (None). Generic: Japan GDP fires
    Feb/May/Aug/Nov, the Tankan Apr/Jul/Oct/Dec — no month is privileged."""
    ms = sorted({d.month for d in dates})
    return None if len(ms) > 6 else tuple(ms)


def _candidate_rules(dates: list[date]) -> list[Cadence]:
    months = _infer_months(dates)
    # If the release lands on one weekday ≥70% of the time it HAS a publication weekday — only offer
    # nth_weekday rules on that weekday, so an adjacent weekday can't win the ±tol count by calendar
    # coincidence and mislabel a Wednesday release as "Tuesday". Mixed-weekday series (e.g. US CPI,
    # day-of-month driven) fall through to fixed_dom.
    wds = [d.weekday() for d in dates]
    mode_wd = max(set(wds), key=wds.count)
    wd_range = [mode_wd] if wds.count(mode_wd) / len(wds) >= 0.7 else range(5)
    cands = [Cadence("last_working_day", months=months)]
    for wd in wd_range:
        for n in (1, 2, 3, 4, -1):
            cands.append(Cadence("nth_weekday", {"n": n, "weekday": wd}, months=months))
    days = sorted(d.day for d in dates)
    cands.append(Cadence("fixed_dom", {"day": days[len(days) // 2]}, months=months))
    return cands


def fit_cadence(dates: list[date]) -> tuple[Cadence | None, float]:
    """Fit the best recurrence rule to observed release dates; return (rule, match_fraction).

    Each candidate predicts a date for every observed month; a prediction MATCHES within ±_FIT_TOL
    days (holidays shift releases a day or two). Rules are ranked by matches first, then by SMALLEST
    mean error — so when a release lands on the 3rd Wednesday, the exact-Wednesday rule beats an
    adjacent-weekday rule that also happens to fall within tolerance (otherwise the label lies and the
    projections skew a day or two). The fraction is the honesty signal — a poor fit becomes
    `confidence: unknown` upstream, not a guess.
    """
    ds = sorted(set(dates))
    if len(ds) < 3:
        return None, 0.0
    best, best_key = None, (-1, 0.0)
    for rule in _candidate_rules(ds):
        errs = [abs((p - d).days) for d in ds if (p := rule.apply(d.year, d.month)) is not None]
        if not errs:
            continue
        matches = sum(1 for e in errs if e <= _FIT_TOL)
        key = (matches, -sum(errs) / len(errs))       # more matches, then lower mean error
        if key > best_key:
            best, best_key = rule, key
    return best, (best_key[0] / len(ds) if best else 0.0)


def project(rule: Cadence, as_of: date, months: int) -> list[date]:
    """Project a rule forward `months` from `as_of` (inclusive). Deterministic calendar arithmetic."""
    out, y, m = [], as_of.year, as_of.month
    for i in range(months + 1):
        yy, mm = y + (m - 1 + i) // 12, (m - 1 + i) % 12 + 1
        p = rule.apply(yy, mm)
        if p and as_of <= p:
            out.append(p)
    return sorted(out)


def _confidence(frac: float) -> str:
    return "high" if frac >= 0.8 else "medium" if frac >= 0.6 else "unknown"


# ── discovery adapters (each returns a resolved record dict, failing soft to `unknown`) ────────────────
@dataclass
class BuildContext:
    as_of: date
    months: int = 9
    fred_key: str = ""


def _unknown(reason: str) -> dict:
    return {"cadence": "", "upcoming": [], "confidence": "unknown",
            "provenance": f"cadence not established — {reason}"}


def _from_dates(dates: list[date], ctx: BuildContext, source: str) -> dict:
    """Fit a rule to observed history and project it forward (the anchors path)."""
    rule, frac = fit_cadence(dates)
    conf = _confidence(frac)
    if rule is None or conf == "unknown":
        return _unknown(f"no clean recurrence in {len(dates)} observed dates ({source})")
    upcoming = project(rule, ctx.as_of, ctx.months)
    return {"cadence": rule.human(),
            "upcoming": [d.isoformat() for d in upcoming],
            "confidence": conf,
            "provenance": f"inferred from {len(dates)} past dates ({int(frac * 100)}% fit); {source}"}


def _adapt_anchors(disc: dict, ctx: BuildContext) -> dict:
    try:
        dates = sorted(date.fromisoformat(s) for s in disc.get("dates", []))
    except (ValueError, TypeError):
        return _unknown("un-parseable anchor dates in taxonomy")
    if len(dates) < 3:
        return _unknown("fewer than 3 anchor dates to fit a rule")
    return _from_dates(dates, ctx, disc.get("source", "agency release calendar"))


def _adapt_rule(disc: dict, ctx: BuildContext) -> dict:
    """An explicit, documented recurrence rule. Projected deterministically at `medium` confidence."""
    rule = _parse_rule(disc.get("cadence", ""), disc.get("months"))
    if rule is None:
        return _unknown(f"un-parseable cadence rule {disc.get('cadence')!r}")
    upcoming = project(rule, ctx.as_of, ctx.months)
    src = disc.get("source", "documented release convention")
    return {"cadence": rule.human(),
            "upcoming": [d.isoformat() for d in upcoming],
            "confidence": "medium", "provenance": f"documented rule; {src}"}


def _parse_rule(spec: str, months: list[int] | None) -> Cadence | None:
    """Parse a compact rule string from the taxonomy: 'nth_weekday: 1 fri' | 'last_working_day' |
    'fixed_dom: 19'. Optional `months:` (a list) pins it to those months (quarterly etc.); omitted =
    every month. Kept small and legible — the taxonomy is human-owned data."""
    spec = (spec or "").strip().lower()
    ms = tuple(months) if months else None
    if spec.startswith("last_working_day"):
        return Cadence("last_working_day", months=ms)
    if spec.startswith("fixed_dom"):
        try:
            return Cadence("fixed_dom", {"day": int(spec.split(":")[1])}, months=ms)
        except (IndexError, ValueError):
            return None
    if spec.startswith("nth_weekday"):
        try:
            _, rest = spec.split(":", 1)
            n_tok, wd_tok = rest.split()
            n = -1 if n_tok in ("last", "-1") else int(n_tok)
            return Cadence("nth_weekday", {"n": n, "weekday": WEEKDAYS[wd_tok[:3]]}, months=ms)
        except (ValueError, KeyError):
            return None
    return None


def _adapt_cb_calendar(disc: dict, ctx: BuildContext, ccy: str) -> dict:
    """Central-bank rate decisions — the official scheduled list from UMD (reconciled, not duplicated)."""
    try:
        sys.path.insert(0, str(Path.home() / "PycharmProjects" / "unified_market_data" / "src"))
        from unified_market_data.analysis.cb_meeting_calendars import meetings_for
    except Exception:
        return _unknown("UMD cb_meeting_calendars unavailable")
    horizon = ctx.as_of + timedelta(days=int(ctx.months * 31))
    dates = sorted(d for d in (dd.date() if hasattr(dd, "date") else dd for dd in meetings_for(ccy))
                   if ctx.as_of <= d <= horizon)
    if not dates:
        return _unknown(f"no scheduled {ccy} meetings within horizon (backlog beyond published dates)")
    return {"cadence": "scheduled list (8/yr)",
            "upcoming": [d.isoformat() for d in dates], "confidence": "high",
            "provenance": "UMD cb_meeting_calendars (central bank's own published schedule)"}


def _adapt_fred(disc: dict, ctx: BuildContext) -> dict:
    """FRED releases/dates — real forward US release dates. Falls back to a declared block if the feed
    (or the API key) is unavailable, so the release still resolves offline."""
    name, key = disc.get("release_name", ""), ctx.fred_key
    if key and name:
        try:
            import requests
            horizon = ctx.as_of + timedelta(days=int(ctx.months * 31))
            r = requests.get("https://api.stlouisfed.org/fred/releases/dates", params={
                "api_key": key, "file_type": "json", "sort_order": "asc",
                "include_release_dates_with_no_data": "false",
                "realtime_start": ctx.as_of.isoformat(), "realtime_end": horizon.isoformat()}, timeout=15)
            r.raise_for_status()
            dates = sorted({date.fromisoformat(rd["date"]) for rd in r.json().get("release_dates", [])
                            if name in rd.get("release_name", "") and rd.get("date")})
            dates = [d for d in dates if ctx.as_of <= d <= horizon]
            if dates:
                return {"cadence": "official forward schedule",
                        "upcoming": [d.isoformat() for d in dates], "confidence": "high",
                        "provenance": f"FRED releases/dates API (release_name~{name!r})"}
        except Exception:
            pass
    fb = disc.get("fallback")
    if isinstance(fb, dict):
        rec = _resolve(fb, ctx, ccy="")
        rec["provenance"] += " [FRED unavailable → fallback]"
        return rec
    return _unknown("FRED unavailable and no fallback declared")


def _resolve(disc: dict, ctx: BuildContext, ccy: str) -> dict:
    via = (disc or {}).get("via")
    if via == "cb_calendar":
        return _adapt_cb_calendar(disc, ctx, ccy)
    if via == "anchors":
        return _adapt_anchors(disc, ctx)
    if via == "rule":
        return _adapt_rule(disc, ctx)
    if via == "fred":
        return _adapt_fred(disc, ctx)
    return _unknown(f"no discovery method (via={via!r})")


# ── build ──────────────────────────────────────────────────────────────────────────────────────────
def _ccy_for(jur_id: str, jurs: list[dict]) -> str:
    return next((j.get("ccy", "") for j in jurs if j.get("id") == jur_id), "")


def build(ctx: BuildContext, taxonomy_path: Path = TAXONOMY) -> list[dict]:
    """Resolve every release in the taxonomy into a calendar record. Generic over jurisdictions —
    US is one row of N, discovered by exactly the same path as GB/EU/JP."""
    tax = yaml.safe_load(taxonomy_path.read_text()) or {}
    jurs = yaml.safe_load((CATALOG / "jurisdictions.yaml").read_text()).get("jurisdictions", [])
    records = []
    for r in tax.get("releases", []):
        ccy = _ccy_for(r.get("jurisdiction", ""), jurs)
        resolved = _resolve(r.get("discovery") or {}, ctx, ccy)
        records.append({
            "id": r["id"], "jurisdiction": r["jurisdiction"], "name": r["name"],
            "category": r.get("category", ""), "domain": r.get("domain", ""),
            "tier": r.get("tier", 3), **resolved})
    return records


def write_calendar(records: list[dict], ctx: BuildContext, out: Path = OUT) -> None:
    header = (f"# GENERATED by scripts/build_release_calendar.py on {ctx.as_of.isoformat()} "
              f"(horizon {ctx.months} months). Do not hand-edit — edit catalog/release_taxonomy.yaml\n"
              "# and re-run. Dates are APPROXIMATE (week-resolution); every record carries provenance\n"
              "# and a confidence flag. confidence: unknown ⇒ cadence could not be established (blank,\n"
              "# never guessed). The ATS harvester (render/ats/harvest.py) reads this file.\n")
    body = yaml.safe_dump({"generated": ctx.as_of.isoformat(), "horizon_months": ctx.months,
                           "releases": records}, sort_keys=False, allow_unicode=True, width=100)
    out.write_text(header + body)


# ── preview (hard-rule #1: a human eyeballs it) ────────────────────────────────────────────────────────
_STARS = {1: "★★★", 2: "★★ ", 3: "★  "}


def preview(records: list[dict], as_of: date, weeks: int = 4) -> str:
    horizon = as_of + timedelta(weeks=weeks)
    rows = []
    for rec in records:
        for ds in rec["upcoming"]:
            d = date.fromisoformat(ds)
            if as_of <= d <= horizon:
                rows.append((d, rec["jurisdiction"], rec.get("tier", 3), rec["name"], rec["confidence"]))
    rows.sort(key=lambda x: (x[0], x[1]))
    out = [f"\nNext {weeks} weeks of releases — {as_of:%d %b %Y} → {horizon:%d %b %Y}"
           f"   (all jurisdictions, US one of N)\n" + "-" * 78]
    if not rows:
        out.append("  (no releases resolved within the window)")
    for d, jur, tier, name, conf in rows:
        flag = "" if conf == "high" else f"  [{conf}]"
        out.append(f"  {d:%a %d %b}  {jur:<3} {_STARS.get(tier, '?')}  {name[:44]:<44}{flag}")
    unknown = [r for r in records if r["confidence"] == "unknown"]
    if unknown:
        out.append("-" * 78)
        out.append(f"  {len(unknown)} release(s) left UNKNOWN (cadence not established, blank — never guessed):")
        for r in unknown:
            out.append(f"    {r['jurisdiction']:<3} {r['id']:<22} — {r['provenance']}")
    by_jur = {}
    for r in records:
        by_jur.setdefault(r["jurisdiction"], []).append(r["confidence"])
    out.append("-" * 78)
    out.append("  coverage by jurisdiction (resolved / total): "
               + "  ".join(f"{j}={sum(c != 'unknown' for c in cs)}/{len(cs)}"
                           for j, cs in sorted(by_jur.items())))
    return "\n".join(out)


def _load_fred_key() -> str:
    import os
    if os.environ.get("FRED_API_KEY"):
        return os.environ["FRED_API_KEY"]
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("FRED_API_KEY=") and "=" in line:
                return line.split("=", 1)[1].strip()
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the approximate cross-jurisdiction release calendar.")
    ap.add_argument("--months", type=int, default=9, help="projection horizon in months (default 9)")
    ap.add_argument("--preview", action="store_true", help="print the next 4 weeks across all regions")
    ap.add_argument("--no-write", action="store_true", help="do not write the calendar file")
    args = ap.parse_args()

    ctx = BuildContext(as_of=date.today(), months=args.months, fred_key=_load_fred_key())
    if not TAXONOMY.exists():
        print(f"FAIL: taxonomy not found at {TAXONOMY}", file=sys.stderr)
        return 2
    records = build(ctx)
    if not args.no_write:
        write_calendar(records, ctx)
        print(f"wrote {OUT.relative_to(REPO)}  —  {len(records)} releases, "
              f"{sum(r['confidence'] != 'unknown' for r in records)} resolved, "
              f"{sum(r['confidence'] == 'unknown' for r in records)} unknown")
    if args.preview:
        print(preview(records, ctx.as_of))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
