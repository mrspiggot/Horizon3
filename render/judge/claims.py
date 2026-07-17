"""Typed claims about executed model output, and the arithmetic that settles them.

§06 role 7: the Judge "scores model-grounding and numerical discipline". This is the disposing half.

THE DIVISION OF LABOUR, and it is the whole design:

    the LLM PROPOSES   — extraction is a language problem. Recognising that "the signal is an
                         inversion — the slope below zero" is a regime claim about the term spread,
                         that "since the GFC" denotes ~2007, that "more recently up" is a direction
                         claim about r*: no regex reaches any of that. That is exactly why the
                         existing HISTORY firewall fails — it matches 4-digit years, and "since the
                         GFC" contains no digits.

    ARITHMETIC DISPOSES — truth is not a language problem. An LLM judge would have certified
                         "CPI 2.83%" as true, because 2.83 reads as an utterly plausible print. It
                         was a 13-month change. The arithmetic does not care how plausible it looks.

So the LLM emits a typed Claim; the functions below evaluate it against model_output_point and return
a verdict with the numbers that settled it. The LLM never judges.

Three claim types, because they are the three that actually shipped to a reader on 2026-07-14:

    SUPERLATIVE  "+0.18pp, the most restrictive setting since the financial crisis"
                 -> max(stance_pct) since 2007 is +2.27pp (2024-08). FALSE.
    REGIME       "Read the spread series and the signal is an inversion — the slope below zero"
                 -> term_spread_pp latest is +0.75pp. FALSE.
    DIRECTION    "r* ... down through the 2010s, and more recently up"
                 -> r_star_pct fell over the last 3 years. FALSE.
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# Named market episodes -> the window a claim about them means. The firewall's blind spot: prose says
# "the GFC", never "2007". Extend deliberately; a missing episode should fail extraction loudly rather
# than be guessed at.
EPISODES: dict[str, tuple[str, str]] = {
    "gfc": ("2007-01-01", "2009-12-31"),
    "financial crisis": ("2007-01-01", "2009-12-31"),
    "global financial crisis": ("2007-01-01", "2009-12-31"),
    "covid": ("2020-01-01", "2020-12-31"),
    "pandemic": ("2020-01-01", "2020-12-31"),
    "taper tantrum": ("2013-05-01", "2013-12-31"),
    "dot-com": ("2000-01-01", "2002-12-31"),
    "volcker": ("1979-08-01", "1987-08-31"),
}


class Claim(BaseModel):
    """One checkable assertion the prose makes about an executed model output."""
    quote: str = Field(description="the sentence fragment from the prose making the claim, verbatim")
    kind: Literal["superlative", "regime", "direction", "episode", "percentile"]
    model_id: str = Field(description="the model whose output this is about")
    output: str = Field(description="the EXACT output name from the offered list, e.g. stance_pct")

    # superlative: "TODAY is the highest/most X since Y"
    # episode:     "the peak/trough HAPPENED in <period>" — same op, but `at` instead of `since`
    op: Literal["max", "min"] | None = Field(default=None, description="superlative and episode only")
    since: str | None = Field(default=None,
                              description="superlative only: YYYY-MM-DD, or an episode name like 'the GFC'")
    at: str | None = Field(
        default=None,
        description="episode only: the period the prose PLACES the extreme in — '2022', 'mid-2023', "
                    "'COVID'. The claim is that the high/low occurred THEN.")

    # regime: where the series sits relative to zero — NOW, or during a stated past window
    predicate: Literal["below_zero", "above_zero", "inverted", "positive", "negative"] | None = None
    during: str | None = Field(
        default=None,
        description="regime only. If the claim is scoped to a PAST period, name it: '2021-01/2022-12', "
                    "'2022', or an episode like 'COVID'. Omit ONLY if the claim is about the present.")

    # direction: which way it has moved lately
    expect: Literal["up", "down"] | None = None
    window_months: int | None = Field(default=None, description="direction only; default 36")

    # percentile: "the 78th percentile of its post-1948 history", "an eighth-percentile reading"
    pct: int | None = Field(default=None, description="percentile only: the percentile the text states, 0-100")
    scope: Literal["full", "recent"] | None = Field(
        default=None,
        description="percentile only: 'full' if the text ties it to the whole history ('since 1948', "
                    "'post-war', 'ever'); 'recent' if to the last few years. Default 'full'.")


class Claims(BaseModel):
    claims: list[Claim] = Field(default_factory=list)


class Verdict(BaseModel):
    quote: str
    kind: str
    output: str
    ok: bool
    detail: str


# Vague halves of a year, as GENEROUS month spans. "mid-2023" is not a date, and the honest response
# to imprecision is a wide window rather than a guess: a narrow one convicts prose for saying something
# ordinary. These overlap deliberately — the cost of being generous is a missed catch, the cost of
# being strict is a false accusation, and only one of those gets this check switched off.
_VAGUE: dict[str, tuple[int, int]] = {
    "early": (1, 7), "mid": (3, 10), "middle": (3, 10), "late": (6, 12),
    "h1": (1, 6), "h2": (7, 12), "first half": (1, 6), "second half": (7, 12),
}


def _month_end(year: int, month: int) -> str:
    """The real last day. Hardcoding 28 silently dropped 29-31 from every month-scoped claim."""
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def _strip_articles(s: str) -> str:
    """`"the taper tantrum".lstrip("the ")` returns "aper tantrum" — lstrip takes a SET of characters,
    not a prefix, so it ate the 't' of 'taper' and the episode never matched. That failed a true claim
    with "unresolvable window", which is the worst thing this file can do."""
    s = s.strip().lower()
    for art in ("the ", "a ", "an "):
        if s.startswith(art):
            s = s[len(art):]
    return s.strip()


def _resolve_window(during: str | None) -> tuple[str | None, str]:
    """A stated period -> (start, end). Accepts an episode ('COVID'), a year ('2022'), a year-month
    ('2023-06'), a year range ('2021-2022'), a vague half ('mid-2023') or an explicit range."""
    if not during:
        return None, ""
    s = _strip_articles(during)
    for name, (lo, hi) in EPISODES.items():
        if name in s:
            return lo, hi
    if "/" in s:
        a, _, b = s.partition("/")
        return _pad(a.strip(), False), _pad(b.strip(), True)
    # ORDER MATTERS. '2023-06' is a MONTH, not the range 2023..06. The old year-range branch tested
    # `len(s) <= 9 and s.replace("-","").isdigit()`, which '2023-06' satisfies — it resolved to
    # ('2023-01-01', '06-12-31') and every claim scoped to a single month was failed as unshowable.
    if re.fullmatch(r"\d{4}-\d{2}", s):
        y, m = int(s[:4]), int(s[5:])
        return f"{s}-01", _month_end(y, m)
    if re.fullmatch(r"\d{4}\s*[-–to]+\s*\d{4}", s):
        yrs = re.findall(r"\d{4}", s)
        return f"{yrs[0]}-01-01", f"{yrs[-1]}-12-31"
    if re.fullmatch(r"\d{4}", s):
        return f"{s}-01-01", f"{s}-12-31"
    # 'mid-2023', 'late 2022', 'H1 2024' — a vague half of a named year.
    if (yr := re.search(r"(19|20)\d{2}", s)):
        y = int(yr.group())
        for word, (m0, m1) in _VAGUE.items():
            if word in s:
                return f"{y:04d}-{m0:02d}-01", _month_end(y, m1)
        return f"{y}-01-01", f"{y}-12-31"          # a year is named; the vagueness is only around it
    return None, ""


def _pad(s: str, end: bool) -> str:
    if re.fullmatch(r"\d{4}", s):
        return f"{s}-12-31" if end else f"{s}-01-01"
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return _month_end(int(s[:4]), int(s[5:])) if end else f"{s}-01"
    return s


def _resolve_since(since: str | None) -> str | None:
    if not since:
        return None
    s = _strip_articles(since)
    for name, (start, _end) in EPISODES.items():
        if name in s:
            return start
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return f"{s}-01"
    if (yr := re.search(r"(19|20)\d{2}", s)):
        return f"{yr.group()}-01-01"
    return None


def adjudicate(claim: Claim, series: list[tuple[date, float]]) -> Verdict:
    """Settle one claim against one executed output series. Deterministic; no model involved."""
    pts = [(d, v) for d, v in series if v is not None]
    if len(pts) < 2:
        return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=False,
                       detail=f"cannot adjudicate: {claim.output} has {len(pts)} usable points")
    latest_d, latest_v = pts[-1]

    if claim.kind == "superlative":
        since = _resolve_since(claim.since)
        if not since:
            return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=False,
                           detail=f"unresolvable window {claim.since!r} — a superlative needs a start")
        window = [(d, v) for d, v in pts if d.isoformat() >= since]
        if not window:
            return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=False,
                           detail=f"no {claim.output} data since {since} — the claim cannot be shown")
        pick = max if claim.op == "max" else min
        ext_d, ext_v = pick(window, key=lambda x: x[1])
        ok = (ext_d == latest_d)
        return Verdict(
            quote=claim.quote, kind=claim.kind, output=claim.output, ok=ok,
            detail=(f"latest {claim.output}={latest_v:+.2f} ({latest_d}); "
                    f"{claim.op} since {since} is {ext_v:+.2f} ({ext_d})"
                    + ("" if ok else f" — the extreme was {abs(ext_v / latest_v):.1f}x the latest, "
                                     f"{ext_d.year - latest_d.year and abs(ext_d.year - latest_d.year)} year(s) earlier")))

    if claim.kind == "percentile":
        # The narrator is handed percentiles, so the narrator writes percentile sentences. Without a
        # type for them the extractor mangled each into a superlative and the adjudicator answered a
        # question nobody asked ("is today the minimum since 1948?" — no, so FAIL), convicting on the
        # wrong grounds. Two of those sentences WERE false; being right by accident is not a check.
        if claim.pct is None:
            return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=False,
                           detail="percentile claim with no stated percentile — cannot settle it")
        recent = pts[-60:] if claim.scope == "recent" else pts
        actual = sum(1 for _, v in recent if v < latest_v) / len(recent) * 100
        which = f"last {len(recent)} obs" if claim.scope == "recent" else f"{pts[0][0]}→{pts[-1][0]}"
        # A writer rounds ("an eighth-percentile reading" off 7.4%). Convict on a real gap, not on
        # rounding: 10 points is wide enough to spare honest prose and far too narrow to let 8-vs-39
        # or 78-vs-23 through.
        ok = abs(actual - claim.pct) <= 10
        return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=ok,
                       detail=(f"{claim.output}={latest_v:+.2f} is the {actual:.0f}th percentile over "
                               f"{which}; the text says {claim.pct}th"
                               + ("" if ok else f" — off by {abs(actual - claim.pct):.0f} points")))

    if claim.kind == "episode":
        # "the trough it reached in mid-2023, the most inverted point the probit has read" — a claim
        # about WHERE IN TIME the extreme sits, not about today. The superlative type cannot say this,
        # so the extractor used to mangle it into one and it was convicted with "unresolvable window":
        # a false accusation against a sentence the data supports (min -1.73 IS 2023-06).
        # This is also the shape of a real defect an editor caught: "the 2022 spike" when the spike is
        # 2020. Misattributing an episode is exactly as wrong as misstating a level.
        lo, hi = _resolve_window(claim.at)
        if not lo:
            return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=False,
                           detail=f"unresolvable period {claim.at!r} — cannot place the extreme")
        scope = pts
        if (since := _resolve_since(claim.since)):
            scope = [(d, v) for d, v in pts if d.isoformat() >= since] or pts
        ext_d, ext_v = (max if claim.op == "max" else min)(scope, key=lambda x: x[1])
        ok = lo <= ext_d.isoformat() <= hi
        return Verdict(
            quote=claim.quote, kind=claim.kind, output=claim.output, ok=ok,
            detail=(f"{'max' if claim.op == 'max' else 'min'} {claim.output}={ext_v:+.2f} at {ext_d}; "
                    f"the prose places it in {lo[:7]}..{hi[:7]}"
                    + ("" if ok else " — the extreme is NOT in that period")))

    if claim.kind == "regime":
        p = claim.predicate
        want_neg = p in ("below_zero", "inverted", "negative")
        # A regime claim may be about NOW ("the signal is an inversion") or about a stated PAST period
        # ("through 2021 and 2022 the ex-post rate went deeply negative"). Checking the latest value
        # against a historical claim fails TRUE prose — the ex-post rate did go to -5.4% in 2022, and
        # an early version of this judge called that sentence a contradiction because the series is
        # +0.22 today. A judge that fails honest work gets switched off, and then it protects nothing.
        if claim.during:
            lo, hi = _resolve_window(claim.during)
            if not lo:
                return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=False,
                               detail=f"unresolvable period {claim.during!r} — cannot scope the claim")
            win = [(d, v) for d, v in pts if lo <= d.isoformat() <= hi]
            if not win:
                return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=False,
                               detail=f"no {claim.output} data in {lo}..{hi} — the claim cannot be shown")
            ext_d, ext_v = (min if want_neg else max)(win, key=lambda x: x[1])
            ok = (ext_v < 0) if want_neg else (ext_v > 0)
            return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=ok,
                           detail=(f"{claim.output} over {lo[:7]}..{hi[:7]}: "
                                   f"{'min' if want_neg else 'max'}={ext_v:+.2f} ({ext_d}); claim says {p}"))
        ok = (latest_v < 0) if want_neg else (latest_v > 0)
        return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=ok,
                       detail=f"latest {claim.output}={latest_v:+.2f} ({latest_d}); claim says {p} (now)")

    # direction. "More recently up" is VAGUE, and the judge must not resolve that vagueness with an
    # arbitrary default and then call the prose a liar. r_star_pct is +0.15 over 12m and -0.03 over
    # 36m: an early version defaulted to 36m and failed "down through the 2010s, and more recently up"
    # — a claim that is TRUE (r* bottomed at +0.56 in 2014-01 and has risen to +1.06 since). Only
    # convict when EVERY plausible reading agrees against the claim; when the windows disagree, the
    # sentence is ambiguous, not false, and that is the writer's business rather than the judge's.
    windows = [claim.window_months] if claim.window_months else [12, 36, 60]
    reads: list[tuple[int, float]] = []
    for m in windows:
        cutoff = date(latest_d.year - m // 12, latest_d.month, 1)
        prior = [(d, v) for d, v in pts if d <= cutoff]
        if prior:
            reads.append((m, latest_v - prior[-1][1]))
    if not reads:
        return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=False,
                       detail=f"no {claim.output} history before {latest_d} to compare against")
    agree = [(m, d) for m, d in reads if ((d > 0) if claim.expect == "up" else (d < 0))]
    shown = " · ".join(f"{m}m {d:+.2f}" for m, d in reads)
    if len(agree) == len(reads):
        return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=True,
                       detail=f"{claim.output} {shown}; claim says {claim.expect} — every window agrees")
    if not agree:
        return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=False,
                       detail=f"{claim.output} {shown}; claim says {claim.expect} — no window supports it")
    return Verdict(quote=claim.quote, kind=claim.kind, output=claim.output, ok=True,
                   detail=(f"{claim.output} {shown}; claim says {claim.expect} — AMBIGUOUS, windows "
                           f"disagree. Not convicted: the claim holds on "
                           f"{', '.join(f'{m}m' for m, _ in agree)}"))
