# Playground archetype — build brief

You are writing **one archetype module** for the Luminfest simulator playground.
Read this whole file before writing code. It is the contract; the reference
implementation is `harness/backend/app/harness/playground/archetypes_core.py`
(`curve_shift`) — read that too, in full. Your module is a variation on it.

## What an archetype is

A reusable **interaction** with no content of its own. Content arrives as a JSON
*spec* whose shape the archetype declares. One archetype + one spec = one game.

## Your deliverable

Two files, both entirely yours (no other builder touches them):

1. `harness/backend/app/harness/playground/archetypes_<group>.py`
   — your archetypes, as `Archetype` objects.
2. `harness/backend/app/media_packs/playground_games_<group>.json`
   — one or two content specs per archetype you built.

Your assigned archetypes are listed at the end of this file.

## The Python shape

```python
from __future__ import annotations
from typing import Any, Mapping
from .archetypes import Archetype, Field

def _body(spec: Mapping[str, Any]) -> str:
    # Markup placed INSIDE the stage element. Build the SVG skeleton in the engine
    # instead when it depends on the spec; a fixed shell here is usually enough.
    return ('<div class="stagecol"><div class="scene-wrap">'
            '<svg class="scene" id="scene" viewBox="0 0 860 460"></svg></div>'
            '<div class="controls">...</div></div>')

_ENGINE = r"""
function build(root, spec) {
  // everything goes here
}
"""

THING = Archetype(
    id='thing',                       # snake_case, unique
    title='Thing',                    # short, title case
    blurb='One sentence a learner would understand.',
    interaction='drag X and watch Y', # the mechanic, one phrase
    subjects=('mathematics',),        # from: mathematics science economics
    tags=('graphs',),                 # free-form, 3-6 tags
    reference='Where the idea came from',
    telemetry='What the single outcome message carries.',
    spec_fields=( Field(...), ... ),
    body=_body,
    engine=lambda spec: _ENGINE,
    scored=True,                      # False only for a pure sandbox
)
```

## The runtime API available inside `build(root, spec)`

Everything below is already in scope. Do not re-implement any of it.

| name | what it does |
|---|---|
| `SPEC` | the spec object (same as `spec`) |
| `W`, `H` | stage viewBox size, `860` × `460` |
| `el(tag, attrs, parent)` | create an HTML element |
| `svg(tag, attrs, parent)` | create an SVG element |
| `clear(node)` | remove all children |
| `clamp(v, lo, hi)` | |
| `fmt(v, places)` | fixed-decimal string, `places` defaults to 2 |
| `scale(domain, range)` | linear map; returns `fn(v)` and `fn.invert(px)` |
| `rand(seed)` | deterministic PRNG → `fn()` in `[0,1)` |
| `shuffle(list, seed)` | deterministic shuffle (copy) |
| `colour(name)` | palette name → hex. Names: `a b c d e ink dim faint grid edge card good bad` |
| `COLOURS` | the same map, if you need it directly |
| `UI.say(text)` | replace the instruction line |
| `UI.chip(key, label, tone)` | add/return a readout chip → `{set(text)}` |
| `UI.feedback(text, ok)` | the status bar. `ok` = `true` green, `false` red, omitted neutral |
| `UI.score(correct, text, detail)` | feedback **and** report the outcome upward |
| `BRIDGE.readout(obj)` | live state → the workbench. Never stored |
| `BRIDGE.outcome(obj)` | a committed, checkable result → recorded as evidence |
| `drag(node, {start, move, end})` | pointer drag. Handlers get `{x, y}` in viewBox units. Return `false` from `start` to refuse the drag |
| `point(event, node)` | raw event → `{x, y}` in viewBox units |

`build()` is called once, after the DOM is ready. Everything else is yours.

## Hard constraints — a violation fails the build

The rendered page is checked by `app.harness.sims_store.validate_html`. It must be:

- **Self-contained.** No `<script src>`, no `<link href>`, no `<img src>` pointing at a
  host, no `@import` of a URL, no `fetch('http…')`, no `XMLHttpRequest`, no
  `WebSocket`, no meta refresh, no form posting to a host. **No network at all.**
- **Free of dynamic code.** No `eval(`, no `Function(`, no `setTimeout('string')`.
- **Well-formed.** Every tag you open, close. The check is lenient but not blind.
- **Under 400,000 bytes.**
- **Carries `data-series`.** The runtime puts it on the stage, so you get this free —
  but if you build your own interactive groups, tag them `data-series="<name>"`.
- **Deterministic.** Any randomness must come from `rand(seed)` / `shuffle(list, seed)`
  with a seed derived from the spec, so the same spec always renders the same game.

