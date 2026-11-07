# 00 — How to use this pack

You are working on Luminfest, a native macOS learning harness: SwiftUI client,
FastAPI backend, 102 endpoints, 51 agent tools, 37 tables, 1518 tests.

## The four layers, in order

1. `01-repo-map.md` — which file does what. Answers 'where is X' without a search.
2. `02-interfaces.md` — the contract surface. Answers 'what must not break'.
3. `03-tests.md` — the behavioural spec. Answers 'what is already promised'.
4. `04-open-gaps.md` — curated audit against the product brief. What is still missing.
5. The source itself — fetched on demand, one span at a time.

## Rules that keep the token bill down

- **Do not open a file to learn what it is for.** The map already says.
- **Fetch spans, not files.** Ask for the function you need, not the module.
- **Trust the test names.** Do not re-derive behaviour the names already state.
- **Ask for a task pack** if you need more than ~15 tool calls. That is a signal
  the pack is missing a layer, not a signal to read harder.

## Invariants — violating these still runs, and quietly harms learners

- Decision layers never collapse: `teaching/policy` (what to teach) · `session`
  (phase/turn) · `procedure` (activities) · `supervision` (should we interrupt) ·
  `classroom` (state machine). `classroom` imports supervision's primitives.
- `mastery_known` is not `mastery`. `PRIOR` 0.15 means 'no attempts yet'.
- Never punish. Away is not guilt; suspicion routes to a variant question or an
  explain-back, never to a detector or a ban.
- A plan is a promise. Only *existing* artifacts may be promised; missing ones
  become `skipped`. A plan that reshapes mid-session is not a lesson.
- Absence is designed: a missing provider degrades to a declared fallback with a
  reason. It never raises, and never fakes output.

## Environment traps

- `grep 'a\|b'` silently matches nothing on this box (toybox grep, no BRE
  alternation). Use `grep -E`. An empty result is not evidence until the query
  is proven to work.
- Tests need cwd `backend/` and a `TMPDIR`/`--basetemp` inside the repo.
- `swift build` needs `--disable-sandbox`. Never use `Bundle.module`.
