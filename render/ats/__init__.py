"""ATS — the Agentic Triggering Subsystem. Decides WHAT article to write, and surfaces a shortlist of ~3
for the owner to pick (trigger proposes, human disposes). See render/ats/run.py::run_ats."""
from .run import run_ats

__all__ = ["run_ats"]