Do not use `localStorage`, `sessionStorage`, `cookies`, `alert`, `prompt`, or `confirm`.
The page runs in a sandboxed view; they will throw or be ignored.

## What makes a game *good* here — the quality bar

This is a learning tool with an evidence-based design. A pretty animation that
proves nothing is a failure.

1. **The learner must commit to something checkable.** Dragging is exploration;
   pressing Check is commitment. Only the commitment produces an outcome. Never
   post `BRIDGE.outcome` on a mere interaction.
2. **`BRIDGE.readout` on live change, `BRIDGE.outcome` exactly once per committed
   task.** A readout is the simulation talking to the screen. An outcome is the
   learner having committed. Do not collapse the two.
3. **Feedback must teach.** On a wrong answer, say what to reconsider — not just
   "incorrect". On a right answer, say *why* it is right.
4. **Give up gracefully.** After 3 tries on one task, reveal the answer and post
   `correct: false` with `gave_up: true` in the detail. Never let a learner grind.
5. **Real subject content.** The physics must be right, the algebra must check out,
   the economics must be defensible. Use the correct terminology for the subject.
6. **Deterministic variation.** Use `rand(spec.seed)` to vary numbers between games
   of the same archetype, so replaying is not memorising — but the same spec must
   always render identically.
7. **Accessible.** Give the SVG `role="img"` and a real `aria-label`. Label every
   input. Keyboard-reachable buttons (use `<button>`, not a clickable `<div>`).
8. **Legible at 860 × 460.** Plot box roughly `x 78→812`, `y 44→388`, with the
   control strip below. Font sizes: ticks 10.5, labels 12, headings via the runtime.

## The game spec JSON

`playground_games_<group>.json` is a JSON array. Each entry:

```json
{
  "slug": "econ-shifting-markets",
  "archetype": "curve_shift",
  "title": "Shifting Markets — Supply & Demand",
  "course_id": "ap_microeconomics",
  "concept": "Supply and demand equilibrium",
  "subjects": ["economics"],
  "difficulty": "core",
  "minutes": 6,
  "prompt": "Read the shock, then shift the right curve.",
  "learning_objective": "Predict the direction of price and quantity after a curve shifts.",
  "reference": "Shifting Markets, reviewecon.com",
  "spec": { "...your archetype's own schema..." }
}
```

`slug` must be globally unique and prefixed with the subject (`econ-`, `math-`,
`sci-`, `cs-`, `gen-`). `difficulty` is one of `intro` `core` `stretch`.
`course_id` should be a real course id from `app/curriculum_packs/*.json`
(e.g. `ap_microeconomics`, `ap_macroeconomics`, `algebra_2`, `physics`, `ap_biology`,
`ap_chemistry`, `computer_science`, `earth_space_science`, `biology`, `chemistry`,
`ap_calculus`, `algebra_one_year`). The `spec` object must satisfy your own schema.

## How to verify your work — do this before you report back

Write a throwaway script (put it in `outputs/.packaging/`, not in the repo tree)
that, for **every** spec in your JSON:

```python
import sys, json
sys.path.insert(0, '/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness/backend')
from app.harness import playground, sims_store

# import your module directly so you do not depend on __init__ being wired yet
from app.harness.playground import archetypes_core  # noqa
import importlib
mod = importlib.import_module('app.harness.playground.archetypes_<group>')
for a in mod.<YOUR_TUPLE_OR_LIST>:
    playground.register(a)          # will raise if the declaration is malformed

games = json.load(open('.../playground_games_<group>.json'))
for g in games:
    arch = playground.get(g['archetype'])
    problems = playground.validate_spec(g['spec'], arch)
    assert not problems, (g['slug'], problems)
    page = playground.render(arch, g['spec'])
    problems = sims_store.validate_html(page, kind='simulation')
    assert not problems, (g['slug'], problems)
    print('OK', g['slug'], len(page), 'bytes')
```

Run it with `harness/ui-tests/.venv/bin/python`. **Every game must print OK.**
If `register` raises, your declaration is malformed — fix it, do not work around it.

Also check the engine JS parses. The fastest way is `node --check` on the extracted
script, or simply confirm there are no unbalanced braces and no stray `</script>`.

## Report back

A short report: each archetype id, what the mechanic is, each game slug, the byte
size of each rendered page, and anything you could not make work. Be honest about
gaps — an archetype you stubbed is far worse than one you say you did not finish.
Do **not** claim a game works if your probe did not print OK for it.

## Your assignment

<!-- filled in per builder -->
