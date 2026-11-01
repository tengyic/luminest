# Luminfest Workbench (`harness/web/`)

The interactive web surface for the Luminfest learning harness: a learner previews a
simulation, hovers to select parts of it, and asks the AI to explain — while
students are bounded to filing categorized change requests instead of issuing
code instructions.

Self-contained static app: **vanilla JS/CSS, no build step**. The backend can
serve it as-is.

```
harness/web/
├── index.html               the workbench page
├── styles.css               layout (sidebar | main | details) + responsive rules
├── app.js                   all client logic
├── sims/
│   └── supply-demand.html   seed simulation (draggable demand curve)
└── README.md
```

## Integration (one line in `main.py`)

`backend/app/web_routes.py` is a self-contained `APIRouter` that serves the
static workbench **and** the `/api/v1/sims/*` endpoints. It reads
`request.app.state.settings` / `app.state.factory` at request time, so it
needs no arguments:

```python
from . import web_routes

def create_app(settings=None):
    ...
    app.include_router(web_routes.router)   # guarded include
```

Route map added by the router:

| Route | Purpose |
|---|---|
| `GET /` | workbench page (`index.html`) |
| `GET /web/{path}` | static assets (css/js/sim html), allow-listed MIME types |
| `GET /api/v1/sims` | list artifacts (store manifest, newest first) `{sims:[{id,kind,title,latest_version,updated_at,meta,requests}]}` |
| `POST /api/v1/sims` | validate + store a new artifact, or add a version to `{id,title,html}` (teacher flow) |
| `GET /api/v1/sims/{id}` | the store manifest entry (+ `requests` count, `version` alias) |
| `GET /api/v1/sims/{id}/raw` | latest version of the sim HTML (same-origin, for the sandboxed iframe) |
| `GET /api/v1/sims/{id}/raw?version=n` | that specific historical version |
| `POST /api/v1/sims/{id}/requests` | file a change request (see boundary below) |

**Single storage path.** `web_routes.py` holds no storage logic of its own:
every read and write goes through `app/harness/sims_store.py` — the same store
(``<data_dir>/sims/<artifact_id>/v{n}.html`` + ``index.json`` manifest) the
sim-creation tools write through, so a tool-created artifact is immediately
served here, with full version history (`?version=n`) and revertibility. The
bundled seed (`sims/supply-demand.html`) is copied into the store through
`create_artifact` on first list (idempotent via a manifest meta marker), so it
is validated like everything else. `POST /api/v1/sims` runs
`sims_store.validate_html` and refuses with the validator's problem list —
nothing that loads an outside resource, fetches, or uses `eval`/`new Function`
is ever stored, on any path.

**Auth:** no new scheme. The alpha UI pastes an existing session access token
once (sidebar), keeps it in `sessionStorage`, and sends `Authorization: Bearer`.
Anonymous access to the sim endpoints is allowed in `development` only;
`production` requires a valid token, exactly like the rest of the API.

## The hover-to-select interaction

The sim runs in `<iframe sandbox="allow-scripts">` — **no `allow-same-origin`,
ever**. That combination (allow-scripts + allow-same-origin) lets sim script
reach up into the workbench document and steal the sessionStorage access token
(the escape orch-verify-2 demonstrated); with `allow-scripts` alone the iframe
runs on an opaque origin and neither side can touch the other.

Because the parent can no longer inspect the sim's DOM, selection is delivered
by a bridge: the server injects `web/luminfest-agent.js` into every served sim at
serve time (`inject_agent_script`, idempotent, store bytes stay canonical).
The bridge observes hover/click inside the sim and postMessages selection
payloads to the workbench:

    {type:'luminfest:ready'}                      bridge is up
    {type:'luminfest:hover',  selector, rect}     cursor over an element
    {type:'luminfest:select', selection}          learner clicked an element

The parent (`app.js`) validates every message — it must come from the sim
frame's own `contentWindow` and carry a known `luminfest:` type — then routes it to
the same highlight/popover/explain handlers as before. `postMessage(..., '*')`
is acceptable here because the payload is only geometry and text of what the
learner pointed at, the parent validates the source frame, and the sim is
served from our own store through the validated creation path. From the
popover:

- **Explain this** → sends a chat turn to `POST /api/v1/agent/stream` with the
  selection payload in `context` and the message text
  `Explain this <kind> ("<text>") in the current simulation.`
- **Request change…** → focuses the student composer with the selection
  attached; the learner picks a category and files the request.

If no bridge announces `luminfest:ready` within two seconds of the frame loading
(e.g. the sim was loaded without the API), the workbench says so explicitly on
the canvas instead of pretending selection works.

## Selection payload schema

Sent as `selection` in both the chat request body and the change-request body:

```json
{
  "kind": "line" | "graph" | "asset" | "element",
  "selector": "[data-series=\"demand\"]",
  "text": "demand",
  "rect": { "x": 60, "y": 30, "w": 600, "h": 330 }
}
```

