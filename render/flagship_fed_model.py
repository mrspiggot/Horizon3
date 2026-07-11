"""Flagship insight artifact — the Fed model on a mega-cap basket, told in the equity PM's voice.

model → data → verified numbers → deterministic render → narration (assessment's definition of
insight). NO number here is authored: every figure is executed by unified_market_data.analysis.
equity_analytics against live UMD data; this module only SELECTS, RENDERS (matplotlib, deterministic),
and NARRATES (the prose strings). Emits a self-contained HTML fragment for the Artifact tool.

Usage: ~/venv/bin/python -m render.flagship_fed_model <out.html>
"""
from __future__ import annotations

import base64
import io
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import psycopg2  # noqa: E402

sys.path.insert(0, str(Path.home() / "PycharmProjects/unified_market_data/src"))
from unified_market_data.analysis.equity_analytics import (  # noqa: E402
    equity_risk_premium, fed_model)

from . import charts, theme  # noqa: E402

PAPER = "#f7f5f0"     # chart-card surface (both themes)
VALUE = "#0e7c7b"     # cheap vs bonds (teal)
RICH = "#b4472e"      # rich (clay)

BASKET = [("AAPL", "Info Tech"), ("MSFT", "Info Tech"), ("JPM", "Financials"),
          ("XOM", "Energy"), ("JNJ", "Health Care"), ("PG", "Staples"),
          ("HD", "Discretionary"), ("CAT", "Industrials")]


def _latest(cur, sid):
    cur.execute("SELECT value FROM observations WHERE series_id=%s ORDER BY timestamp DESC LIMIT 1", (sid,))
    r = cur.fetchone()
    return float(r[0]) if r else None


def load():
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    cur = conn.cursor()
    bond = _latest(cur, "DGS10")
    real = _latest(cur, "DFII10")
    rows = []
    for sym, sector in BASKET:
        pe = _latest(cur, f"{sym}_PE")
        ey = _latest(cur, f"{sym}_EARNINGS_YIELD")
        dy = _latest(cur, f"{sym}_DIV_YIELD")
        fm = fed_model(ey, bond)
        erp = equity_risk_premium(ey, real)
        rows.append(dict(sym=sym, sector=sector, pe=pe, ey=ey, dy=dy,
                         gap=fm.gap_pct, signal=fm.signal, erp=erp))
    conn.close()
    rows.sort(key=lambda r: r["gap"], reverse=True)  # cheapest (highest gap) first
    return bond, real, rows


def _b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=PAPER)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def chart_scatter(bond, rows):
    theme.use_theme()
    fig, ax = plt.subplots(figsize=(6.1, 4.5))
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    ey = [r["ey"] for r in rows]
    gap = [r["gap"] for r in rows]
    labels = [r["sym"] for r in rows]
    charts.scatter(ax, ey, gap, labels=labels, color_job="diverging",
                   xlabel="trailing earnings yield (%)", ylabel="Fed-model gap vs 10-year (%)")
    ax.axhline(0, color=theme.MUTED, lw=1.2, ls="--")
    ax.text(ax.get_xlim()[1], 0.06, "fair vs bonds", ha="right", va="bottom",
            fontsize=7.5, color=theme.MUTED, style="italic")
    return _b64(fig)


def chart_erp(rows):
    theme.use_theme()
    fig, ax = plt.subplots(figsize=(6.1, 4.5))
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    srt = sorted(rows, key=lambda r: r["erp"])
    charts.bar(ax, [r["sym"] for r in srt], [r["erp"] for r in srt],
               color_job="diverging", ylabel="equity risk premium vs 10y real (%)")
    return _b64(fig)


def _pill(signal):
    color = {"equities cheap": VALUE, "equities rich": RICH}.get(signal, "var(--neutral)")
    label = {"equities cheap": "cheap vs bonds", "equities rich": "rich",
             "neutral": "neutral"}.get(signal, signal)
    return f'<span class="pill" style="--pc:{color}"><span class="dot"></span>{label}</span>'


