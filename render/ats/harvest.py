"""The harvesters — turn each trigger source into `CandidateTrigger`s.

Four sources, one shape out: economic CALENDAR (central-bank meetings via UMD + statistical data
releases for every jurisdiction via catalog/release_calendar.yaml), USER-suggested (a paragraph / URLs
the owner hands in), STANDING pieces (evergreen templates that light up on the right conditions), and
ZEITGEIST (what the news cycle is trending on, via GDELT). Each harvester fails soft — an unreachable
feed yields no candidates, never an exception — so the funnel always runs.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from . import vocab
from .schema import CandidateTrigger

_CATALOG = Path(__file__).resolve().parents[2] / "catalog"
_RELEASE_CALENDAR = _CATALOG / "release_calendar.yaml"


@dataclass
class HarvestContext:
    as_of: date
    lookahead_days: int = 12
    user_input: str = ""                                    # a paragraph and/or whitespace-sep URLs
    upcoming_meetings: list[dict] = field(default_factory=list)   # [{jur, ccy, cb, date}] within lookahead
    recent_surprises: list[dict] = field(default_factory=list)    # [{domain, z, date, event_type}]
    fred_key: str = ""


# ── (a) economic calendar ──────────────────────────────────────────────────────────────────────────
def _cb_meetings(ctx: HarvestContext) -> list[CandidateTrigger]:
    try:
        sys.path.insert(0, str(Path.home() / "PycharmProjects" / "unified_market_data" / "src"))
        from unified_market_data.analysis.cb_meeting_calendars import meetings_for
    except Exception:
        return []
    out = []
    horizon = ctx.as_of + timedelta(days=ctx.lookahead_days)
    for j in vocab.jurisdictions():
        for d in meetings_for(j["ccy"]):
            if isinstance(d, datetime):
                d = d.date()
            if ctx.as_of <= d <= horizon:
                days = (d - ctx.as_of).days
                out.append(CandidateTrigger(
                    source="calendar", domain="rates", jurisdiction=j["id"],
                    event_datetime=datetime(d.year, d.month, d.day),
                    title=f"{j['central_bank']} decides {d:%d %b} — what's at stake",
                    rationale=f"{j['central_bank']} rate decision in {days} day(s); read the policy choice through its own rulebook.",
                    raw_refs=[f"cb_meeting_calendars:{j['ccy']}"],
                    provenance={"harvester": "calendar.cb_meetings"}))
    return out


def _data_releases(ctx: HarvestContext, exclude_rate_keys: set) -> list[CandidateTrigger]:
    """Statistical data releases for EVERY jurisdiction, read from catalog/release_calendar.yaml (built
    by scripts/build_release_calendar.py). US is one jurisdiction of N — no FRED-only path, no `"US"`
    literal; title/prose are data-driven from each jurisdiction's own vocab. Fails soft (no file ⇒ []).

    `exclude_rate_keys` = (jurisdiction, date) pairs already emitted as central-bank DECISIONS by
    `_cb_meetings`; a matching rates row is skipped so the funnel reconciles with UMD, never duplicates.
    """
    try:
        releases = (yaml.safe_load(_RELEASE_CALENDAR.read_text()) or {}).get("releases", [])
    except Exception:
        return []
    horizon = ctx.as_of + timedelta(days=ctx.lookahead_days)
    out = []
    for rel in releases:
        jur, domain, name = rel.get("jurisdiction"), rel.get("domain"), rel.get("name", "")
        reader = vocab.jurisdiction_vocab(jur).get("cb_the") or vocab.central_bank_for(jur) or jur
        for ds in rel.get("upcoming", []) or []:
            try:
                d = date.fromisoformat(ds)
            except (ValueError, TypeError):
                continue
            if not (ctx.as_of <= d <= horizon):
                continue
            if domain == "rates" and (jur, d) in exclude_rate_keys:
                continue
            days = (d - ctx.as_of).days
            out.append(CandidateTrigger(
                source="calendar", domain=domain, jurisdiction=jur,
                event_datetime=datetime(d.year, d.month, d.day),
                title=f"{name} — {d:%d %b}: what {reader} will read into it",
                rationale=f"{jur} {name} releases in {days} day(s); read the print through {reader}'s "
                          f"lens before the surprise.",
                raw_refs=[f"release_calendar:{rel.get('id')}"],
                provenance={"harvester": "calendar.releases", "id": rel.get("id"),
                            "tier": rel.get("tier"), "confidence": rel.get("confidence")}))
    return out


def harvest_calendar(ctx: HarvestContext) -> list[CandidateTrigger]:
    cb = _cb_meetings(ctx)
    rate_keys = {(c.jurisdiction, c.event_datetime.date()) for c in cb if c.event_datetime}
    return cb + _data_releases(ctx, rate_keys)


# ── (b) user-suggested ───────────────────────────────────────────────────────────────────────────────
def harvest_user(ctx: HarvestContext) -> list[CandidateTrigger]:
    text = (ctx.user_input or "").strip()
    if not text:
        return []
    urls = [w for w in text.split() if w.startswith("http")]
    title = "Owner's commission"
    prose = " ".join(w for w in text.split() if not w.startswith("http"))[:200]
    return [CandidateTrigger(
        source="user", title=f"Owner's commission: {prose[:60]}" if prose else "Owner's commission",
        rationale=prose or "Article requested by the owner.",
        raw_refs=urls, provenance={"harvester": "user"})]


# ── (c) standing pieces ──────────────────────────────────────────────────────────────────────────────
def _cond_met(cond: dict, ctx: HarvestContext) -> bool:
    if "cb_meeting_collision" in cond:
        p = cond["cb_meeting_collision"]
        w, need = p.get("within_days", 7), p.get("min_banks", 2)
        within = [m for m in ctx.upcoming_meetings if 0 <= (m["date"] - ctx.as_of).days <= w]
        return len({m["jur"] for m in within}) >= need
    if "recent_surprise" in cond:
        p = cond["recent_surprise"]
        return any(s for s in ctx.recent_surprises
                   if s["domain"] == p.get("domain") and abs(s.get("z", 0)) >= p.get("abs_z_min", 1.5)
                   and 0 <= (ctx.as_of - s["date"]).days <= p.get("within_days", 5))
    return False


def _lights_up(entry: dict, ctx: HarvestContext) -> bool:
    cond = entry.get("lights_up_when") or {}
    if "any" in cond:
        return any(_cond_met(c, ctx) for c in cond["any"])
    if "all" in cond:
        return all(_cond_met(c, ctx) for c in cond["all"])
    return False


def harvest_standing(ctx: HarvestContext) -> list[CandidateTrigger]:
    try:
        entries = yaml.safe_load((_CATALOG / "standing_pieces.yaml").read_text())["standing_pieces"]
    except Exception:
        return []
    out = []
    for e in entries:
        personas = [p for p in e.get("personas", []) if vocab.is_valid_persona(p)]
        if not personas:
            continue
        hot = _lights_up(e, ctx)
        out.append(CandidateTrigger(
            source="standing", title=e["title"], domain=e.get("domain"),
            personas=personas, models=e.get("models", []),
            rationale=(("Timely now: " if hot else "Evergreen: ")
                       + " ".join(str(e.get("thesis", "")).split())[:160]),
            raw_refs=[f"standing:{e['id']}"],
            provenance={"harvester": "standing", "id": e["id"], "hot": hot,
                        "evergreen_floor": e.get("evergreen_floor", 0.35),
                        "jurisdictions": e.get("jurisdictions", [])}))
    return out


# ── (d) zeitgeist (GDELT) ────────────────────────────────────────────────────────────────────────────
def harvest_zeitgeist(ctx: HarvestContext, *, max_items: int = 6) -> list[CandidateTrigger]:
    """Trending financial-market themes from GDELT's free DOC 2.0 API. Domain/persona are left for the
    LLM mapper (constrained to our vocabulary). Fails soft to []."""
    try:
        import time

        import requests
        q = ('(inflation OR "interest rate" OR "central bank" OR recession OR "credit spread" OR '
             '"bond market" OR volatility OR commodities OR "federal reserve") sourcelang:english')
        params = {"query": q, "mode": "artlist", "format": "json", "maxrecords": 40,
                  "timespan": "3d", "sort": "hybridrel"}
        ua = {"User-Agent": "Mozilla/5.0 (Horizon3 ATS research)"}
        r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, headers=ua, timeout=20)
        if r.status_code == 429:                            # GDELT throttles to ~1 req / 5s
            time.sleep(6)
            r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, headers=ua, timeout=20)
        r.raise_for_status()
        arts = r.json().get("articles", [])
    except Exception:
        return []
    # crude dedup/cluster by domain keyword → one candidate per theme, up to max_items
    themes: dict[str, dict] = {}
    KEYS = {"inflation": "inflation", "rate": "rates", "central bank": "rates", "recession": "growth",
            "credit": "credit", "spread": "credit", "volatility": "vol", "equity": "equity",
            "stock": "equity", "commodit": "commodity", "oil": "commodity", "gold": "commodity"}
    for a in arts:
        title = (a.get("title") or "").strip()
        low = title.lower()
        dom = next((d for k, d in KEYS.items() if k in low), None)
        if not title or not dom or dom in themes:
            continue
        themes[dom] = {"title": title, "url": a.get("url", ""), "domain": dom}
        if len(themes) >= max_items:
            break
    return [CandidateTrigger(
        source="zeitgeist", title=t["title"][:90], domain=t["domain"],
        rationale=f"Trending in the news cycle now ({t['domain']}).",
        raw_refs=[t["url"]] if t["url"] else [], provenance={"harvester": "zeitgeist.gdelt"})
        for t in themes.values()]


HARVESTERS = [harvest_calendar, harvest_user, harvest_standing, harvest_zeitgeist]


def harvest_all(ctx: HarvestContext) -> list[CandidateTrigger]:
    out: list[CandidateTrigger] = []
    for h in HARVESTERS:
        try:
            out.extend(h(ctx))
        except Exception:
            continue
    return out
