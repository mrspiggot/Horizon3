"""DATA FITNESS — can UMD support the charts the catalog asks for? Ask BEFORE rendering, and say so LOUDLY.

UMD is not a black box. Every series can be interrogated for its extent, its cadence and its holes, and
the model graph declares exactly which series each chart consumes. So the fitness of the data for a
chart is *computable up front* — we never have to discover it by looking at a bad chart afterwards.

The failure this exists to end (§04-fm3, hard rule #5): on 2026-07-14 `reaction_function` asked for 65
monthly points, the executor silently dropped 57 of them, and an 8-point chart shipped captioned "through
the tightening cycle". Nothing raised. The window has since silently *recovered* via backfill — which is
the whole problem: nobody could tell either way, in either direction.

Three verdicts, and the distinction between the last two is the point:

  OK             the requested window is delivered in full.
  DELIVERY GAP   the catalog asked and UMD could not deliver — holes, or transform warm-up. Chart is
                 starved; refuse it or fix the data.
  UNDER-ASKED    UMD holds materially MORE history than the catalog asked for. Free depth, no data work
                 — widen `history.start`. (This is the cheap half of the "crises off-chart" defect: the
                 prose names 2008/2011/2020 and the chart starts in 2023 *because nobody asked for more*.)
  SHORTFALL      the series itself is too shallow to support the claims. This is an ACQUISITION TASK —
                 a source must be found or a backfill run. This is what we report LOUDLY.

    ~/venv/bin/python scripts/data_fitness.py              # metadata + execute for ground truth
    ~/venv/bin/python scripts/data_fitness.py --fast       # metadata only, no execution
    ~/venv/bin/python scripts/data_fitness.py --model reaction_function
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.graph_corpus import GRAPH_DIR, _dates, _fetch_factory, _load_model  # noqa: E402

# Observations a transform must consume before it can emit its first value. A yoy needs the calendar
# year behind it; a GARCH fit needs enough returns to identify. Expressed in MONTHS of lead-in.
_WARMUP_MONTHS = {
    "yoy": 12, "yoy_diff": 12, "sahm": 15, "pct_change": 1,
    "garch_vol": 3, "momentum": 12, "roll_skew": 12, "roll_kurt": 12,
    "realized_vol": 1, "log": 0, "none": 0,
}
# How much unused depth counts as materially under-asked, in years.
_UNDER_ASK_YEARS = 2.0
# Depth below which a chart cannot carry a claim about its own history — no distribution to sit in, no
# cycle to point at. The prose in these articles routinely says "thin by the standard of its own
# history" and names 2008/2011/2020; a 3-year series can support none of that, however honestly it is
# drawn. Until charts declare `requires_history:`, this is the standing floor for a cyclical claim.
_CYCLE_YEARS = 10.0

RED, AMBER, GREEN, BOLD, OFF = "\033[31m", "\033[33m", "\033[32m", "\033[1m", "\033[0m"


def _m(key: str) -> int:
    """'YYYY-MM' -> absolute month index."""
    return int(key[:4]) * 12 + int(key[5:7]) - 1


def _fmt_years(months: int) -> str:
    return f"{months / 12:.1f}y"


def series_coverage(cur, sid: str, source: str | None) -> dict:
    """Interrogate UMD for one series: extent, count, cadence and holes. Read-only."""
    if source:
        cur.execute("SELECT timestamp::date FROM observations WHERE series_id=%s AND source=%s "
                    "ORDER BY timestamp", (sid, source))
    else:
        cur.execute("SELECT timestamp::date FROM observations WHERE series_id=%s ORDER BY timestamp", (sid,))
    dates = [str(r[0]) for r in cur.fetchall()]
    if not dates:
        return {"sid": sid, "n": 0, "first": None, "last": None, "cadence_m": None, "holes": []}
    keys = sorted({d[:7] for d in dates})
    gaps = sorted(_m(b) - _m(a) for a, b in zip(keys, keys[1:]))
    cadence = gaps[len(gaps) // 2] if gaps else 1
    holes = [f"{a} → {b}" for a, b in zip(keys, keys[1:]) if (_m(b) - _m(a)) > max(cadence, 1)]
    return {"sid": sid, "n": len(dates), "first": keys[0], "last": keys[-1],
            "cadence_m": cadence, "holes": holes}


def assess_model(model_id: str, cur, conn, execute: bool) -> dict:
    """Everything knowable about whether this model's charts can be built, before drawing one."""
    m = _load_model(model_id)
    hist = m["history"]
    req_start = hist.get("start", "2021-01")[:7]
    req_end = hist.get("end", "2026-05")[:7]
    cadence = hist.get("cadence", "monthly")
    requested = _dates(req_start, req_end, cadence)

    inputs = []
    for inp in m["spec"].inputs:
        if inp.source == "derived" or not inp.series_id:
            continue
        cov = series_coverage(cur, inp.series_id, m["db_sources"].get(inp.series_id))
        warm = _WARMUP_MONTHS.get(inp.transform or "none", 0)
        cov["transform"] = inp.transform or "none"
        cov["warmup_m"] = warm
        # the earliest as-of at which this input can yield a value
        cov["effective_first"] = None if not cov["first"] else _key_add(cov["first"], warm)
        inputs.append(cov)

    missing = [i for i in inputs if i["n"] == 0]
    available_first = max((i["effective_first"] for i in inputs if i["effective_first"]), default=None)
    available_last = min((i["last"] for i in inputs if i["last"]), default=None)
    binding_start = next((i for i in inputs if i["effective_first"] == available_first), None)
    binding_end = next((i for i in inputs if i["last"] == available_last), None)

    delivered = None
    if execute and not missing:
        from unified_market_data.analysis.executor import Executor
        ex = Executor(_fetch_factory(conn, m["db_sources"]))
        runs = ex.run_history(m["spec"], requested)
        delivered = {"n": len(runs), "first": runs[0].as_of[:7] if runs else None,
                     "last": runs[-1].as_of[:7] if runs else None}

    # verdicts
    verdicts = []
    if missing:
        verdicts.append(("SHORTFALL", f"series absent from UMD: {', '.join(i['sid'] for i in missing)}"))
    if delivered is not None and delivered["n"] < len(requested):
        short = len(requested) - delivered["n"]
        verdicts.append(("DELIVERY GAP",
                         f"asked {len(requested)}, got {delivered['n']} — {short} as-of dates refused"))
    if available_first and _m(available_first) < _m(req_start) - int(_UNDER_ASK_YEARS * 12):
        unused = _m(req_start) - _m(available_first)
        verdicts.append(("UNDER-ASKED",
                         f"UMD holds from {available_first}; catalog asks {req_start} — "
                         f"{_fmt_years(unused)} of history unused, free"))
    if available_first and _m(available_first) > _m(req_start):
        gap = _m(available_first) - _m(req_start)
        verdicts.append(("SHORTFALL",
                         f"catalog asks {req_start}; earliest possible is {available_first} "
                         f"({_fmt_years(gap)} short) — bound by {binding_start['sid']}"))
    depth = (_m(available_last) - _m(available_first)) if (available_first and available_last) else None
    if depth is not None and depth < _CYCLE_YEARS * 12:
        verdicts.append(("SHALLOW",
                         f"UMD holds only {_fmt_years(depth)} in total ({available_first} → "
                         f"{available_last}), bound by {binding_start['sid']} — no chart from this "
                         f"model can carry an 'own history' or past-cycle claim, however honestly drawn"))
    # CO-TENANT DRAG: the executor resolves every input at every as-of, so ONE shallow series truncates
    # the whole model — including charts that never plot it. That is not an acquisition task, it is a
    # modelling one (split the model, or make the input optional), and it is free. Detect it by
    # comparing the binding input against the next-shallowest.
    firsts = sorted({i["effective_first"] for i in inputs if i["effective_first"]})
    if len(firsts) > 1 and (_m(firsts[-1]) - _m(firsts[-2])) > 24:
        drag = _m(firsts[-1]) - _m(firsts[-2])
        peers = ", ".join(sorted({i["sid"] for i in inputs if i["effective_first"] == firsts[-2]}))
        # Only charts that never read the shallow input are recoverable by splitting. Which outputs
        # depend on which inputs lives inside the impl function, so this reports the FACT and names the
        # charts to check — it does not claim a split is possible. (For beveridge_curve the drag is
        # intrinsic: JOLTS vacancies genuinely start in 2000 and every chart needs them.)
        free = [c.get("id", "?") for c in m["charts"]
                if binding_start["sid"] not in yaml.safe_dump(c.get("data_contract", {}))
                and not _reads_input(c, _iid_of(m, binding_start["sid"]))]
        verdicts.append(("CO-TENANT DRAG",
                         f"{binding_start['sid']} (from {firsts[-1]}) is {_fmt_years(drag)} shallower "
                         f"than its co-tenants ({peers}, from {firsts[-2]}) and truncates EVERY chart "
                         f"in this model. Charts to check for a free split: "
                         f"{'; '.join(free) if free else '(none — every chart reads it; drag is intrinsic)'}"))

    return {"model_id": model_id, "req_start": req_start, "req_end": req_end,
            "n_requested": len(requested), "inputs": inputs, "delivered": delivered,
            "available_first": available_first, "available_last": available_last,
            "binding_start": binding_start, "binding_end": binding_end,
            "verdicts": verdicts, "charts": m["charts"], "persona": m["meta"].get("persona", "?")}


