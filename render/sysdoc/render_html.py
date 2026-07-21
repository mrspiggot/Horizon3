"""Render the manifest+narrative to a self-contained, theme-aware HTML document.

Converts the SAME markdown that `render_md` emits (so the two never diverge), turning
```mermaid fences into <pre class="mermaid"> and wrapping tables for horizontal scroll,
then wraps it in the house design shell (navy ink, node-kind palette, light/dark).
Mermaid is loaded from a CDN for local/GitHub viewing; in a published Artifact the
runtime renders it natively.
"""
from __future__ import annotations

import re
from pathlib import Path

import mistune

from .manifest import MANIFEST_PATH, SystemManifest
from .render_md import assemble_markdown

DEFAULT_HTML = MANIFEST_PATH.parent / "agentic-system-design.generated.html"

_CSS = """
:root{
  --ink:#1A2238; --paper:#f4f6fa; --surface:#fff; --surface-2:#eef2f7;
  --muted:#54617a; --faint:#7c88a0; --hairline:#d7dee8; --hairline-2:#e6ebf3;
  --accent:#a9761f; --accent-soft:#f4ead4; --accent-ink:#6b4e12;
  --code-bg:#eef1f6; --code-ink:#2b3750;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
  --sans:"Helvetica Neue",Helvetica,system-ui,-apple-system,"Segoe UI",Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --ink:#e7ecf5; --paper:#0f1420; --surface:#161d2c; --surface-2:#1c2534;
  --muted:#9aa6bd; --faint:#7f8ba3; --hairline:#28313f; --hairline-2:#222b3a;
  --accent:#e0a94a; --accent-soft:#2a2314; --accent-ink:#e8c274;
  --code-bg:#1b2431; --code-ink:#c7d2e6;
}}
:root[data-theme="light"]{--ink:#1A2238;--paper:#f4f6fa;--surface:#fff;--surface-2:#eef2f7;--muted:#54617a;--faint:#7c88a0;--hairline:#d7dee8;--hairline-2:#e6ebf3;--accent:#a9761f;--accent-soft:#f4ead4;--accent-ink:#6b4e12;--code-bg:#eef1f6;--code-ink:#2b3750;}
:root[data-theme="dark"]{--ink:#e7ecf5;--paper:#0f1420;--surface:#161d2c;--surface-2:#1c2534;--muted:#9aa6bd;--faint:#7f8ba3;--hairline:#28313f;--hairline-2:#222b3a;--accent:#e0a94a;--accent-soft:#2a2314;--accent-ink:#e8c274;--code-bg:#1b2431;--code-ink:#c7d2e6;}
*{box-sizing:border-box;}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.62;font-size:17px;margin:0;-webkit-font-smoothing:antialiased;}
.doc{max-width:820px;margin:0 auto;padding:32px 24px 90px;}
h1{font-family:var(--serif);font-weight:600;font-size:clamp(2rem,4.6vw,3rem);line-height:1.06;letter-spacing:-.015em;margin:.4em 0 .5em;text-wrap:balance;}
h2{font-weight:750;font-size:clamp(1.5rem,3vw,2rem);letter-spacing:-.01em;margin:1.7em 0 .5em;padding-top:.5em;border-top:1px solid var(--hairline-2);text-wrap:balance;}
h3{font-weight:700;font-size:1.16rem;margin:1.5em 0 .4em;color:var(--ink);}
p{margin:0 0 1em;}
a{color:var(--accent);text-decoration:none;border-bottom:1px solid color-mix(in srgb,var(--accent) 40%,transparent);}
strong{font-weight:700;}
em{color:var(--muted);}
code{font-family:var(--mono);font-size:.85em;background:var(--code-bg);color:var(--code-ink);padding:.1em .38em;border-radius:4px;border:1px solid var(--hairline-2);}
pre{background:var(--code-bg);color:var(--code-ink);border:1px solid var(--hairline-2);border-radius:8px;padding:14px 16px;overflow-x:auto;font-family:var(--mono);font-size:12.6px;line-height:1.5;}
pre code{background:none;border:none;padding:0;}
ul,ol{margin:0 0 1em;padding-left:1.3em;}
li{margin:.35em 0;}
li::marker{color:var(--accent);}
blockquote{border-left:3px solid var(--accent);background:var(--accent-soft);color:var(--ink);margin:1.4em 0;padding:12px 18px;border-radius:0 8px 8px 0;}
blockquote p{margin:.3em 0;}
.tablewrap{overflow-x:auto;margin:1.2em 0;border:1px solid var(--hairline);border-radius:10px;}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:520px;}
th,td{text-align:left;padding:9px 13px;border-bottom:1px solid var(--hairline-2);vertical-align:top;}
thead th{background:var(--surface-2);font-weight:700;font-size:12px;letter-spacing:.03em;text-transform:uppercase;border-bottom:2px solid var(--hairline);}
tbody tr:last-child td{border-bottom:none;}
tbody tr:hover{background:color-mix(in srgb,var(--accent) 6%,transparent);}
td code,th code{font-size:.82em;}
.mermaid{background:#fbfcfe;border:1px solid var(--hairline);border-radius:12px;padding:16px;margin:1.3em 0;overflow-x:auto;text-align:center;}
.topbar{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:12px;padding:9px 24px;background:color-mix(in srgb,var(--paper) 88%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--hairline);font-size:13px;}
.topbar b{color:var(--accent);}
.topbar .sp{margin-left:auto;}
.themebtn{cursor:pointer;border:1px solid var(--hairline);background:var(--surface);color:var(--ink);border-radius:20px;padding:4px 12px;font:inherit;font-size:12px;}
"""

_MERMAID_LOADER = """
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  const dark = matchMedia('(prefers-color-scheme: dark)').matches;
  mermaid.initialize({ startOnLoad: true, securityLevel: 'loose' });
</script>
<script>
  (function(){
    var b=document.getElementById('themebtn');
    if(!b)return;
    b.addEventListener('click',function(){
      var r=document.documentElement;
      var cur=r.getAttribute('data-theme')|| (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
      r.setAttribute('data-theme', cur==='dark'?'light':'dark');
    });
  })();
</script>
"""


class _Renderer(mistune.HTMLRenderer):
    def block_code(self, code, info=None):
        if (info or "").strip() == "mermaid":
            return f'<pre class="mermaid">\n{code}\n</pre>\n'
        return super().block_code(code, info)


_md = mistune.create_markdown(renderer=_Renderer(), plugins=["table", "strikethrough"])


def _wrap_tables(html: str) -> str:
    return re.sub(r"(<table[\s\S]*?</table>)", r'<div class="tablewrap">\1</div>', html)


def render_html(m: SystemManifest) -> str:
    body = _wrap_tables(_md(assemble_markdown(m)))
    v = m.version
    stamp = f"{v.pyproject or '?'} · {v.git_sha or '?'}"
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Horizon3 — Agentic System Design (generated)</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n"
        '<div class="topbar"><span>Horizon3 · <b>Agentic System Design</b></span>'
        f'<span class="sp"></span><span style="color:var(--muted)">{stamp}</span>'
        '<button class="themebtn" id="themebtn">◑ theme</button></div>\n'
        f'<main class="doc">\n{body}\n</main>\n{_MERMAID_LOADER}\n</body>\n</html>\n'
    )


def write_html(m: SystemManifest, path: Path = DEFAULT_HTML) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(m), encoding="utf-8")
    return path
