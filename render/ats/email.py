"""Deliver the morning briefing — a legible PDF, emailed.

Renders the self-contained briefing HTML to a single-column PDF (Playwright print), then sends it as an
attachment via SMTP, reusing the same env vars as knowledge/notify.py (SMTP_HOST/PORT/USER/PASS/FROM).
The email BODY is a plain-text digest of the shortlist — the headline, the "why now", and the one-line
publish command for each — so the owner can decide from the phone and open the PDF for the full detail.
Sending is an explicit, owner-requested action to the owner's own address; nothing is sent without the
SMTP config being present.
"""
from __future__ import annotations

import os
import smtplib
from datetime import date
from email.message import EmailMessage
from pathlib import Path

_DEFAULT_TO = "richard.walker@lucidate.co.uk"


def render_pdf(html_path: Path, pdf_path: Path) -> Path:
    """Briefing HTML → a single-column, legible A4 PDF via headless chromium (print media)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page()
        pg.goto(Path(html_path).resolve().as_uri(), wait_until="networkidle")
        pg.emulate_media(media="print")
        pg.add_style_tag(content=(
            ".grid{grid-template-columns:1fr !important;gap:0}"
            ".card{border:none;padding:0 10px}"
            ".card + .card{page-break-before:always}"           # each new candidate starts a fresh page
            "img,.scores,.dim,.charts{page-break-inside:avoid}"  # never split a figure or the score block
            "h2{font-size:26px}.gist{font-size:16px;line-height:1.65}.why{font-size:15px}"
            ".dim{grid-template-columns:150px 1fr 40px;font-size:12px}"))
        pg.pdf(path=str(pdf_path), format="A4", print_background=True,
               margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
        br.close()
    return pdf_path


def _digest_body(shortlist, as_of: date) -> str:
    lines = [f"Horizon3 — morning briefing, {as_of:%A %d %B %Y}",
             f"{len(shortlist.cards)} recommended from {len(shortlist.all_candidates)} candidates.",
             "The full briefing (charts, infographic, gist, scores) is attached as a PDF.", ""]
    for i, card in enumerate(shortlist.cards, 1):
        c, art = card["candidate"], card.get("article") or {}
        s = c.scores.total if c.scores else 0
        lines += [f"{i}. [{c.source} · {c.persona}]  score {s:.2f}",
                  f"   {art.get('title', c.title)}",
                  f"   Why now: {c.rationale}",
                  f"   Publish: scripts/ats_briefing.py --as-of {as_of} --pick {c.id}", ""]
    return "\n".join(lines)


def send_briefing(shortlist, html_path, as_of: date, *, to: str = "") -> bool:
    """Email the briefing PDF. Returns True if sent; False (with a printed reason) if SMTP isn't set."""
    if not os.environ.get("SMTP_HOST"):
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        except Exception:
            pass
    if not os.environ.get("SMTP_HOST"):
        print("SMTP not configured (set SMTP_HOST/PORT/USER/PASS/FROM in .env) — briefing not emailed.")
        return False

    pdf = render_pdf(Path(html_path), Path(html_path).with_suffix(".pdf"))
    to = to or os.environ.get("SMTP_TO", _DEFAULT_TO)
    msg = EmailMessage()
    msg["Subject"] = f"Horizon3 morning briefing — {as_of:%d %b %Y} ({len(shortlist.cards)} to consider)"
    msg["From"] = os.environ.get("SMTP_FROM", os.environ["SMTP_USER"])
    msg["To"] = to
    msg.set_content(_digest_body(shortlist, as_of))
    msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf",
                       filename=f"morning_briefing_{as_of}.pdf")
    hp = Path(html_path)                                     # also the interactive self-contained HTML
    if hp.exists():
        msg.add_attachment(hp.read_bytes(), maintype="text", subtype="html",
                           filename=f"morning_briefing_{as_of}.html")
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587))) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
        print(f"briefing emailed to {to} (PDF: {pdf})")
        return True
    except Exception as exc:
        print(f"email failed: {type(exc).__name__}: {exc}")
        return False
