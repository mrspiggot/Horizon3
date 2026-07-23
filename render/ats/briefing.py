"""The morning briefing — a self-contained HTML page of the 3 shortlisted articles for the owner to pick.

Each card shows the same skeleton the build phase adopted (the Van Gogh header, the infographic, the
charts, the 150-200-word gist) plus the "why now" and the full, auditable score breakdown (per-dimension
bars) so the editor sees exactly why it surfaced. Utilitarian information design: theme-aware, scannable,
images embedded as data URIs so the page is portable. Diffusion touches nothing here — this only lays out
already-rendered artifacts.
"""
from __future__ import annotations

import base64
import html as _html
import io
from datetime import date
from pathlib import Path

_ACCENT = "#4C6EA8"


def _data_uri(png: str | Path, max_px: int = 1100) -> str:
    p = Path(png)
    if not p.exists():
        return ""
    try:
        from PIL import Image
        img = Image.open(p)
        if max(img.size) > max_px:
            img.thumbnail((max_px, max_px), Image.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=82)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def _bars(cand) -> str:
    sc = cand.scores
    if not sc:
        return ""
    rows = []
    for d, w in sc.weights.items():
        v = sc.dims.get(d, 0.0)
        tag = "llm" if sc.judged_by.get(d) == "llm" else "det"
        rows.append(
            f'<div class="dim"><span class="dl">{_html.escape(d.replace("_"," "))} '
            f'<em class="{tag}">{tag}</em></span>'
            f'<span class="track"><span class="fill" style="width:{v*100:.0f}%"></span></span>'
            f'<span class="dv">{v:.2f}</span></div>')
    bonus = f'<span class="bonus">+{sc.bonus:.2f} multi-dimension bonus</span>' if sc.bonus else ""
    return (f'<div class="scores"><div class="stot">score {sc.total:.2f} {bonus}</div>'
            + "".join(rows) + "</div>")


def _card(i: int, card: dict) -> str:
    c, art, err = card["candidate"], card.get("article") or {}, card.get("error")
    why = _html.escape(c.rationale)
    when = ""
    if c.event_datetime:
        when = f'<span class="when">{c.event_datetime:%a %d %b}</span>'
    refs = "".join(f'<a href="{_html.escape(u)}">{_html.escape(u[:60])}</a>'
                   for u in c.raw_refs if u.startswith("http"))
    imgs = ""
    if art.get("illustration_png"):
        imgs += f'<img class="hero" src="{_data_uri(art["illustration_png"])}" alt="">'
    if art.get("infographic_png"):
        imgs += f'<img class="infog" src="{_data_uri(art["infographic_png"])}" alt="">'
    charts = "".join(f'<img class="ch" src="{_data_uri(p, 640)}" alt="">' for p in art.get("chart_pngs", []))
    gist = _html.escape(art.get("gist", "") or (f"[not rendered: {err}]" if err else ""))
    return f'''<article class="card">
  <div class="eyebrow"><span class="src {c.source}">{c.source}</span>
     {f'<span class="jur">{_html.escape(c.jurisdiction or (c.readiness.jurisdiction if c.readiness else "") or "—")}</span>' }
     <span class="persona">{_html.escape(art.get("persona", c.persona))}</span> {when}</div>
  <h2>{_html.escape(art.get("title", c.title))}</h2>
  <p class="why"><strong>Why now.</strong> {why}</p>
  {imgs}
  <p class="gist">{gist}</p>
  {f'<div class="charts">{charts}</div>' if charts else ""}
  {_bars(c)}
  {f'<div class="prov">{refs}</div>' if refs else ""}
  <div class="pick">Publish → <code>scripts/ats_briefing.py --as-of {{AS_OF}} --pick {c.id}</code></div>
</article>'''


