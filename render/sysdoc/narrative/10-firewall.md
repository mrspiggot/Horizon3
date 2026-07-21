## The number firewall

Every design decision in this repo defends a single rule from `CLAUDE.md`: **the LLM
never authors a number.** Numbers are produced by *executing* a catalogued model on UMD
data; the LLM only **selects** which model to run, **designs** how to show it, and
**narrates** what it means. A companion rule keeps rendering deterministic — no
diffusion model touches a numeric artifact.

The firewall is enforced structurally, not by asking nicely. The Chart Studio agents
are shown a *data profile* — field names, types, ranges — and never the values. They
emit an encoding that references field names with its `data` array **forced empty**; the
compiler injects the real rows at render time.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'Helvetica,Arial,sans-serif','fontSize':'14px','primaryColor':'#eef2f7','primaryBorderColor':'#1A2238','primaryTextColor':'#1A2238','lineColor':'#54617a'}}}%%
flowchart LR
  subgraph DET["DETERMINISTIC — disposes"]
    direction TB
    EX[(UMD executor<br/>runs the model)]:::data
    NO[NumberObject<br/>value + provenance]:::det
    CO[compile: inject rows<br/>→ matplotlib PNG]:::det
  end
  subgraph LLMD["LLM — proposes"]
    direction TB
    PROF[data PROFILE<br/>names · types · ranges]:::llm
    ENC[chart FORM<br/>mark + encoding, data=∅]:::llm
    NAR[prose narration]:::llm
  end
  EX --> NO
  NO -->|"schema only,<br/>no values"| PROF
  PROF --> ENC
  ENC -->|"encoding"| CO
  NO -->|"real rows,<br/>at render time"| CO
  NO --> NAR
  CO --> OUT[["chart PNG"]]:::ext
  classDef llm fill:#e8e7fb,stroke:#5b57c7,color:#2a2870;
  classDef det fill:#e6ebf3,stroke:#5b6b86,color:#2b3750;
  classDef data fill:#f6ecd6,stroke:#b5852b,color:#6b4e12;
  classDef ext fill:#f6e2df,stroke:#b0574d,color:#6e2c25;
```
