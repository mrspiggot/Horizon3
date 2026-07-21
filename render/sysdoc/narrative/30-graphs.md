## The graphs

The subsystem is a set of LangGraph graphs that share one house pattern: a `state.py`
TypedDict, `nodes.py` of pure `State → partial-State` functions, and a `graph.py` that
wires the `StateGraph` — every step traced to LangSmith. The article pipeline is the
orchestrator; it invokes the selector, studio and judge as sub-graphs. The ATS is a
separate, hand-coded commissioning orchestrator (not a StateGraph) that decides *what*
to write before the pipeline decides *how*.

The roster below is generated from the compiled graphs. The small DAGs (selector,
judge, ATS) follow; the orchestrator and the studio get their own sections.
