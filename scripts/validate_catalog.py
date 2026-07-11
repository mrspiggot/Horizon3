#!/usr/bin/env python
"""Validate the Horizon3 model catalog against the live UMD estate (read-only).

Deliverable 1's fitness check and the embryo of the Deliverable-6 conviction test. The catalog is
role-based and jurisdiction-generic (hard-rule #6): a model declares input ROLES; catalog/
jurisdictions.yaml binds each role to concrete UMD series per jurisdiction. This validator resolves
each model across EVERY jurisdiction it claims to support and prints a currency × model matrix of
DATA and IMPLEMENTATION coverage.

Checks (read-only):
  1. schema well-formedness (required keys; family/order in enums; exactly one of
     implemented_by / build_stub; every input.role is in the role vocabulary);
  2. per (model, jurisdiction): each REQUIRED role binds AND its bound series exists in the estate
     -> DATA ok. A model that CLAIMS a jurisdiction but whose required role is unbound/absent there
     is OVER-CLAIMING -> FAIL;
  3. IMPLEMENTATION coverage: jurisdiction in model.implementation_coverage.covers (impl gaps where
     DATA ok but not covered are the honest Deliverable-5/impl backlog, NOT failures);
  4. every non-stub implemented_by resolves to a real callable in UMD analysis/ (static);
  5. every personas[].uses id resolves to a model file.

Exit: 0 if no authored model over-claims a jurisdiction; 1 otherwise; 2 on estate error.

Env: TIMESCALE_DSN (or TSDB_*); UMD_SRC (default ~/PycharmProjects/unified_market_data/src).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import psycopg2
import yaml

REPO = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    """Best-effort .env loader (no hard dependency). Does not clobber real env vars."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv(REPO / ".env")

MODELS_DIR = REPO / "catalog" / "models"
PERSONAS_FILE = REPO / "catalog" / "personas.yaml"
JURIS_FILE = REPO / "catalog" / "jurisdictions.yaml"
UNDERLYINGS_FILE = REPO / "catalog" / "underlyings.yaml"
EVENTS_FILE = REPO / "catalog" / "events.yaml"
COMMODITIES_FILE = REPO / "catalog" / "commodities.yaml"
PAIRS_FILE = REPO / "catalog" / "pairs.yaml"

# Generalization axes: which binding file + list key + model "claimed instances" field each uses.
AXES = {
    "currency":   {"file": JURIS_FILE,        "list_key": "jurisdictions", "claim_field": "jurisdictions"},
    "underlying": {"file": UNDERLYINGS_FILE,   "list_key": "underlyings",   "claim_field": "instances"},
    "event":      {"file": EVENTS_FILE,        "list_key": "events",        "claim_field": "instances"},
    "commodity":  {"file": COMMODITIES_FILE,   "list_key": "commodities",   "claim_field": "instances"},
    "pair":       {"file": PAIRS_FILE,         "list_key": "pairs",         "claim_field": "instances"},
}

FAMILIES = {"rates", "vol", "credit", "fx", "commodity", "equity", "macro", "event"}
ORDERS = {"level", "delta", "delta2", "context", "diffusion", "surprise"}
# surface/computed = API/analysis-derived (not a raw series) → declared, not DB-checked.
SOURCES = {"observations", "curve", "derived", "event", "surface", "computed"}

_TTY = sys.stdout.isatty()
def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _TTY else s
OK, FAIL, STUB = c("32", "OK"), c("31", "FAIL"), c("33", "STUB")
TICK, GAP, CROSS = c("32", "✓"), c("33", "·"), c("31", "✗")


def dsn() -> str:
    if os.environ.get("TIMESCALE_DSN"):
        return os.environ["TIMESCALE_DSN"]
    host = os.environ.get("TSDB_HOST", "127.0.0.1")
    if host == "localhost":
        host = "127.0.0.1"
    return (f"host={host} port={os.environ.get('TSDB_PORT','5434')} "
            f"dbname={os.environ.get('TSDB_DB','unified_market_data')} "
            f"user={os.environ.get('TSDB_USER','postgres')} "
            f"password={os.environ.get('TSDB_PASS','devpassword')}")


def umd_src() -> Path:
    return Path(os.environ.get("UMD_SRC", str(Path.home() / "PycharmProjects/unified_market_data/src")))


