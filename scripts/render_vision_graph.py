#!/usr/bin/env python
"""Render the persona -> models -> sources -> inputs -> outcomes -> insights graph as an HTML artifact.

This is THE graph the vision demands, drawn honestly: every model coloured by the drains-up audit
(GREEN = proven published method, fully illustrated; AMBER = grounded but thin / not yet role-illustrated;
RED = homemade slop). It shows, for every persona, the full chain — the decision-maker, the models they
use, the published SOURCE each model implements, the multi-dimensional INPUTS (as §10 states), the
OUTCOMES the model computes, and the INSIGHT it yields.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
GRAPH = REPO / "catalog" / "graph"
REG = REPO / "knowledge" / "registry.yaml"


def verdict(d: dict) -> str:
    m = d.get("method", "UNTAGGED")
    roles = {ch.get("role") for ch in (d.get("charts") or [])}
    illustrated = {"input", "outcome", "consequence"} <= roles and \
        len({ch.get("chart_type") for ch in (d.get("charts") or [])}) >= 2
    if m in ("composite",) or m == "UNTAGGED":
        return "red"
    if m == "arithmetic":
        return "amber"
    if m in ("published", "data-direct"):
        return "green" if illustrated else "amber"
    return "amber"


def main() -> int:
    papers = {p["id"]: p for p in (yaml.safe_load(REG.read_text()).get("papers") or [])}
    specs = {f.stem: yaml.safe_load(f.read_text())
             for f in sorted(GRAPH.glob("*.yaml")) if f.name != "personas.yaml"}
    personas = yaml.safe_load((GRAPH / "personas.yaml").read_text()).get("personas", {})

    def esc(s):
        return html.escape(str(s))

    cards = []
    counts = {"green": 0, "amber": 0, "red": 0}
    for pid, p in personas.items():
        rows = []
        for mid in (p.get("models") or []):
            d = specs.get(mid, {})
            if not d:
                continue
            v = verdict(d)
            counts[v] += 1
            srcs = " · ".join(esc(papers.get(g, {}).get("title", g))[:40] for g in (d.get("grounded_in") or []))
            inputs = [i for i in (d.get("inputs") or [])]
            inpt = ", ".join(esc(i.get("series_id") or i.get("id")) for i in inputs[:6])
            outs = ", ".join(esc(o["name"]) for o in (d.get("outputs") or [])[:5])
            interp = (d.get("interpretations") or [{}])
            insight = esc((interp[0].get("says") if interp else "") or "—")
            method = esc(d.get("method", "?"))
            rows.append(f"""
            <div class="model {v}">
              <div class="mhead"><span class="dot"></span><b>{esc(d.get('name', mid))}</b>
                <span class="method">{method}</span></div>
              <div class="chain">
                <div class="cell src"><span class="lbl">source</span>{srcs or '—'}</div>
                <div class="arr">→</div>
                <div class="cell"><span class="lbl">inputs (§10 states)</span>{inpt}</div>
                <div class="arr">→</div>
                <div class="cell"><span class="lbl">outcomes</span>{outs}</div>
                <div class="arr">→</div>
                <div class="cell ins"><span class="lbl">insight</span>{insight}</div>
              </div>
            </div>""")
        cards.append(f"""
        <section class="persona">
          <h2>{esc(p.get('name', pid))}<span class="dec">{esc(p.get('decision',''))}</span></h2>
          {''.join(rows)}
        </section>""")

    total = sum(counts.values())
    body = f"""<style>