- `kind=graph` when the element has a `[data-series]` ancestor (curve/series).
- `kind=line` for bare SVG line/path/polyline, `asset` for images,
  `element` otherwise.
- `selector` priority: `[data-series="…"]` → `#id` → a `body tag:nth-of-type(n) > …`
  path (max depth 6).
- `rect` is the element's client rect inside the iframe viewport (px, rounded).

## `data-series` convention (for sim authors and the sim-generating AI)

Every plottable series in a simulation must be wrapped in a group tagged with
a stable `data-series` attribute:

```html
<g data-series="demand">   ...curve + hit area + label...   </g>
<g data-series="supply">   ...                              </g>
<g data-series="equilibrium"> ...point + dashed guides...    </g>
```

Rules: one `data-series` per visual series; the value is a lowercase identifier
(`demand`, `supply`, `equilibrium`); include the label text inside the group so
hover-selection can name it. The workbench resolves any hover/click on children
to the nearest `[data-series]` ancestor, which makes series-level explain and
change requests stable across re-renders. The seed sim
(`sims/supply-demand.html`) follows the convention and is the reference
implementation: drag the blue demand curve to shift it, and the equilibrium
point, dashed guides and readouts update.

## Chat / agent streaming contract

`POST /api/v1/agent/stream` (SSE) events handled by `app.js`:
`turn_start`, `message_delta {text}`, `tool_call {id,name,arguments}`,
`tool_result {id,name,ok,summary,data}`, `turn_end {reason}`, `error {message}`,
plus `reasoning_delta {text}` — rendered **only** when Developer mode is on
(hidden behind the `dev` chip in the details panel, default off). The request
body carries `{message, role, sim_id, selection, history, developer_mode}`.
Cancel is an in-flight `AbortController` on the stream fetch.

Tool calls render as collapsible cards (name + arguments + result). Status
pill: `idle | running | error`; the Cancel button appears only while running.
Chat history is persisted per session in `localStorage` and restored on load —
navigation never blanks the transcript.

## Student / Teacher boundary (hard requirement)

- Role toggle in the sidebar (persisted per tab).
- **Student composer**: exactly four category buttons — `bug`, `wrong_info`,
  `ugly`, `ux` — plus a note field. There is no free-form send. `create` /
  `restructure` are not offered, and any attempt to force them through the
  client is rejected with a one-line explanation: *"Creating or restructuring
  simulations belongs to your teacher."*
- **Teacher composer**: free-form; can create/modify sims.
- **Server-side role.** The acting role comes from the authenticated account
  (`users.role`), never from the request payload — a client-declared
  `role: "teacher"` is ignored (recorded only as a declaration in the audit
  trail). Fail closed: only the canonical `'teacher'` account role grants the
  teacher path; every other value decides as a student.
- **One decision table.** The allow/refuse decision is made by
  `creation_gate.evaluate` — the same gate the creation tools answer to — with
  the category sets imported from `creation_gate`, not redefined here. A
  student's `create`/`restructure` attempt is refused with the reason naming
  the four categories they can file instead; unknown categories and empty
  notes are refused with their reasons too.
- The UI enforces the same boundary (four category buttons only, boundary
  explanation line), but the server is the enforcement point.

## What is and is not wired yet

Wired and verified against the real backend (`create_app`, fresh data dir):
static serving, sim list/metadata/raw, change requests (with server-side
category enforcement), bearer-token auth via the sidebar (sessionStorage), and
`POST /api/v1/agent/stream` — the SSE wire format was probed live (`event:` +
full-event JSON `data:`), the reasoning channel (`message_delta` with
`channel:'reasoning'`) is handled, and `turn_end.content` is consumed as the
final text. The request body matches `AgentTurnInput`:
`{session_id, message, developer_mode, context:{selection, sim_id, role}}` —
history is deliberately not replayed; the harness memory tools own that.

Remaining assumption: a live provider turn (DeepSeek) was not exercised from
this client to save the team's tokens; the offline-provider path
(`error` + `turn_end reason=unavailable`) renders correctly in the transcript.
Sim-version bump detection polls metadata once after `turn_end` rather than
listening to a push event.

## Verify by trying to falsify

1. **Blank state** — open `/`, pick no sim, reload, switch sessions back and
   forth: the transcript and canvas must never blank or lose history.
2. **Hover/select** — hover the demand curve in the seed sim: a green highlight
   must appear over the curve only; click → popover → "Explain this" must emit
   a chat request whose body contains the full selection payload
   (`[data-series="demand"]`).
3. **Student boundary** — as Student, try to send with no category (blocked
   with hint), then file a `bug` request (succeeds), then `curl` the same
   endpoint with `"category":"create","role":"student"` → must be `403`.
4. **Streaming/cancel** — start a teacher turn and hit Cancel mid-stream:
   stream aborts, status returns to `idle`, partial text is kept.
5. **Version refresh** — POST a new version of the active sim (via
   `POST /api/v1/sims`), then finish any turn: canvas must reload to the new
   version without a manual page reload.