class Estate:
    def __init__(self, conn):
        self.conn = conn
        self._series: dict[str, bool] = {}
        self._curve: dict[tuple[str, str], bool] = {}

    def series_exists(self, sid: str) -> bool:
        if sid.endswith("*"):
            pat = sid[:-1] + "%"
            if pat not in self._series:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM observations WHERE series_id LIKE %s LIMIT 1", (pat,))
                    self._series[pat] = cur.fetchone() is not None
            return self._series[pat]
        if sid not in self._series:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM observations WHERE series_id = %s LIMIT 1", (sid,))
                self._series[sid] = cur.fetchone() is not None
        return self._series[sid]

    def curve_exists(self, ccy: str, ctype: str) -> bool:
        key = (ccy, ctype)
        if key not in self._curve:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM curve_snapshots WHERE currency=%s AND curve_type=%s LIMIT 1", key)
                self._curve[key] = cur.fetchone() is not None
        return self._curve[key]

    def binding_exists(self, binding: dict) -> bool:
        ref, source = binding.get("ref"), binding.get("source")
        if source in ("surface", "computed"):
            return True  # API/analysis-derived — declared (manually API-verified), not DB-checked
        if source in ("observations", "event"):
            return self.series_exists(ref)
        if source == "curve":
            if ":" not in (ref or ""):
                return False
            ccy, ctype = ref.split(":", 1)
            return self.curve_exists(ccy, ctype)
        return False


def resolve_callable(dotted: str, src: Path) -> tuple[bool, str]:
    parts = dotted.split(".")
    if len(parts) < 2:
        return False, f"malformed '{dotted}'"
    *mod, fn = parts
    path = src.joinpath(*mod).with_suffix(".py")
    if not path.exists():
        return False, f"module not found: {path}"
    if re.search(rf"^\s*(async\s+def|def|class)\s+{re.escape(fn)}\b", path.read_text(errors="ignore"), re.M):
        return True, f"{fn} in {path.name}"
    return False, f"'{fn}' not in {path.name}"


def _load_axis(cfg: dict) -> dict:
    if not cfg["file"].exists():
        return {"roles": set(), "insts": {}, "order": [], "claim": cfg["claim_field"]}
    d = yaml.safe_load(cfg["file"].read_text())
    insts = {x["id"]: x for x in d.get(cfg["list_key"], [])}
    return {"roles": set(d.get("roles", {})), "insts": insts, "order": list(insts), "claim": cfg["claim_field"]}


