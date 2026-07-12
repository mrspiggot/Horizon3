"""LLM + observability setup for the Chart Studio.

One place to construct the reasoning model (Claude Opus — multimodal, so it also serves the
vision critique) and to wire LangSmith tracing so every Studio run is inspectable. Keys come
from Horizon3's .env (ANTHROPIC_API_KEY) and the LangSmith vars already present in sibling
.envs; we load them without ever printing a value.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _load_env() -> None:
    """Load ANTHROPIC_API_KEY + LANGSMITH_* from H3's .env (and kalshi's as a fallback) if not
    already in the environment. Never prints values."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for p in (Path.home() / "PycharmProjects/Horizon3/.env",
              Path.home() / "PycharmProjects/kalshi/.env"):
        if p.exists():
            load_dotenv(p, override=False)
    # LangSmith: enable tracing to a Studio project if a key is present.
    if os.environ.get("LANGSMITH_API_KEY") and not os.environ.get("LANGSMITH_TRACING"):
        os.environ["LANGSMITH_TRACING"] = "true"
    os.environ.setdefault("LANGSMITH_PROJECT", "horizon3-chart-studio")


# Model IDs (CLAUDE.md): Opus 4.8 is the most capable current model and is multimodal.
REASONING_MODEL = "claude-opus-4-8"
VISION_MODEL = "claude-opus-4-8"


@lru_cache(maxsize=4)
def get_llm(model: str = REASONING_MODEL, temperature: float | None = None, max_tokens: int = 4096):
    """A cached ChatAnthropic. temperature is omitted — Opus 4.8 deprecates it (proposer
    diversity comes from per-form prompts instead). Kept in the signature for call-site clarity."""
    _load_env()
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=model, max_tokens=max_tokens, timeout=120)
