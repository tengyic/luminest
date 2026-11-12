# Full backend suite — measured aggregate after the fix, 2026-11-12

**2,289 passed / 0 failed / 2 skipped / 0 errors.** 2,291 collected. 8 warnings.
889.45 s (14 m 49 s), `PYTEST_EXIT=0`. This is the *aggregate after* the three red tests
were fixed; the earlier front-page row said that number had not been measured. It has now
been measured, once, in one process, on the shipping branch.

## What was measured

| Field | Value |
|---|---|
| Date | 2026-11-12, 11:11–11:26 local |
| Branch | `feature/a11y-i18n` |
| Commit | `c35d24fc7a7ca8a36334bf0690698f48695a37de` (`c35d24f`) |
| Working tree | one uncommitted documentation note (`harness/docs/evidence/2026-11-11/AC-3.txt`) and scratch logs; **no source, test, or fixture changes** |
| Interpreter | `harness/backend/.venv/bin/python` → CPython 3.14.3 |
| Host | macOS arm64, 16 GB |
| Scope | all 122 test files, `2291 tests collected` (see `collection.txt`) |

Command, from the workspace root:

```sh
mkdir -p outputs/qa/tmp
cd harness/backend
env -u PYTHONPATH \
  TMPDIR="<workspace>/outputs/qa/tmp" \
  PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -m pytest -q -rs -p no:cacheprovider \
  --basetemp="<workspace>/outputs/qa/bt"
```

`env -u PYTHONPATH` and a `--basetemp` **inside the workspace** are both required here:
the host injects a `sitecustomize` shim through `PYTHONPATH` that intercepts `mkdir` and
produces spurious collection errors, and the sandbox refuses a basetemp at the system temp
root. Running the same command without them fails at collection with errors that look like
product defects. A collect-only run made from the wrong working directory was discarded for
exactly that reason.

## The two skips

Both are explicit opt-in live-provider checks, reported by `-rs`:

```
SKIPPED [1] tests/test_diagram.py:255: Live DeepSeek diagram smoke disabled; set HARNESS_DIAGRAM_LIVE_SMOKE=1
SKIPPED [1] tests/test_live_smoke.py:39: Live smoke disabled; set HARNESS_LIVE_SMOKE=1
```

2289 + 2 = 2291 collected. A skip is not a pass; the release gate blocks on skipped tests
at every strictness level.

## Before → after

| Commit | Date | Result |
|---|---|---|
| `ab8bcda` | 2026-11-11 | 2,286 passed / **3 failed** / 2 skipped (2,291 collected) |
| `a7bfb6d` | 2026-11-11 | fixes the three tests and the release gate; only the affected files were re-run (130 passed) |
| `c35d24f` | 2026-11-12 | **2,289 passed / 0 failed / 2 skipped**, full suite, one process |

The arithmetic closes exactly: the three failures (`test_teacher_clone` resolving a
regenerated node id by title, `test_video_seed` re-keying/retiring orphaned curated video
rows, `test_mathkit` identifying the deliberate `function_probe` sentinel by its note) are
now passes; the two opt-in skips are unchanged. Nothing else moved.

## Do not confuse this with the 3.12 parity number

An uncommitted note in `harness/docs/evidence/2026-11-11/AC-3.txt` reports a separate
CPython 3.12 host run as `2286 passed / 5 skipped / 0 failed`. That is a **different
interpreter and a different skip profile** (live-provider smokes plus playwright-absent
checks), on a working tree, with no raw log archived alongside it. It is neither a
contradiction nor a substitute for this 3.14 aggregate. The number published on the front
page for the shipping branch is the one above.

## What this does not establish

- `c35d24f` is on the development branch, not on `main`. The `main` row in the front page
  (1,835 / 1 / 2 on `bbbe2e4`) is unchanged and still has its one environment-artefact
  failure.
- Layer 3 is measured separately and is **not green**: 6 passed / 1 blocked / 3 failed
  (`docs/evidence/native-layer3-2026-11-12/`).
- This is a test-suite result, not certification of content depth, signing, notarization,
  or fitness to ship.
