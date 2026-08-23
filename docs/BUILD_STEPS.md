# Alibi — Build Steps

Protect this sequence. Do not skip ahead to auto-generated inputs, side-effect tracking, or memory until the core loop (steps 1–7) works end to end on hardcoded inputs.

**Checkpoint discipline:** if step 3 or step 4 isn't working by roughly the hour-2 mark, stop pushing forward. Hardcode more, cut auto-generation entirely, and get a working demo on a simplified path instead.

## Step 0 — Repo setup (done)
- [x] Public GitHub repo created, single `main` branch
- [x] Scaffold: `src/`, `tests/`, `demo-repo/`, `docs/`
- [x] Teammates added as collaborators

## Step 1 — Demo repo
Build or curate a small codebase with one clean **pure function** to modify — e.g. a discount/pricing calculator.
- Lives in `demo-repo/`
- Same input → same output, no DB/network/time/randomness, stable signature
- Write the "before" version first; this is what Codex will patch in step 2
- Sanity check: can you call the function with 3–5 inputs by hand and predict the outputs?

## Step 2 — Codex generates a change
- Write a plain-English ticket describing a behavior change to the demo function (e.g. "add a 10% loyalty discount for orders over $100")
- Run Codex against `demo-repo/` with that ticket
- Confirm you can parse Codex's output: the diff, the new function body, which file/function it touched
- Save the ticket text somewhere structured (e.g. `demo-repo/tickets/001.md`) — layer 6 needs it later to judge intent

## Step 3 — Validated call-site evidence
- Keep 3–5 representative call sites checked in and validate them against the source
- Use those validated locations as the pipeline's sole call-site input
- Keep Greptile PR review as a side-by-side comparison only; it never feeds the pipeline

Standalone checkpoint command:

```bash
python3 src/greptile_call_sites.py --function calculate_discount
```

Greptile deprecated its codebase Query API and directed the project to its PR
review product. The pipeline therefore uses only the five manually verified
call sites in `demo-repo/call-sites/calculate_discount.json`. The standalone
script validates those locations against the checked-out source and emits
structured JSON. Greptile PR review is demonstrated separately and does not
provide pipeline input.

## Step 4 — Modal runs OLD vs NEW  *(high-risk unknown — test in isolation first)*
- Two isolated sandboxes: one loads the pre-Codex function, one loads the post-Codex function
- Start with **3–5 hardcoded test inputs** — skip auto-generation entirely for now
- Run both versions against the same inputs, capture both outputs
- Confirm you get clean structured output back from Modal (not just logs) — this is what step 5 consumes

## Step 5 — Diff engine (no AI, ever)
- Plain Python/TypeScript equality check between OLD output and NEW output
- On mismatch, report the exact field/value that changed, e.g. `discount_amount: 20 → 40`
- No model calls in this file/module, period — this is the one architectural rule not to bend
- Unit test the diff engine itself with a few known-equal and known-different pairs

## Step 6 — Divergence classifier
- Input: one CONFIRMED divergence (from step 5) + the original ticket text (from step 2)
- Output: `intended` (matches what the ticket asked for) or `unintended` (regression)
- Keep the prompt narrow — it only judges divergences the diff engine already confirmed, it never re-runs the comparison itself

## Step 7 — Verdict aggregation
- All divergences across all test inputs come back `intended` → **auto-approve**
- Any divergence comes back `unintended`, or a run errors → **flag**, attach the exact evidence (which input, which field, old value → new value)
- This is the object you'd show a human reviewer or print in a demo

**Stop and demo-test here.** Once steps 1–7 work end to end on the hardcoded path, you have a complete, honest demo. Everything below is upside, not required.

## Step 8 — Only after 1–7 work end to end
- Keep Greptile PR review separate from the hardcoded Alibi pipeline
- If time remains: wire in Claude-Mem so repeat verifications on similar code visibly recall prior context instead of starting cold — this is the "warm boot / speed" angle for the demo

## Guardrails (don't scope-creep into these during the hackathon)
- No side-effect tracking (DB writes, emails, API calls) — return-value comparison only
- No mocking/stubbing external dependencies
- No general-purpose "run any function from any repo" tooling
- No auto test-input generation before the hardcoded version works end to end

## Pitch accuracy (for the demo narrative)
- Say "the divergence-detection step is deterministic" — not "zero hallucination" or "100% AI-free"
- This proves behavior didn't unexpectedly change on the specific inputs tested — non-regression evidence, not a correctness guarantee
- The technique (differential/golden testing) isn't new — applying it to verifying AI-agent-generated changes is the actual pitch, and it's a more credible claim to a technical judge, not a weaker one
