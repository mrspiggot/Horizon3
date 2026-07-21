## The pipeline, end to end

The article graph threads a single `ArticleState` object through its nodes. Its design
intent, quoted in the source: charts, prose, and the dashboard are *projections of ONE
state rather than three artifacts built from three unsynchronised sources*. The `draft`
node is an atomic best-of-N loop — write, ground, critique, keep-best — and the two
`reconcile_*` nodes are the consistency stage the predecessor never had: they build the
charts the prose actually names and derive the dashboard from the finished article.

The DAG below is extracted from the compiled `article_graph`; node colour is its kind
(LLM / vision / deterministic) and hexagons mark gates.
