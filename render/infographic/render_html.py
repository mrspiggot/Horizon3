"""Deterministic HTML/SVG → PNG renderer for the AIS.

Every figure is emitted as ``<span class="num" data-src=… data-val=…>…</span>`` — so the tier-1 gate
verifies numbers by DOM inspection, never OCR (the property Horizon2 lacked). Charts embed as base64
PNGs from the ACS families. No diffusion, no LLM at render time. CSS design system adapted from
``render/flagship_fed_model.py``.
"""
from __future__ import annotations

import html as _html

from .schema import Block, InfographicSpec, NumberObject


def _num_span(n: NumberObject) -> str:
    return (f'<span class="num" data-src="{_html.escape(n.source)}" data-val="{n.value:.6g}" '
            f'data-fmt="{_html.escape(n.fmt)}">{_html.escape(n.rendered())}</span>')


def _fill(template: str, numbers: list[NumberObject]) -> str:
    """Replace {name} placeholders with number spans; escape the surrounding prose."""
    if not template:
        return ""
    parts, out = template.split("{"), []
    out.append(_html.escape(parts[0]))
    for seg in parts[1:]:
        if "}" in seg:
            name, rest = seg.split("}", 1)
            n = next((x for x in numbers if x.name == name.strip()), None)
            out.append(_num_span(n) if n else _html.escape("{" + seg))
            out.append(_html.escape(rest))
        else:
            out.append(_html.escape("{" + seg))
    return "".join(out)


# ── per-block HTML ─────────────────────────────────────────────────────────────────────────────
def _tile(b: Block) -> str:
    big = _num_span(b.numbers[0]) if b.numbers else ""
    sub = _fill(b.text, b.numbers[1:]) if b.text else ""
    return (f'<div class="tile {b.tone}"><div class="k">{_html.escape(b.title)}</div>'
            f'<div class="v">{big}</div><div class="s">{sub}</div></div>')


def _chart(b: Block) -> str:
    cap = _html.escape(b.title)
    img = f'<img alt="{cap}" src="data:image/png;base64,{b.chart_png}"/>' if b.chart_png else ""
    return f'<figure class="chart">{img}<figcaption>{cap}</figcaption></figure>'


def _ranked_table(b: Block) -> str:
    """A ranked ladder: rows carry {label} + a NumberObject name; the value cell is a verified span.
    `b.rows` = [{"label": str, "name": <NumberObject.name>, "note": str?}, …] in ranked order."""
    body = []
    for i, r in enumerate(b.rows, 1):
        n = b.num(r.get("name", ""))
        val = _num_span(n) if n else ""
        note = f'<span class="tnote">{_html.escape(r.get("note", ""))}</span>' if r.get("note") else ""
        body.append(f'<tr><td class="rk">{i}</td><td class="lbl">{_html.escape(r.get("label", ""))}{note}</td>'
                    f'<td class="val">{val}</td></tr>')
    head = f'<div class="thead">{_html.escape(b.title)}</div>' if b.title else ""
    return f'<div class="ladder">{head}<table>{"".join(body)}</table></div>'


def _render_blocks(spec: InfographicSpec) -> str:
    html, i, blocks = [], 0, spec.blocks
    while i < len(blocks):
        b = blocks[i]
        if b.type == "kpi_tile":                       # group a run of tiles
            run = []
            while i < len(blocks) and blocks[i].type == "kpi_tile":
                run.append(_tile(blocks[i])); i += 1
            html.append('<div class="tiles">' + "".join(run) + "</div>"); continue
        if b.type == "chart_embed":                    # group a run of charts
            run = []
            while i < len(blocks) and blocks[i].type == "chart_embed":
                run.append(_chart(blocks[i])); i += 1
            html.append('<div class="charts">' + "".join(run) + "</div>"); continue
        if b.type == "state_badge":                    # group a run of regime pills
            run = []
            while i < len(blocks) and blocks[i].type == "state_badge":
                bb = blocks[i]
                run.append(f'<span class="pill {bb.tone}">{_html.escape(bb.title)} '
                           f'{_fill(bb.text, bb.numbers)}</span>')
                i += 1
            html.append('<div class="badges">' + "".join(run) + "</div>"); continue
        if b.type == "thesis_callout":
            html.append(f'<div class="callout">{_fill(b.text, b.numbers)}</div>')
        elif b.type == "note":
            html.append(f'<div class="note"><h3>{_html.escape(b.title)}</h3>'
                        f'<p>{_fill(b.text, b.numbers)}</p></div>')
        elif b.type == "ranked_table":
            html.append(_ranked_table(b))
        elif b.type == "state_badge":
            html.append(f'<span class="pill {b.tone}">{_html.escape(b.title)} '
                        f'{_fill(b.text, b.numbers)}</span>')
        elif b.type == "illustration_slot":
            src = b.chart_png
            inner = (f'<img alt="illustration" src="data:image/png;base64,{src}"/>' if src
                     else '<div class="illus-ph">illustration</div>')
            html.append(f'<div class="illus" data-illustration="1">{inner}</div>')
        elif b.type == "source":
            html.append(f'<div class="prov">{_fill(b.text, b.numbers)}</div>')
        i += 1
    return "\n".join(html)


