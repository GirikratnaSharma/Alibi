# Alibi

Alibi verifies AI-generated code by actually running it, instead of asking another AI to read it and give an opinion.

Codex says a PR is done. We don't take its alibi at face value — we run the old code and the new code side by side and check what actually changed.

## Architecture

```
7. Verdict          → auto-approve, or flag a specific divergence for human review
6. Judgment (LLM)   → for each CONFIRMED divergence, does it match the ticket's intent?
5. Codex            → generates the code change from a plain-English ticket
4. Modal            → runs OLD code + NEW code safely, in isolated sandboxes
3. Call-site evidence → validated checked-in locations; no live query dependency
2. Diff engine      → deterministic equality check: did the output actually change? (NO AI HERE)
1. Foundation       → same input to a pure function = same output, every time
```

**Core rule:** the diff engine (layer 2) never calls an LLM. It's a plain structural equality check — the same operation any test assertion uses. AI is only used for code generation (Codex), test-input generation, and divergence judgment. Everything else is deterministic.

### Data flow

```
Ticket (plain English)
   → Codex writes the code change
   → Checked-in call-site evidence validates representative callers
   → Hardcoded test inputs exercise the intended behavior
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

The test suite imports the pinned Modal dependency. Run it with the repository
virtual environment, where Modal is installed, rather than bare `python3`:

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

Step 3 uses validated checked-in call sites as the pipeline's sole source. Run
the standalone checkpoint with:

```bash
python3 src/greptile_call_sites.py --function calculate_discount
```

The script validates five checked-in source locations and emits structured
JSON. Greptile deprecated its codebase Query API and directed the project to PR
review instead, so Greptile review is shown only as a side-by-side comparison
and never feeds Alibi's pipeline.

## Status

The hardcoded Steps 1–7 pipeline works end to end. Greptile PR review remains a
separate demo comparison.

---

Built for the YC Fast Hackathon, Aug 23 2026.
