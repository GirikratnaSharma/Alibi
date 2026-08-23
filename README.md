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
- [Karthikeyan Setti](https://github.com/karthikeyansett1)
- [Hritik Munde](https://github.com/hritikmunde)

## Setup

The current checkpoints use Python's standard library, so no package install is
required. Run all local tests with:

```bash
python3 -m unittest discover -s tests -v
```

Step 3 requires a Greptile API key. Create one in Greptile, export it as
`GREPTILE_API_KEY`, and run:

```bash
python3 src/greptile_call_sites.py --function calculate_discount
```

The script reuses the authenticated GitHub CLI token unless `GITHUB_TOKEN` is
explicitly provided. It never writes either credential to disk or includes it
in output.

## Status

Steps 1–2 are implemented. Step 3's standalone Greptile integration and local
contract tests are implemented; live verification requires a Greptile API key
and an indexed repository.

---

Built for the YC Fast Hackathon, Aug 23 2026.
