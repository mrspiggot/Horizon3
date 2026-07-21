## How the agents are instructed

Prompts here are inline string literals inside each `nodes.py`, paired with a Pydantic
model via LangChain's `.with_structured_output(Model)`. There are no classic
function-calling tools — **the structured-output schema *is* the tool surface**, and
each schema's `Field(description=…)` text is itself part of the prompt.

The catalogue below is extracted statically: for each LLM/vision node, its
structured-output schema, the resolved model, and the **declared** temperature.
Note: `get_llm()` ignores temperature at runtime (Opus 4.8), so the value is shown for
call-site clarity, not runtime behaviour. The schema field tables that follow are pulled
from wherever each Pydantic class is actually defined.

**The principles the prompts encode:** LLM proposes / deterministic code disposes ·
start from the message, not a chart you like · never author a number (enforced in code) ·
look at the rendered pixels · constrain to a closed, proven vocabulary · feed rejection
reasons back as input rather than re-asking.
