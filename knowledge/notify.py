"""Lightweight notifications for the curation utility.

Mirrors the pattern of unified_market_data/services/notify.py (file log +
desktop + optional email) but is self-contained so Horizon3 stays decoupled from
UMD. Policy: everything logs; a digest goes to desktop (macOS) and, if SMTP is
configured in the environment, to email. Failures never raise.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import subprocess
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger("horizon3.knowledge")

_LOG = Path(__file__).resolve().parent / "digests" / "notify.log.jsonl"


def notify(subject: str, body: str, *, level: str = "info", email: bool = False) -> None:
    """Log always; desktop-notify on macOS; email only when asked AND configured."""
    ts = datetime.now(timezone.utc).isoformat()
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        with _LOG.open("a") as f:
            f.write(json.dumps({"ts": ts, "level": level, "subject": subject}) + "\n")
    except OSError:
        pass
    logger.info("[%s] %s", level, subject)

    # macOS desktop banner (best-effort)
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{subject[:180]}" with title "Horizon3 corpus"'],
            check=False, capture_output=True, timeout=5,
        )
    except Exception:
        pass

    if email and os.environ.get("SMTP_HOST"):
        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = os.environ.get("SMTP_FROM", os.environ["SMTP_USER"])
            msg["To"] = os.environ.get("SMTP_TO", os.environ["SMTP_USER"])
            with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587))) as s:
                s.starttls()
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
                s.send_message(msg)
        except Exception as e:  # never fail the job on notification
            logger.warning("email notify failed: %s", e)