def _key_add(key: str, months: int) -> str:
    n = _m(key) + months
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def _iid_of(m: dict, series_id: str) -> str | None:
    """The input id bound to a series, e.g. BAMLH0A0HYM2 -> 'hy'."""
    return next((i.id for i in m["spec"].inputs if i.series_id == series_id), None)


def _reads_input(chart: dict, input_id: str | None) -> bool:
    """Does this chart's data_contract reference `input:<id>` — or ANY output? An output may be a
    function of every input, so a chart that plots outputs cannot be assumed independent of any of
    them. Conservative by design: only a chart that reads named inputs, none of them the shallow one,
    is reported as recoverable."""
    if not input_id:
        return True
    blob = yaml.safe_dump(chart.get("data_contract", {}) or {})
    if "output:" in blob:
        return True                       # depends on the impl fn, which consumes every input
    return f"input:{input_id}" in blob


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="metadata only — skip model execution")
    ap.add_argument("--model", help="assess one model")
    args = ap.parse_args()

    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    cur = conn.cursor()

    ids = [args.model] if args.model else sorted(
        p.stem for p in GRAPH_DIR.glob("*.yaml") if p.stem not in ("personas", "vision"))

    rows, failed = [], []
    for mid in ids:
        try:
            rows.append(assess_model(mid, cur, conn, execute=not args.fast))
        except Exception as exc:
            failed.append((mid, f"{type(exc).__name__}: {exc}"))

    print(f"\n{BOLD}DATA FITNESS — can UMD support what the catalog asks for?{OFF}")
    print(f"{'model':32} {'requested':22} {'delivered':>11}  verdict")
    print("─" * 100)
    for r in sorted(rows, key=lambda r: r["model_id"]):
        d = r["delivered"]
        dtxt = f"{d['n']}/{r['n_requested']}" if d else f"?/{r['n_requested']}"
        kinds = [v[0] for v in r["verdicts"]]
        order = ["DELIVERY GAP", "SHORTFALL", "SHALLOW", "CO-TENANT DRAG", "UNDER-ASKED"]
        tag = next((k for k in order if k in kinds), "OK")
        col = {"OK": GREEN, "UNDER-ASKED": AMBER, "CO-TENANT DRAG": AMBER}.get(tag, RED)
        extra = f"  +{len(kinds) - 1}" if len(kinds) > 1 else ""
        print(f"{r['model_id']:32} {r['req_start']} → {r['req_end']:9} {dtxt:>11}  {col}{tag}{OFF}{extra}")

    # ── the loud part ────────────────────────────────────────────────────────────────────────────
    loud = ("SHORTFALL", "DELIVERY GAP", "SHALLOW")
    short = [r for r in rows if any(v[0] in loud for v in r["verdicts"])]
    if short:
        print(f"\n{RED}{BOLD}{'█' * 100}{OFF}")
        print(f"{RED}{BOLD}  DATA SHORTFALL — these charts CANNOT honestly carry their claims on what UMD holds{OFF}")
        print(f"{RED}{BOLD}{'█' * 100}{OFF}")
        for r in short:
            print(f"\n  {BOLD}{r['model_id']}{OFF}  (persona: {r['persona']})")
            for kind, msg in r["verdicts"]:
                col = AMBER if kind in ("UNDER-ASKED", "CO-TENANT DRAG") else RED
                print(f"    {col}▸ {kind}: {msg}{OFF}")
            for i in r["inputs"]:
                flag = f"  {RED}← BINDING{OFF}" if i is r["binding_start"] else ""
                hole = f"  {RED}{len(i['holes'])} HOLE(S): {'; '.join(i['holes'][:2])}{OFF}" if i["holes"] else ""
                print(f"      {i['sid']:16} {str(i['first']):8} → {str(i['last']):8} "
                      f"n={i['n']:<6} {i['transform']:12}{flag}{hole}")
            print(f"    {BOLD}charts affected:{OFF} " + "; ".join(c.get("id", "?") for c in r["charts"]))

    drag = [r for r in rows if any(v[0] == "CO-TENANT DRAG" for v in r["verdicts"])]
    if drag:
        print(f"\n{AMBER}{BOLD}{'▒' * 100}{OFF}")
        print(f"{AMBER}{BOLD}  CO-TENANT DRAG — one shallow input truncates the whole model. Charts named below "
              f"read only inputs it isn't one of{OFF}")
        print(f"{AMBER}  and are being truncated for nothing — a free fix, no data work. Charts that plot "
              f"OUTPUTS are conservatively{OFF}")
        print(f"{AMBER}  assumed to need every input, so this UNDER-reports: a pass-through model may free "
              f"more than is listed.{OFF}")
        print(f"{AMBER}{BOLD}{'▒' * 100}{OFF}")
        for r in drag:
            for kind, msg in r["verdicts"]:
                if kind == "CO-TENANT DRAG":
                    print(f"  {BOLD}{r['model_id']:28}{OFF} {msg}")

    under = [r for r in rows if any(v[0] == "UNDER-ASKED" for v in r["verdicts"])
             and not any(v[0] in ("SHORTFALL", "DELIVERY GAP") for v in r["verdicts"])]
    if under:
        print(f"\n{AMBER}{BOLD}{'▒' * 100}{OFF}")
        print(f"{AMBER}{BOLD}  UNDER-ASKED — UMD already holds the history. Widen history.start. NO data work needed.{OFF}")
        print(f"{AMBER}{BOLD}{'▒' * 100}{OFF}")
        for r in under:
            for kind, msg in r["verdicts"]:
                if kind == "UNDER-ASKED":
                    print(f"  {BOLD}{r['model_id']:30}{OFF} {msg}")

    # ── the acquisition backlog: series that block charts, ranked by blast radius ─────────────────
    backlog: dict[str, dict] = {}
    for r in short:
        b = r["binding_start"]
        if not b:
            continue
        e = backlog.setdefault(b["sid"], {"first": b["first"], "models": [], "charts": 0, "personas": set()})
        e["models"].append(r["model_id"])
        e["charts"] += len(r["charts"])
        e["personas"].add(r["persona"])
    if backlog:
        print(f"\n{RED}{BOLD}{'█' * 100}{OFF}")
        print(f"{RED}{BOLD}  DATA ACQUISITION BACKLOG — find a source or backfill these, by blast radius{OFF}")
        print(f"{RED}{BOLD}{'█' * 100}{OFF}")
        for sid, e in sorted(backlog.items(), key=lambda kv: -kv[1]["charts"]):
            print(f"  {BOLD}{sid:16}{OFF} earliest {e['first']}  "
                  f"blocks {e['charts']} chart(s) across {len(e['personas'])} persona(s): "
                  f"{', '.join(sorted(e['personas']))}")

    if failed:
        print(f"\n{RED}could not assess:{OFF}")
        for mid, err in failed:
            print(f"  {mid:30} {err}")

    n_ok = sum(1 for r in rows if not r["verdicts"])
    print(f"\n{len(rows)} models assessed — {GREEN}{n_ok} OK{OFF}, {AMBER}{len(under)} under-asked{OFF}, "
          f"{RED}{len(short)} short{OFF}\n")


if __name__ == "__main__":
    main()
