# Alibi — Architecture

## Pipeline layers

Each layer is built on top of the one below it. Layer 2 (the diff engine) is the load-bearing claim of the whole project: it is plain code, never an LLM call.

```mermaid
flowchart BT
    L1["1. Foundation<br/>pure function: same input → same output, every time"]
    L2["2. Diff engine<br/>deterministic equality check — NO AI HERE"]
    L3["3. Git AST + Greptile review<br/>finds callers deterministically; review is advisory"]
    L4["4. Modal<br/>runs OLD code + NEW code in isolated sandboxes"]
    L5["5. Codex<br/>generates the code change from a plain-English ticket"]
    L6["6. Judgment (LLM)<br/>does each CONFIRMED divergence match ticket intent?"]
    L7["7. Verdict<br/>auto-approve, or flag a specific divergence for human review"]

    L1 --> L2 --> L3 --> L4 --> L5 --> L6 --> L7

    style L2 fill:#2d5,stroke:#163,stroke-width:2px,color:#000
```

## End-to-end data flow

```mermaid
flowchart TD
    T["Ticket (plain English)"] --> CX["Codex writes the code change"]
    CX --> GR["Git AST finds callers; Greptile adds optional PR-review context"]
    GR --> IG["LLM generates schema-constrained inputs from those usages"]

    IG --> MO["Modal: run OLD code"]
    IG --> MN["Modal: run NEW code"]

    MO --> DIFF{{"Diff engine\ndeterministic equality check\nNO LLM"}}
    MN --> DIFF

    DIFF -->|"outputs identical"| APPROVE["Auto-approve"]
    DIFF -->|"outputs diverge"| CLS["LLM: classify divergence\nintended (matches ticket) vs unintended"]

    CLS -->|"intended"| APPROVE
    CLS -->|"unintended / regression"| FLAG["Flag for human review\n+ exact evidence (field/value that changed)"]
```

## Where AI is used vs. where it isn't

```mermaid
flowchart LR
    subgraph AI["Uses an LLM"]
        A1["Codex: code generation"]
        A2["Test-input generation from Greptile usages"]
        A3["Divergence classifier (intended vs. unintended)"]
    end
    subgraph DET["Deterministic — no LLM"]
        D1["Modal sandbox execution"]
        D2["Diff engine (structural equality check)"]
        D3["Verdict aggregation"]
    end
```

**Core rule:** the diff engine never calls an LLM. It's the same operation any test assertion uses — `assert old_output == new_output` — structured to report the exact field/value that changed. AI touches code generation, test-input generation, and judgment on *already-confirmed* diffs. It never touches the comparison itself.

## Scope boundary (hackathon)

Stay inside pure functions only:
- same input → same output, always
- no DB calls, no timestamps, no randomness, no network calls
- no change to the function's signature (same params in, before and after)

This is the only zone where every layer above is unambiguously true with zero caveats.

## Tech stack per layer

| Layer | Tool | Role |
|---|---|---|
| Code generation | OpenAI Codex | Writes the fix from the ticket |
| Usage discovery | Git + Python AST | Finds executable call sites deterministically |
| PR review context | Greptile | Adds optional advisory review comments from GitHub |
| Sandboxed execution | Modal | Runs OLD and NEW code in isolation, returns outputs |
| Diff engine | Plain Python/TypeScript | Deterministic structural equality check |
| Test input generation | LLM (Claude or GPT) | Turns real usage patterns into concrete test inputs |
| Divergence classifier | LLM (Claude or GPT) | Judges whether a CONFIRMED output change matches ticket intent |
| Memory (stretch) | Claude-Mem | Speeds up repeat verifications on similar code — build last |
