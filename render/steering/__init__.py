"""Steering: the graph decides what to write.

The article set is no longer a hand-typed persona list. It is ENUMERATED from the spine — every
(decision-maker, currency) whose models are proven EXECUTABLE_IN that currency — with the near-misses
reported as data/porting gaps. This is the layer that turns the Neo4j spine from a per-persona lookup
into the thing that steers generation across models × currencies.
"""
from .enumerate import (Analysis, data_gaps, enumerate_analyses, load_facts,  # noqa: F401
                        port_backlog)