def main() -> int:
    axes = {name: _load_axis(cfg) for name, cfg in AXES.items()}

    model_files = sorted(MODELS_DIR.glob("*.yaml"))
    docs = {f.stem: yaml.safe_load(f.read_text()) for f in model_files}

    try:
        conn = psycopg2.connect(dsn())
        conn.set_session(readonly=True, autocommit=True)
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL}: cannot reach UMD estate — {e}", file=sys.stderr)
        return 2
    estate, src = Estate(conn), umd_src()
    print(f"UMD source: {src}")
    print(f"UMD estate: {dsn().split('password=')[0].strip()}")
    for name, ax in axes.items():
        if ax["order"]:
            print(f"Axis '{name}': {', '.join(ax['order'])}")
    print()

    over_claims = 0
    matrices: dict[str, dict[str, dict[str, str]]] = {name: {} for name in AXES}

    for stem, doc in docs.items():
        mid = doc.get("model_id", stem)
        fam = doc.get("family", "?")
        is_stub = doc.get("build_stub") is True
        is_direct = doc.get("data_direct") is True
        covers = set((doc.get("implementation_coverage") or {}).get("covers", []) or [])
        # pick the generalization axis this model varies over
        _go = doc.get("generic_over") or []
        axis_name = ("event" if "event" in _go else "commodity" if "commodity" in _go
                     else "pair" if "pair" in _go
                     else "underlying" if "underlying" in _go else "currency")
        ax = axes[axis_name]
        role_vocab, insts, order = ax["roles"], ax["insts"], ax["order"]
        claimed = doc.get(ax["claim"], []) or []
        if is_stub:
            kind = f"{STUB}"
        elif is_direct:
            kind = "data-direct (published series)"
        else:
            kind = f"impl: {doc.get('implemented_by','—').split('.')[-1]}"
        print(f"MODEL {mid}  [{fam}]  ({axis_name})  {kind}  covers: {sorted(covers) or '—'}")

        # schema
        errs = []
        for k in ("model_id", "name", "family", "spec", "inputs", "outputs", "interpretation"):
            if k not in doc:
                errs.append(f"missing '{k}'")
        if not (doc.get("visualizations") or []):
            errs.append("no visualizations declared (charts are first-class)")
        if doc.get("family") not in FAMILIES:
            errs.append(f"family '{doc.get('family')}' invalid")
        n_kind = sum([("implemented_by" in doc), is_stub, is_direct])
        if n_kind != 1:
            errs.append(f"must have exactly ONE of implemented_by/build_stub/data_direct (got {n_kind})")
        req_roles, opt_roles = [], []
        for inp in doc.get("inputs", []) or []:
            r = inp.get("role")
            if r not in role_vocab:
                errs.append(f"input.role '{r}' not in {axis_name} vocab")
            (req_roles if inp.get("required") else opt_roles).append(r)
            if inp.get("order") not in ORDERS:
                errs.append(f"bad order '{inp.get('order')}'")
            if not inp.get("horizon"):
                errs.append(f"role {r} missing horizon")
        for j in claimed:
            if j not in insts:
                errs.append(f"unknown {axis_name} '{j}'")
        print(f"  schema           {OK if not errs else FAIL}" + ("" if not errs else "  " + "; ".join(errs)))

        if "implemented_by" in doc:
            good, detail = resolve_callable(doc["implemented_by"], src)
            print(f"  implemented_by   {OK if good else FAIL}  {detail}")
            if not good:
                over_claims += 1

        print(f"  roles: required={sorted(set(req_roles))}  optional={sorted(set(opt_roles))}")

        matrices[axis_name][mid] = {}
        cells = []
        for j in order:
            if j not in claimed:
                matrices[axis_name][mid][j] = " -"
                continue
            bindings = insts[j].get("bindings", {}) or {}
            missing = []
            for role in set(req_roles):
                b = bindings.get(role)
                if not b:
                    missing.append(f"{role}=unbound")
                elif not estate.binding_exists(b):
                    missing.append(f"{role}:{b.get('ref')}=absent")
            data_ok = not missing
            impl_ok = (j in covers)
            cell = (TICK if data_ok else CROSS) + (TICK if impl_ok else GAP)
            matrices[axis_name][mid][j] = cell
            cells.append(f"{j} {cell}" + ("" if data_ok else f" ({'; '.join(missing)})"))
            if not data_ok:
                over_claims += 1
        print(f"  DATA/IMPL by {axis_name}:")
        for line in cells:
            print(f"    {line}")
        print(f"  => {'STUB (D5 impl)' if is_stub else 'authored'}\n")

    # one compact matrix per axis that has models
    for axis_name, mtx in matrices.items():
        if not mtx:
            continue
        order = axes[axis_name]["order"]
        print(f"{axis_name.upper()} × MODEL MATRIX   (cell = DATA/IMPL:  "
              f"{TICK}{TICK}=both  {TICK}{GAP}=data-only(impl gap)  {CROSS}{GAP}=data-missing  -=not claimed)")
        w = max(len(m) for m in mtx)
        print(" " * (w + 2) + "  ".join(f"{j:>4}" for j in order))
        for mid, row in mtx.items():
            print(f"  {mid:<{w}} " + "  ".join(f"{row[j]:>4}" for j in order))
        print()

    # renderability — how many declared viz specs map to a render primitive (render/from_catalog)
    _RENDERERS = {"fan", "heatmap", "surface3d", "smile", "lines", "bar", "dumbbell"}
    _INFER = [("fan", ["fan"]), ("surface3d", ["3d surface"]), ("smile", ["smile"]),
              ("heatmap", ["heatmap"]), ("dumbbell", ["dumbbell", "lollipop"]), ("bar", ["bar"]),
              ("scatter", ["scatter"]), ("stacked_area", ["stacked area"]), ("table", ["table"]),
              ("lines", ["time series", "over time", "lines", "curve", "term structure", "smiles by",
                         "reliability", "density", "loading", "ridge"])]

    def _ct(v):
        if v.get("chart_type"):
            return v["chart_type"]
        t = (str(v.get("form", "")) + " " + str(v.get("id", ""))).lower()
        for ct, kws in _INFER:
            if any(k in t for k in kws):
                return ct
        return None

    viz = [v for d in docs.values() for v in (d.get("visualizations") or [])]
    unwired = sorted({_ct(v) or "unknown" for v in viz if _ct(v) not in _RENDERERS})
    ren = sum(1 for v in viz if _ct(v) in _RENDERERS)
    print(f"RENDERABILITY: {ren}/{len(viz)} declared viz specs map to a render primitive"
          + (f"  (unwired chart_types: {unwired})" if unwired else ""))

    # personas
    print("\nPERSONAS")
    persona_fail = 0
    personas = yaml.safe_load(PERSONAS_FILE.read_text()).get("personas", [])
    known = set(docs.keys())
    for p in personas:
        uses = p.get("uses", []) or []
        missing = [u for u in uses if u not in known]
        print(f"  {p.get('persona_id'):28} uses {len(uses):>2}  {OK if not missing else FAIL}"
              + ("" if not missing else f"  unresolved: {missing}"))
        persona_fail += bool(missing)

    total = over_claims + persona_fail
    print(f"\nSUMMARY: {over_claims} over-claim/impl failures · {persona_fail} persona unresolved · "
          f"{sum(1 for d in docs.values() if d.get('build_stub'))} stubs")
    conn.close()
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
