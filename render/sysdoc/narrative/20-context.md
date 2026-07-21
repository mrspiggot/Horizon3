## System context

Two triggers start work: a **persona** commissioned directly, or the **ATS**
(article-trigger system) surfacing a candidate from central-bank calendars, data
releases and standing pieces. The engine reaches one LLM (`claude-opus-4-8`, used for
both reasoning and vision) and two data systems inside the external UMD platform:
**TimescaleDB/Postgres** for the time series and executed outputs, and the **Neo4j
model spine** for the proven-model vocabulary. The ChromaDB corpus is a dashed,
design-time input — see the honesty note under the spine.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'Helvetica,Arial,sans-serif','fontSize':'14px','primaryColor':'#eef2f7','primaryBorderColor':'#1A2238','primaryTextColor':'#1A2238','lineColor':'#54617a'}}}%%
flowchart TB
  P([Persona commission]):::actor
  T([ATS trigger<br/>CB calendars · releases]):::actor
  subgraph H3["HORIZON3 ENGINE — render/"]
    ENG[Article pipeline<br/>+ Selector · Studio · Judge]:::det
  end
  LLM{{"claude-opus-4-8<br/>reasoning + vision"}}:::llm
  PG[(UMD TimescaleDB<br/>localhost:5434<br/>observations · outputs)]:::ext
  NEO[(Neo4j model spine<br/>horizon-neo4j : 7688)]:::data
  CH[(ChromaDB corpus<br/>design-time only)]:::ext
  OUT[[".docx article · charts<br/>infographic · ATS briefing"]]:::ext
  P --> ENG
  T --> ENG
  ENG <-->|"structured prompts"| LLM
  ENG -->|"SQL · executor"| PG
  ENG -->|"Cypher"| NEO
  CH -.->|"grounds design, not runtime"| ENG
  ENG --> OUT
  classDef actor fill:#ffffff,stroke:#54617a,color:#1A2238;
  classDef llm fill:#e8e7fb,stroke:#5b57c7,color:#2a2870;
  classDef det fill:#e6ebf3,stroke:#5b6b86,color:#2b3750;
  classDef data fill:#f6ecd6,stroke:#b5852b,color:#6b4e12;
  classDef ext fill:#f6e2df,stroke:#b0574d,color:#6e2c25;
```
