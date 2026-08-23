# Alibi

Alibi verifies AI-generated code by actually running it, instead of asking another AI to read it and give an opinion.

Codex says a PR is done. We don't take its alibi at face value — we run the old code and the new code side by side and check what actually changed.

## Architecture

```
7. Verdict          → auto-approve, or flag a specific divergence for human review
6. Judgment (LLM)   → for each CONFIRMED divergence, does it match the ticket's intent?
5. Codex            → generates the code change from a plain-English ticket
4. Modal            → runs OLD code + NEW code safely, in isolated sandboxes
3. Greptile         → finds real call sites of the changed function in the codebase
2. Diff engine      → deterministic equality check: did the output actually change? (NO AI HERE)
1. Foundation       → same input to a pure function = same output, every time
```

**Core rule:** the diff engine (layer 2) never calls an LLM. It's a plain structural equality check — the same operation any test assertion uses. AI is only used for code generation (Codex), test-input generation, and divergence judgment. Everything else is deterministic.

### Data flow

```
Ticket (plain English)
   → Codex writes the code change
   → Greptile finds real callers of the changed function(s)
   → LLM generates realistic test inputs from those real usages
   → Modal runs OLD code + NEW code against identical inputs
   → Diff engine compares outputs (deterministic, no AI, just equality checks)
   → LLM classifies each divergence: intended (matches ticket) vs unintended (regression)
   → Verdict: auto-approve, or flag the specific divergence for a human
```

## Scope (hackathon)

Pure functions only: same input → same output, no DB calls, no timestamps, no randomness, no network calls, no signature changes. This keeps every layer above unambiguously true.

## Teammates

- [Girikratna Sharma](https://github.com/GirikratnaSharma)
- [Kartik Setti](https://github.com/karthikeyansett1)
- [Hritik Munde](https://github.com/hritikmunde)

## Setup

TBD — setup instructions will be added once the language/framework choices for the pipeline are finalized.

## Status

Scaffold only — pipeline implementation has not started yet.

---

Built for the YC Fast Hackathon, Aug 23 2026.
