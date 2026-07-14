"""Horizon3 decorative illustration subsystem — the one place diffusion is allowed.

An article's header is an abstract van Gogh-style painting that evokes THAT article's finding (an LLM
art-director reads the actual insight and invents the scene). It is a painting, not an infographic, so
it carries no numeric-fidelity constraint. Fully isolated — imports nothing from the numeric pipeline
except the schema Block helper, and nothing from Horizon2.
"""
from .vangogh import art_director, illustration_block, illustration_png

__all__ = ["art_director", "illustration_png", "illustration_block"]
