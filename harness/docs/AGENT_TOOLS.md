# Agent tools — registry, dispatch and the declarative interaction boundary

Grounded in `backend/app/harness/toolbox.py`, `backend/app/harness/agent_loop.py`,
`backend/app/declarative_ui.py`, `backend/app/interactive_runtime.py` and the interactive
routes in `backend/app/main.py`.

## 1. Tool registry and posture model

Every tool is declared once as a `ToolSpec` and registered via `_register`
(`toolbox.py:203-236`). The declaration carries `name`, `summary`, `arguments`, `posture`,
`returns`, optional `requires` (for tools on an optional package) and an advisory
`timeout_seconds`. A tool whose optional dependency is unavailable reports `available:
False` in the catalogue rather than being listed and failing after a turn.

Postures are ordered from most to least trusted (`toolbox.py:39-52`):

| Posture | Meaning |
| --- | --- |
| `internal` | Reads this project's own graph and curriculum. |
| `personal` | Reads one learner's own records. |
| `ingestible` | May read outside text because a licence clears it. |
| `embed_only` | May hand back a provider-hosted player or a licence-cleared media file; never holds a copy the licence does not clear. |
| `link_only` | May name an outside source but never return its text. |
| `sandboxed` | Executes learner-supplied code inside a restricted workspace. |

The posture is published to the model as part of the tool's signature
(`name(args) -> returns [posture]`) so the contract the model reads is the contract the
registry enforces.

## 2. Machine-checkable JSON Schemas

`ToolSpec.argument_schema` is compiled from the same human-readable signature string that
is printed to the model (`toolbox.py:159-190`, `:227-231`). A top-level splitter keeps
bracketed/notated arguments such as `[{heading, bullets, notes}]` as one argument, so the
prompt and the validator cannot drift apart. Unknown annotations are admitted as
unconstrained values rather than guessed at. Required arguments are those without a
default; `additionalProperties: False` is set. `return_json_schema` is deliberately loose:
field names from the `returns` description are checkable, values are not (`:193-200`).
`to_dict()` publishes both schemas alongside the posture, timeout, requirements and
availability (`:233-239`).

## 3. Strict dispatcher validation

`invoke` is the single gate every tool call passes through (`toolbox.py:1962-2013`):

1. **Unknown name** → a refusal (`Unknown tool …`), never a silent no-op.
2. **Surface boundary** — if a live lesson is on surface `X` and the tool belongs to
   surface `Y`, the call is refused with the active surface, the owning surface and the
   decision tool. The refusal tells the model to call `stage_surface` with a reason and
   retry. This is checked here, in one place, rather than duplicated in each tool.
3. **Identifier grounding** — `_ground_identifiers` replaces placeholder or invented ids
   (e.g. a schema example `board_id_example` or `lesson_1`) with real ids from the live
   lesson context. When a substitution happens, the tool result carries a `notes` line
   naming what the server actually used, so the model's original tool_call and the server's
   action are both visible in the trace.
4. **Argument validation** — unknown arguments are refused (`Arguments must match the
   published tool schema`), and each supplied value is checked against its published
   schema property with `_schema_accepts`; a type mismatch is refused by name. A
   `TypeError` from the callable is also caught and returned as a refusal.
5. The advisory `timeout_seconds` is reported, **not enforced**: the generic dispatcher
   cannot safely interrupt a blocking Python call (`:217-219`).

Refusals are structured `ToolResult`s with `ok=False`, a `refused` explanation and an
`error`/`notes` field; `agent_loop` feeds the refusal back to the model with the decision
it needs to recover (the surface-boundary refusal is the explicit example in `invoke`'s
docstring). A refusal is a decision boundary, not an unhandled failure.

## 4. Closed declarative UI vocabulary

`backend/app/declarative_ui.py` is deliberately *not* a general UI language. Its registry
(`:71-91`) is the approved vocabulary a model may emit for a native, stateful interaction:

