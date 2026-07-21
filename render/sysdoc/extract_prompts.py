"""AST extraction of node → (kind, structured-output schema, declared temperature).

Static analysis only — nothing is imported or executed here, so it works without a
DB or an LLM. Two products:

  * `node_llm_info(pkg)` — per node function in `<pkg>/nodes.py`: the structured-output
    schema class(es), the resolved model constant(s), the declared temperature(s), and
    an AST-inferred kind (llm | vision | deterministic).
  * `index_schemas()` — every pydantic BaseModel across `render/`, name → module +
    fields (with `Field(description=...)`), so a schema referenced in one file but
    defined in another (state.py / claims.py / encoding.py) still resolves.

Caveats baked in (see the plan): `get_llm()` ignores `temperature` at runtime, so the
declared value is recorded but the renderer labels it "declared, not applied";
`article_graph` nodes delegate to writer.py and carry no inline LLM call, so their kind
comes from annotations, not from here.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RENDER = REPO / "render"

# model constants used across the node modules all resolve to this today
_FALLBACK_CONSTS = {"VISION_MODEL": "claude-opus-4-8", "REASONING_MODEL": "claude-opus-4-8"}


def _str_const(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _module_str_consts(tree: ast.Module) -> dict[str, str]:
    out: dict[str, str] = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            v = _str_const(n.value)
            if v is not None:
                out[n.targets[0].id] = v
    return out


def _field_desc(call: ast.Call) -> str:
    """Pull a description out of a `Field(...)` call (keyword `description=` or the
    first positional string)."""
    for kw in call.keywords:
        if kw.arg == "description":
            return _str_const(kw.value) or ""
    for a in call.args:
        s = _str_const(a)
        if s is not None and s != "":
            return s
    return ""


def _class_fields(cls: ast.ClassDef) -> list[dict]:
    fields: list[dict] = []
    for stmt in cls.body:
        target = None
        value = None
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            target, value = stmt.target.id, stmt.value
        elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            target, value = stmt.targets[0].id, stmt.value
        if not target or target.startswith("_") or target == "model_config":
            continue
        desc = ""
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "Field":
            desc = _field_desc(value)
        fields.append({"name": target, "desc": desc})
    return fields


def _is_basemodel(cls: ast.ClassDef) -> bool:
    for b in cls.bases:
        if isinstance(b, ast.Name) and b.id in {"BaseModel"}:
            return True
        if isinstance(b, ast.Attribute) and b.attr in {"BaseModel"}:
            return True
    return False


def index_schemas() -> dict[str, dict]:
    """name -> {module (repo-relative), fields:[{name,desc}]} for every BaseModel."""
    index: dict[str, dict] = {}
    for py in sorted(RENDER.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = str(py.relative_to(REPO))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and _is_basemodel(node):
                # first definition wins; schemas are uniquely named in this repo
                index.setdefault(node.name, {"module": rel, "fields": _class_fields(node)})
    return index


def node_func_map(pkg: str) -> dict[str, str]:
    """node id → node function name, parsed from `<pkg>/graph.py`'s add_node calls.

    LangGraph node ids need not equal the function name (e.g. add_node("critique",
    nodes.multimodal_critique)). `article_graph` registers via a getattr loop, so
    there node id == function name and this map is simply empty (callers fall back
    to the id).
    """
    graph_py = REPO / pkg / "graph.py"
    if not graph_py.exists():
        return {}
    tree = ast.parse(graph_py.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_node" and len(node.args) >= 2):
            continue
        nid = _str_const(node.args[0])
        target = node.args[1]
        fn = None
        if isinstance(target, ast.Attribute):
            fn = target.attr
        elif isinstance(target, ast.Name):
            fn = target.id
        if nid and fn:
            out[nid] = fn
    return out


class _NodeVisitor(ast.NodeVisitor):
    def __init__(self, consts: dict[str, str]):
        self.consts = consts
        self.schemas: list[str] = []
        self.models: list[str] = []
        self.temps: list[float | None] = []

    def visit_Call(self, call: ast.Call):
        f = call.func
        # .with_structured_output(Schema)
        if isinstance(f, ast.Attribute) and f.attr == "with_structured_output" and call.args:
            arg = call.args[0]
            if isinstance(arg, ast.Name):
                self.schemas.append(arg.id)
        # get_llm(model=..., temperature=...)
        if isinstance(f, ast.Name) and f.id == "get_llm":
            model_name = "REASONING_MODEL"     # get_llm default
            temp: float | None = None
            for kw in call.keywords:
                if kw.arg == "model":
                    if isinstance(kw.value, ast.Name):
                        model_name = kw.value.id
                    elif (s := _str_const(kw.value)) is not None:
                        model_name = s
                elif kw.arg == "temperature" and isinstance(kw.value, ast.Constant):
                    if isinstance(kw.value.value, (int, float)):
                        temp = float(kw.value.value)
            self.models.append(model_name)
            self.temps.append(temp)
        self.generic_visit(call)


def _resolve_model(name: str, consts: dict[str, str]) -> str:
    return consts.get(name) or _FALLBACK_CONSTS.get(name) or name


def _is_vision(models_raw: list[str]) -> bool:
    return any(m == "VISION_MODEL" for m in models_raw)


def node_llm_info(pkg: str) -> dict[str, dict]:
    """pkg e.g. 'render/studio' → {node_fn_name: {kind, schemas, models, declared_temps}}."""
    nodes_py = REPO / pkg / "nodes.py"
    if not nodes_py.exists():
        return {}
    tree = ast.parse(nodes_py.read_text(encoding="utf-8"))
    consts = _module_str_consts(tree)
    out: dict[str, dict] = {}
    for n in tree.body:
        if not isinstance(n, ast.FunctionDef):
            continue
        args = n.args.args
        if not args or args[0].arg not in {"state", "_state"}:
            continue
        v = _NodeVisitor(consts)
        for stmt in n.body:
            v.visit(stmt)
        vision = _is_vision(v.models)
        if vision:
            kind = "vision"
        elif v.schemas or v.models:
            kind = "llm"
        else:
            kind = "deterministic"
        out[n.name] = {
            "kind": kind,
            "schemas": v.schemas,
            "models": sorted({_resolve_model(m, consts) for m in v.models}),
            "declared_temps": v.temps,
        }
    return out