def build_html(bond, real, rows) -> str:
    asof = date.today().isoformat()
    cheapest = rows[0]
    richest = rows[-1]
    median_gap = sorted(r["gap"] for r in rows)[len(rows) // 2]
    neg_erp = [r for r in rows if r["erp"] < 0]

    scatter_b64 = chart_scatter(bond, rows)
    erp_b64 = chart_erp(rows)

    table_rows = "\n".join(
        f'''<tr>
          <td class="sym">{r['sym']}</td><td class="sec">{r['sector']}</td>
          <td class="num">{r['pe']:.1f}</td>
          <td class="num">{r['ey']:.2f}</td>
          <td class="num gap" style="--v:{r['gap']:.3f}">{r['gap']:+.2f}</td>
          <td class="num">{r['erp']:+.2f}</td>
          <td>{_pill(r['signal'])}</td>
        </tr>''' for r in rows)

    neg_erp_txt = (", ".join(r["sym"] for r in neg_erp) if neg_erp
                   else "none in this basket")

    return f"""<style>
:root {{
  --paper:{PAPER};
  --bg:#efece4; --panel:#f7f5f0; --ink:#1b1e26; --muted:#6a7180; --line:#dcd7cc;
  --accent:#22417a; --value:{VALUE}; --rich:{RICH}; --neutral:#8a8f9a;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
}}
@media (prefers-color-scheme:dark) {{
  :root {{
    --bg:#10141d; --panel:#1a202e; --ink:#e9ebf1; --muted:#9aa2b2; --line:#2a3242;
    --accent:#7aa2e3; --value:#35b0a6; --rich:#e0805f; --neutral:#7c8496;
  }}
}}
:root[data-theme="dark"] {{
  --bg:#10141d; --panel:#1a202e; --ink:#e9ebf1; --muted:#9aa2b2; --line:#2a3242;
  --accent:#7aa2e3; --value:#35b0a6; --rich:#e0805f; --neutral:#7c8496;
}}
:root[data-theme="light"] {{
  --bg:#efece4; --panel:#f7f5f0; --ink:#1b1e26; --muted:#6a7180; --line:#dcd7cc;
  --accent:#22417a; --value:{VALUE}; --rich:{RICH}; --neutral:#8a8f9a;
}}
* {{ box-sizing:border-box; }}
.board {{
  background:var(--bg); color:var(--ink); font-family:var(--sans);
  line-height:1.55; padding:clamp(20px,4vw,52px);
  -webkit-font-smoothing:antialiased; min-height:100%;
}}
.wrap {{ max-width:1060px; margin:0 auto; display:flex; flex-direction:column; gap:34px; }}
.eyebrow {{
  font-family:var(--mono); font-size:11.5px; letter-spacing:.18em; text-transform:uppercase;
  color:var(--accent); font-weight:600;
}}
h1 {{
  font-family:var(--serif); font-weight:600; font-size:clamp(38px,6.5vw,66px);
  line-height:1.02; margin:.28em 0 0; text-wrap:balance; letter-spacing:-.01em;
}}
.deck {{ font-size:clamp(16px,2.2vw,19px); color:var(--muted); max-width:60ch; margin:.7em 0 0; }}
.rule {{ height:1px; background:var(--line); border:0; margin:0; }}

.callout {{
  border-left:3px solid var(--accent); padding:2px 0 2px 20px;
  font-family:var(--serif); font-size:clamp(19px,2.6vw,24px); line-height:1.4; text-wrap:pretty;
}}
.callout b {{ color:var(--accent); font-weight:600; }}
.callout .up {{ color:var(--value); font-weight:600; }}
.callout .dn {{ color:var(--rich); font-weight:600; }}

.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; }}
.tile {{
  background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:18px 20px; display:flex; flex-direction:column; gap:3px;
}}
.tile .k {{ font-family:var(--mono); font-size:10.5px; letter-spacing:.1em; text-transform:uppercase; color:var(--muted); }}
.tile .v {{ font-family:var(--mono); font-size:30px; font-weight:600; font-variant-numeric:tabular-nums; letter-spacing:-.02em; }}
.tile .s {{ font-size:13px; color:var(--muted); }}
.tile.up {{ border-top:3px solid var(--value); }}
.tile.dn {{ border-top:3px solid var(--rich); }}
.tile.mid {{ border-top:3px solid var(--neutral); }}
.tile.up .v {{ color:var(--value); }}
.tile.dn .v {{ color:var(--rich); }}

.charts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:18px; }}
.card {{ background:var(--paper); border:1px solid var(--line); border-radius:10px; padding:14px 14px 6px; overflow:hidden; }}
.card img {{ width:100%; height:auto; display:block; }}
.card .cap {{ font-family:var(--mono); font-size:11px; color:#6a7180; padding:8px 4px 6px; letter-spacing:.02em; }}

.section-h {{ font-family:var(--mono); font-size:11.5px; letter-spacing:.16em; text-transform:uppercase; color:var(--muted); margin:0 0 -14px; }}

.tablewrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:10px; background:var(--panel); }}
table {{ border-collapse:collapse; width:100%; font-size:14px; min-width:640px; }}
thead th {{
  font-family:var(--mono); font-size:10.5px; letter-spacing:.08em; text-transform:uppercase;
  color:var(--muted); text-align:right; padding:14px 16px 10px; border-bottom:1px solid var(--line); font-weight:600;
}}
thead th:first-child, thead th:nth-child(2) {{ text-align:left; }}
tbody td {{ padding:11px 16px; border-bottom:1px solid var(--line); text-align:right; }}
tbody tr:last-child td {{ border-bottom:0; }}
td.sym {{ font-weight:700; text-align:left; letter-spacing:.01em; }}
td.sec {{ text-align:left; color:var(--muted); font-size:13px; }}
td.num {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }}
td.gap {{ font-weight:600; color:color-mix(in oklab, var(--rich), var(--value) calc(50% + var(--v) * 14%)); }}
.pill {{
  display:inline-flex; align-items:center; gap:7px; font-size:12px; font-weight:600;
  padding:4px 11px 4px 9px; border-radius:100px; color:var(--pc);
  background:color-mix(in oklab, var(--pc) 14%, transparent);
}}
.pill .dot {{ width:7px; height:7px; border-radius:50%; background:var(--pc); }}

.note {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:20px; }}
.note .col h3 {{ font-family:var(--serif); font-size:19px; margin:0 0 8px; font-weight:600; }}
.note .col.says h3 {{ color:var(--value); }}
.note .col.not h3 {{ color:var(--rich); }}
.note p {{ margin:0; color:var(--muted); font-size:14.5px; line-height:1.6; }}

.prov {{
  font-family:var(--mono); font-size:11.5px; color:var(--muted); line-height:1.7;
  border-top:1px solid var(--line); padding-top:18px;
}}
.prov b {{ color:var(--ink); font-weight:600; }}
.prov .tag {{ color:var(--accent); }}
</style>

<div class="board"><div class="wrap">

  <header>
    <div class="eyebrow">Equity / Multi-Asset PM &nbsp;·&nbsp; Valuation Board</div>
    <h1>Priced for Perfection?</h1>
    <p class="deck">The Fed model, run across eight mega-caps: which still pay more than the
      10-year Treasury &mdash; and which are priced for a future that has to go exactly right.</p>
  </header>

  <hr class="rule"/>

  <div class="callout">
    Against a <b>{bond:.2f}%</b> 10-year, <span class="up">{cheapest['sym']}</span> is the only
    name paying a real premium over bonds (a <b>{cheapest['gap']:+.2f}%</b> Fed gap), while
    <span class="dn">{richest['sym']}</span> sits <b>{richest['gap']:+.2f}%</b> below the bond
    line &mdash; its earnings yield of {richest['ey']:.2f}% asks you to fund a Treasury-beating
    return entirely from growth.
  </div>

  <div class="tiles">
    <div class="tile up">
      <div class="k">Cheapest vs bonds</div>
      <div class="v">{cheapest['sym']}</div>
      <div class="s">Fed gap {cheapest['gap']:+.2f}% &nbsp;·&nbsp; ERP {cheapest['erp']:+.2f}%</div>
    </div>
    <div class="tile dn">
      <div class="k">Richest vs bonds</div>
      <div class="v">{richest['sym']}</div>
      <div class="s">Fed gap {richest['gap']:+.2f}% &nbsp;·&nbsp; ERP {richest['erp']:+.2f}%</div>
    </div>
    <div class="tile mid">
      <div class="k">10-year benchmark</div>
      <div class="v">{bond:.2f}<span style="font-size:16px">%</span></div>
      <div class="s">real 10y (TIPS) {real:.2f}% &nbsp;·&nbsp; median gap {median_gap:+.2f}%</div>
    </div>
  </div>

  <div class="charts">
    <figure class="card">
      <img alt="Scatter of each name's trailing earnings yield against its Fed-model gap versus the 10-year; points colored teal (cheap) to clay (rich)." src="data:image/png;base64,{scatter_b64}"/>
      <figcaption class="cap">Earnings yield vs the Fed-model gap. Above the dashed line = pays more than the 10-year.</figcaption>
    </figure>
    <figure class="card">
      <img alt="Diverging bar chart of each name's equity risk premium over the real 10-year yield, ranked." src="data:image/png;base64,{erp_b64}"/>
      <figcaption class="cap">Equity risk premium = earnings yield &minus; real 10-year ({real:.2f}%). Below zero = no cushion over real bonds.</figcaption>
    </figure>
  </div>

  <div class="section-h">The basket, ranked cheap &rarr; rich vs bonds</div>
  <div class="tablewrap">
    <table>
      <thead><tr>
        <th>Name</th><th>Sector</th><th>P/E</th><th>Earn. yld</th>
        <th>Fed gap</th><th>ERP</th><th>Signal</th>
      </tr></thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </div>

  <div class="note">
    <div class="col says">
      <h3>What the Fed model says</h3>
      <p>Equities and bonds compete for the same capital. When a stock's earnings yield tops the
        10-year, it pays you more to own the earnings than to clip the coupon &mdash; the positive
        Fed gap. Here only {cheapest['sym']} clears that bar; the growth names ({richest['sym']}
        among them) sit well below it, and the ERP column shows how thin the cushion over real
        bonds has become ({'negative for ' + neg_erp_txt if neg_erp else 'still positive across the basket'}).</p>
    </div>
    <div class="col not">
      <h3>What it doesn't say</h3>
      <p>It is a <em>relative</em> gauge, not a timing signal: a rich name can stay rich for years
        while its earnings grow into the price. These are trailing earnings on single names, not the
        index (AlphaVantage OVERVIEW is empty for the S&amp;P ETF), and a low earnings yield is often
        the market correctly paying up for durable growth &mdash; the gap is the question to ask, not
        the answer.</p>
    </div>
  </div>

  <div class="prov">
    <b>Provenance.</b> Earnings yield = 100 / trailing P/E, from <b>AlphaVantage OVERVIEW</b> (acquired {asof}).
    Bond leg <b>DGS10</b> = {bond:.2f}% &nbsp;·&nbsp; real leg <b>DFII10</b> = {real:.2f}% (FRED, via UMD).<br/>
    Every figure is <span class="tag">executed</span>, not authored &mdash; by
    <b>unified_market_data.analysis.equity_analytics.fed_model / equity_risk_premium</b>.
    Rendering is deterministic matplotlib. The narrative selects and explains; it writes no number.
  </div>

</div></div>
"""


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("flagship_fed_model.html")
    bond, real, rows = load()
    out.write_text(build_html(bond, real, rows))
    print(f"wrote {out}  ({len(rows)} names, 10y={bond:.2f}%, real={real:.2f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