- Components: `text`, `slider`, `number`, `choice`, `readout`, `feedback`, `reset` — each
  with a fixed set of allowed and required fields (`:51-68`).
- Expressions: numbers, `{"const": ...}`, `{"ref": input_id}` and `{"op": ..., "args":
  [...]}` with a fixed operator enum (`add/sub/mul/div/min/max/abs`, comparisons,
  `and/or/not`) and declared arity bounds (`:40-49`).
- Limits: at most 40 components, 16 inputs, 8 options, depth 8, string length 400
  (`:30-35`). Ids must match a short identifier regex; duplicates are refused.
- **`validate`** turns an untrusted spec into a normalized one or a named `ValueError`
  reason (`:155-258`). There is no `eval`, no import, no DOM, no network and no file
  access; references are ids and operators are an enum, so the tree is checked before
  anything renders it.
- **`evaluate`** recomputes inputs, readouts, feedback, reset state and an `evidence` block
  from learner state (`:322-361`). The evidence explicitly says it is **"not an Attempt,
  not a receipt-bound answer, and not a grade."** Feedback is authored guidance, not a
  certified grade (`:88-90`, `:256-257`).
- Deliberately absent: arbitrary drawing, file access, third-party embeds, model-supplied
  scripts, and persisting interaction evidence as an `Attempt` (`:19-21`).

The HTTP surface for this vocabulary is `GET /interactive/registry`,
`GET /interactive/example`, `POST /interactive/validate`, `POST /interactive/evaluate`,
`POST /interactive/evidence` and `GET /interactive/artifacts/{id}` — see `docs/API.md`.

## 5. The `emit_interactive` path

`emit_interactive` is the generative-interaction boundary tool
(`toolbox.py:739-764`, registered at `:1424-1434`):

- It requires a bound database session and authenticated learner; otherwise it refuses
  ("Interactive artifacts require an authenticated learner").
- It calls `interactive_runtime.persist_artifact(ctx.db, ctx.user, spec,
  concept_id=..., source='model')`, which validates the spec with the *same* closed
  validator the renderer uses. A `ValueError`/`TypeError` becomes a refusal with the named
  reason ("The declarative UI vocabulary is closed").
- On success it returns an `artifact_id` plus the validated spec, `schema_version`,
  `source`, `concept_id`, `title` and `created_at`. The artifact is stored under the
  authenticated learner **before** the client renders it; the returned id is the handle the
  tutor turn carries and the client uses to write bounded interaction evidence.
- The result notes say the client renders the stored spec inline in this turn and that
  interaction frames are evidence, not Attempts or grades.

The related `validate_interactive` tool checks a spec without persisting it
(`toolbox.py:721-735`). The system prompt (`main.py:3869`) tells the model to use the
closed-vocabulary path, and the agent loop publishes a human-readable activity label for
`emit_interactive` ("Building an interaction you can use", `agent_loop.py:103`).

## 6. Refusal behaviour summary

| Situation | Behaviour |
| --- | --- |
| Tool not in registry | `ToolResult(ok=False, refused='Unknown tool …')`; fed back to the model. |
| Wrong surface for the live lesson | Refusal naming active/owner surfaces + `stage_surface` decision tool. |
| Invented/placeholder identifier | Server-bound to the real live id; substitution recorded in result notes. |
| Unknown or mistyped argument | Refusal naming the bad argument; schema is authoritative. |
| Spec outside declarative vocabulary | Named `ValueError` → `422` on the API, or a structured tool refusal. |
| No authenticated learner for `emit_interactive` | Structured refusal; nothing persisted. |
| No configured model / transient failure | Declared `notice` with reason + next action, or graceful fallback — never fabricated content rendered as authored, never a stack trace/status code on screen. |

## 7. Not claimed

- The closed vocabulary is not a general UI toolkit; refusal is the intended behaviour.
- A generated interaction is not a grade, a certified assessment, or an `Attempt`.
- Tool availability reflects declared optional dependencies, not a guarantee about the
  quality or safety of an external provider's output.
