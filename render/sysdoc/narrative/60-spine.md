## The GraphRAG model spine

The live GraphRAG in this system is the **Neo4j model spine**. A `Model` node carries
`executable:true` *only after it actually ran*, alongside the run's `points` and
`as_of`. The selector's retrieval returns that closed set, and the LLM chooses among it.
It *cannot* pick a model that does not exist or cannot run, because it is never offered
one. The retrieval query:

```
MATCH (m:Model {catalog:'horizon3', executable:true})
OPTIONAL MATCH (m)-[:PRODUCES]->(o:Output)
OPTIONAL MATCH (m)-[:RENDERS]->(v:Visualization)
RETURN m.id, m.name, m.family, m.points, m.as_of, collect(o.name), collect(v.insight)
```

> **Honesty note — read before citing "RAG":** the Neo4j spine is the only retrieval
> that feeds an agent at runtime. The **ChromaDB corpus under `knowledge/` is
> design-time grounding only** — it is queried by humans, not imported by any node in
> `render/`. A runtime literature-RAG is a planned future step, not a shipped feature.

The census below is read live from `bolt://localhost:7688`. If the spine is offline when
this doc is built, the counts are omitted and this section says so — the doc still
renders.