:root {{
  --bg:#0f1420; --panel:#161d2b; --ink:#e8ecf5; --muted:#93a0b8; --line:#26304260;
  --green:#2ecc71; --amber:#e6a532; --red:#e05555; --accent:#6ea8ff;
  --serif:"Iowan Old Style",Palatino,Georgia,serif; --sans:system-ui,-apple-system,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace;
}}
@media (prefers-color-scheme: light) {{
  :root {{ --bg:#f4f2ec; --panel:#fbfaf6; --ink:#1a1f2b; --muted:#5c6678; --line:#e0dccf; }}
}}
:root[data-theme="dark"] {{ --bg:#0f1420; --panel:#161d2b; --ink:#e8ecf5; --muted:#93a0b8; --line:#26304260; }}
:root[data-theme="light"] {{ --bg:#f4f2ec; --panel:#fbfaf6; --ink:#1a1f2b; --muted:#5c6678; --line:#e0dccf; }}
*{{box-sizing:border-box}}
.wrap {{ background:var(--bg); color:var(--ink); font-family:var(--sans); padding:clamp(20px,4vw,48px);
  min-height:100%; -webkit-font-smoothing:antialiased; }}
.inner {{ max-width:1180px; margin:0 auto; }}
.eyebrow {{ font-family:var(--mono); font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--accent); }}
h1 {{ font-family:var(--serif); font-size:clamp(30px,5vw,50px); line-height:1.05; margin:.2em 0 .1em; }}
.deck {{ color:var(--muted); max-width:70ch; font-size:16px; }}
.tally {{ display:flex; gap:10px; margin:22px 0 30px; flex-wrap:wrap; }}
.pill {{ font-family:var(--mono); font-size:13px; padding:6px 12px; border-radius:100px; border:1px solid var(--line); }}
.pill.g {{ color:var(--green); border-color:var(--green) }} .pill.a {{ color:var(--amber); border-color:var(--amber) }}
.pill.r {{ color:var(--red); border-color:var(--red) }}
.persona {{ margin:0 0 30px; }}
.persona > h2 {{ font-family:var(--serif); font-size:22px; margin:0 0 12px; border-bottom:1px solid var(--line); padding-bottom:8px; }}
.persona > h2 .dec {{ font-family:var(--sans); font-size:13px; color:var(--muted); font-weight:400; margin-left:12px; }}
.model {{ background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--muted);
  border-radius:10px; padding:12px 16px; margin:0 0 10px; }}
.model.green {{ border-left-color:var(--green) }} .model.amber {{ border-left-color:var(--amber) }}
.model.red {{ border-left-color:var(--red) }}
.mhead {{ display:flex; align-items:center; gap:9px; font-size:15px; margin-bottom:8px; }}
.mhead .dot {{ width:9px; height:9px; border-radius:50%; background:var(--muted); }}
.green .dot {{ background:var(--green) }} .amber .dot {{ background:var(--amber) }} .red .dot {{ background:var(--red) }}
.method {{ font-family:var(--mono); font-size:10.5px; color:var(--muted); border:1px solid var(--line);
  padding:2px 7px; border-radius:5px; margin-left:auto; }}
.chain {{ display:flex; align-items:stretch; gap:8px; overflow-x:auto; }}
.cell {{ flex:1; min-width:130px; font-size:12.5px; line-height:1.45; }}
.cell .lbl {{ display:block; font-family:var(--mono); font-size:9.5px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--muted); margin-bottom:3px; }}
.cell.src {{ color:var(--accent); }} .cell.ins {{ color:var(--ink); font-style:italic; min-width:200px; }}
.arr {{ color:var(--muted); align-self:center; font-size:15px; }}
.foot {{ font-family:var(--mono); font-size:11.5px; color:var(--muted); border-top:1px solid var(--line);
  padding-top:16px; margin-top:24px; line-height:1.7; }}
</style>
<div class="wrap"><div class="inner">
  <div class="eyebrow">Horizon3 · the executable model-knowledge graph · audited</div>
  <h1>Persona → Model → Source → Inputs → Outcomes → Insight</h1>
  <p class="deck">Every decision-maker runs published models on real, systematically-sourced data read as
    §10 states; the insight is the model's reading, illustrated input → outcome → consequence. Each model
    below is coloured by the drains-up audit — honestly, including the slop still to be remediated.</p>
  <div class="tally">
    <span class="pill g">● {counts['green']} GREEN — proven published, fully illustrated</span>
    <span class="pill a">● {counts['amber']} AMBER — grounded but thin / not yet role-illustrated</span>
    <span class="pill r">● {counts['red']} RED — homemade slop, to replace</span>
  </div>
  {''.join(cards)}
  <div class="foot">
    {total} models · {len(personas)} personas · graded by <b>scripts/audit.py</b> (a CI gate that FAILS
    while any RED remains) · every input series sourced from UMD's registry (daily + backfilled).<br/>
    Remediation in progress: RED composites → published methods (Merton, Gordon DDM, Gorton storage, BNP carry);
    AMBER published models → add input/outcome/consequence chart roles to reach GREEN.
  </div>
</div></div>"""
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "vision_graph.html"
    out.write_text(body)
    print(f"wrote {out}  ({total} models: {counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