_CSS = """
:root{
  --bg:#fbfbfa; --board:#ffffff; --ink:#16161d; --muted:#6a6a72; --line:#e6e6ea;
  --accent:__ACCENT__; --up:#0a7d4d; --dn:#c2410c; --mid:#4a4a52;
  --serif:"Georgia",serif; --sans:-apple-system,"Helvetica Neue",Arial,sans-serif; --mono:"SF Mono",ui-monospace,monospace;
}
@media (prefers-color-scheme:dark){:root{--bg:#0e0e12;--board:#16161d;--ink:#ececf1;--muted:#9a9aa2;--line:#2a2a33;}}
*{box-sizing:border-box;} html,body{margin:0;background:var(--bg);}
.board{width:1000px;margin:0 auto;background:var(--board);color:var(--ink);font-family:var(--sans);}
.wrap{padding:40px 44px 30px;}
.eyebrow{font:600 12px/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--accent);}
h1{font:600 33px/1.12 var(--serif);margin:12px 0 8px;letter-spacing:-.01em;}
.deck{font:400 15px/1.5 var(--sans);color:var(--muted);max-width:64ch;margin:0;}
.rule{border:none;border-top:1px solid var(--line);margin:22px 0;}
.callout{font:400 18px/1.5 var(--serif);padding:16px 20px;border-left:3px solid var(--accent);
  background:color-mix(in srgb,var(--accent) 6%,transparent);border-radius:0 8px 8px 0;margin:0 0 22px;}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:0 0 22px;}
.tile{border:1px solid var(--line);border-radius:12px;padding:14px 16px;background:var(--board);}
.tile .k{font:600 11px/1.3 var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
  min-height:2.3em;display:flex;align-items:flex-start;}
.tile .v{font:600 30px/1.1 var(--sans);margin:8px 0 4px;letter-spacing:-.02em;}
.tile .s{font:400 12.5px/1.35 var(--sans);color:var(--muted);}
.tile.up{border-top:3px solid var(--up);} .tile.dn{border-top:3px solid var(--dn);}
.tile.mid{border-top:3px solid var(--mid);}
.charts{display:grid;grid-template-columns:1fr;gap:20px;margin:0 0 22px;}
.chart{margin:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--board);}
.chart img{width:100%;display:block;}
.chart figcaption{font:400 13.5px/1.45 var(--serif);color:var(--ink);padding:12px 16px 14px;border-top:1px solid var(--line);}
.note{border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 20px;}
.note h3{font:600 12px/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin:0 0 8px;}
.note p{font:400 14px/1.55 var(--sans);color:var(--ink);margin:0;}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px;}
.pill{display:inline-block;font:600 12.5px/1.2 var(--sans);padding:7px 13px;border-radius:999px;
  border:1px solid var(--line);margin:0;color:var(--muted);}
.pill.up{color:var(--up);border-color:color-mix(in srgb,var(--up) 55%,var(--line));
  background:color-mix(in srgb,var(--up) 7%,transparent);}
.pill.dn{color:var(--dn);border-color:color-mix(in srgb,var(--dn) 55%,var(--line));
  background:color-mix(in srgb,var(--dn) 7%,transparent);}
.ladder{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:0 0 22px;}
.ladder .thead{font:600 11px/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);padding:13px 16px;border-bottom:1px solid var(--line);background:color-mix(in srgb,var(--accent) 4%,transparent);}
.ladder table{width:100%;border-collapse:collapse;}
.ladder td{padding:11px 16px;border-bottom:1px solid var(--line);vertical-align:baseline;}
.ladder tr:last-child td{border-bottom:none;}
.ladder tr:hover td{background:color-mix(in srgb,var(--accent) 3%,transparent);}
.ladder .rk{width:2.2em;font:600 13px/1 var(--mono);color:var(--muted);}
.ladder .lbl{font:500 14.5px/1.35 var(--sans);color:var(--ink);}
.ladder .lbl .tnote{display:block;font:400 12px/1.3 var(--sans);color:var(--muted);margin-top:2px;}
.ladder .val{text-align:right;white-space:nowrap;font-size:16px;}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums;font-weight:600;color:var(--accent);}
.callout .num,.note .num{color:var(--ink);}
.prov{font:400 10.5px/1.5 var(--mono);color:var(--muted);border-top:1px solid var(--line);padding-top:14px;margin-top:6px;}
.illus{border-radius:12px;overflow:hidden;margin:0 0 22px;} .illus img{width:100%;display:block;}
.illus-ph{height:120px;display:flex;align-items:center;justify-content:center;color:var(--muted);
  border:1px dashed var(--line);border-radius:12px;font:400 13px var(--sans);}
"""


def render_html(spec: InfographicSpec) -> str:
    css = _CSS.replace("__ACCENT__", spec.layout.accent or "#4C6EA8")
    body = (
        f'<div class="board"><div class="wrap">'
        f'<div class="eyebrow">{_html.escape(spec.persona)}</div>'
        f'<h1>{_html.escape(spec.title)}</h1>'
        + (f'<p class="deck">{_html.escape(spec.deck)}</p>' if spec.deck else "")
        + '<hr class="rule"/>'
        + _render_blocks(spec)
        + "</div></div>"
    )
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>"


def html_to_png(html: str, out_png: str, width: int = 1000, scale: int = 2) -> str:
    """Rasterise via headless chromium (Playwright). Full-page, retina-scale."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 100}, device_scale_factor=scale)
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=out_png, full_page=True)
        browser.close()
    return out_png