_CSS = """
:root{--bg:#f7f7f6;--card:#fff;--ink:#17171c;--muted:#6b6b74;--line:#e6e6ea;--accent:__ACCENT__;
 --track:#e9e9ee;--serif:Georgia,serif;--sans:-apple-system,'Helvetica Neue',Arial,sans-serif;--mono:ui-monospace,'SF Mono',monospace;}
@media(prefers-color-scheme:dark){:root{--bg:#0e0e12;--card:#16161d;--ink:#ececf1;--muted:#9a9aa2;--line:#2a2a33;--track:#2a2a33;}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.5}
.wrap{max-width:1240px;margin:0 auto;padding:40px 28px 60px}
header h1{font:600 30px/1.15 var(--serif);margin:0 0 4px;letter-spacing:-.01em}
header p{color:var(--muted);margin:0 0 28px;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:22px;align-items:start}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 20px 16px;overflow:hidden}
.eyebrow{display:flex;align-items:center;gap:8px;font:600 11px/1 var(--sans);text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-bottom:10px}
.src{padding:3px 8px;border-radius:999px;color:#fff;background:var(--accent)}
.jur{padding:3px 7px;border-radius:999px;border:1px solid var(--line);color:var(--muted);font-weight:700}
.src.calendar{background:#2f6f7f}.src.zeitgeist{background:#b3541e}.src.user{background:#7048a8}.src.standing{background:#3a7d54}
.when{margin-left:auto;color:var(--muted);font-weight:600}
h2{font:600 20px/1.25 var(--serif);margin:0 0 10px;text-wrap:balance}
.why{font-size:13.5px;color:var(--muted);margin:0 0 14px}.why strong{color:var(--ink)}
img{width:100%;display:block;border-radius:9px;border:1px solid var(--line);margin:0 0 12px}
img.hero{aspect-ratio:3/2;object-fit:cover}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:8px}.charts img{margin:0}
.gist{font:400 14.5px/1.6 var(--serif);margin:2px 0 14px}
.scores{border-top:1px solid var(--line);padding-top:12px;margin-top:6px}
.stot{font:600 13px/1 var(--sans);margin-bottom:10px}.bonus{color:var(--accent);font-weight:600;margin-left:6px}
.dim{display:grid;grid-template-columns:120px 1fr 34px;align-items:center;gap:8px;margin:4px 0;font-size:11px;color:var(--muted)}
.dl em{font-style:normal;font-size:9px;padding:1px 4px;border-radius:4px;background:var(--track);margin-left:3px}
.dl em.llm{color:var(--accent)}
.track{height:7px;background:var(--track);border-radius:4px;overflow:hidden}
.fill{display:block;height:100%;background:var(--accent);border-radius:4px}
.dv{font-family:var(--mono);text-align:right;color:var(--ink)}
.prov{margin:10px 0 0;font-size:11px;display:flex;flex-direction:column;gap:2px}.prov a{color:var(--accent);text-decoration:none;word-break:break-all}
.pick{margin-top:12px;padding-top:10px;border-top:1px dashed var(--line);font-size:11.5px;color:var(--muted)}
.pick code{font-family:var(--mono);color:var(--ink);background:var(--track);padding:2px 5px;border-radius:5px;font-size:11px}
/* PDF / print: one big legible card per page */
@media print{
 :root{--bg:#fff}
 .wrap{max-width:none;padding:0}
 .grid{grid-template-columns:1fr;gap:0}
 .card{border:none;border-radius:0;padding:0 12px 8px}
 .card + .card{page-break-before:always}
 img,.scores,.dim,.charts{page-break-inside:avoid}
 h2{font-size:26px}.gist{font-size:16px;line-height:1.65}.why{font-size:15px}
 .dim{grid-template-columns:150px 1fr 40px;font-size:12px}
}
"""


def render_briefing(shortlist, out_path: Path, as_of: date) -> str:
    cards = "".join(_card(i, c) for i, c in enumerate(shortlist.cards)).replace("{AS_OF}", as_of.isoformat())
    n = len(shortlist.all_candidates)
    ok = sum(1 for c in shortlist.all_candidates if c.readiness and c.readiness.groundable)
    body = (f'<div class="wrap"><header><h1>Morning briefing — {as_of:%A %d %B %Y}</h1>'
            f'<p>{len(shortlist.cards)} recommended from {n} candidates ({ok} groundable). '
            f'Each card is the article as a skeleton; pick one to write in full.</p></header>'
            f'<div class="grid">{cards}</div></div>')
    css = _CSS.replace("__ACCENT__", _ACCENT)
    doc = (f"<!doctype html><html><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>ATS briefing {as_of.isoformat()}</title><style>{css}</style></head><body>{body}</body></html>")
    out_path.write_text(doc)
    return str(out_path)
