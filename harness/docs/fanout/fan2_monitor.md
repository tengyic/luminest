# UNIT-2 — Teacher-monitoring loop: periodic snapshots → vision analysis → silent guidance

Worker: fan-2. Read-only unit: no code was modified; the only artifact is this report.

## Findings (file:line evidence)

**Provider layer has NO vision support today.**

- `backend/app/harness/provider.py:63` — `chat(settings, messages: Sequence[dict[str, str]], ...)` is typed as string-content messages and posts them verbatim to `{url}/chat/completions` (`provider.py:91-93`). Nothing in the module constructs OpenAI multimodal content parts (`[{"type": "text"}, {"type": "image_url", "image_url": {...}}]`); no `detail`, no base64 data-URL helper, no image settings exist anywhere in the module. The Ollama branch (`provider.py:79-89`) likewise passes messages straight through with no `images` field, so even a local vision model is unreachable through current code.
- The messages list *is* forwarded as raw JSON, so the OpenAI-compatible wire could carry content parts with a small extension — but no caller builds them and the configured model cannot accept them (below).
- `backend/app/config.py:151-162` — provider settings are a single tuple: `HARNESS_TUTOR_PROVIDER ∈ {offline, ollama, openai}`, `HARNESS_TUTOR_URL`, `HARNESS_TUTOR_MODEL`, `HARNESS_TUTOR_KEY`, `HARNESS_TUTOR_TIMEOUT_SECONDS` (12 s default, 300 s cap, `config.py:165-171`). One provider for the whole app; there is no separate vision/monitor slot.
- `backend/.env` (inspected, values redacted): contains exactly two keys — `DEEPSEEK_API_KEY=<redacted>` and `DEEPSEEK_BASE_URL=<redacted>`. `config.py:52-55` aliases these onto `HARNESS_TUTOR_KEY` / `HARNESS_TUTOR_URL` when unset. Note: `HARNESS_TUTOR_PROVIDER` is **not** set in `.env`, so with today's defaults the tutor runs `offline` (`config.py:151`) — an operator must set it explicitly, by design (`config.py:22-23`).

**Empirical conclusion on the critical question:** the configured endpoint is DeepSeek's OpenAI-compatible API. DeepSeek's public API serves only text models (`deepseek-chat`, `deepseek-reasoner`) — there is no vision model or image-input endpoint on that base URL today. Combined with the audit above: **no vision path exists in this deployment**, and the monitoring loop must degrade to text-only analysis by default. (Confidence: high for the code side — read directly; high for the provider side — DeepSeek has served text-only models since launch and nothing in the repo suggests otherwise, but this is a claim about a third party's current catalogue, so the design treats "vision-capable" as a runtime capability probe, not an assumption.)

**Consent pattern to reuse.**

- `native/Sources/LearningHarness/Core.swift:751` — active-seconds accrual is gated on `user["telemetry_consent"].bool` (plus foreground and not-paused); `Core.swift:534` gates telemetry POSTs the same way; `Core.swift:672-680` (`updateSettings`) is the settings-write pattern (PATCH `/me`-style body, epoch guard, busy/error handling). The monitoring loop should gate on a `monitor_consent` flag exactly like this: no consent → the snapshot timer never fires, client-side, before any capture happens.

**UI patterns for non-blocking guidance.**

- `native/Sources/LearningHarness/Studio.swift:468-469` — existing inline `notice` text row (`Text(media["notice"].string)...foregroundStyle(Palette.tertiary)`) is the template for a quiet, non-modal suggestion banner. Core.swift already carries an app-level `notice` string; a student suggestion should ride the same channel, auto-dismissing, never a modal or an interruption of an in-flight question (`questionPaused`, Core.swift:751).

**Auth / role / audit patterns to match.**

- `backend/app/main.py:529-548` — `authenticated` dependency yields `(db, user)`; every route uses `auth=Depends(authenticated)`.
- `main.py:2249-2251` — `require_admin(user)` checks `user.role ∈ {'admin','staff'}`; a `require_role(user, {'teacher'})` helper is the natural sibling. `user.role` defaults to `'learner'` (`main.py:62`).
- `backend/app/user_scope.py:67-89` — `USER_SCOPED_TABLES` frozenset; the SQLAlchemy read-guard structurally blocks any SELECT on a listed table without a `user_id` predicate or an audited `unscoped()` hatch (`user_scope.py:111-129`). Any new per-student table **must** be added here.
- `backend/app/db.py:625-626` — `AdminAuditLog` (`admin_audit_log`) with actor/target indexes (`db.py:693-695`) is the audit-log surface for privileged views.
- `backend/app/security.py:168` — `rate_limit(factory, key, maximum, period)` for endpoint-level limiting.
- `main.py:2219-2245` — `/agent/stream` SSE shape: synchronous events replayed as `event:`/`data:` pairs via `StreamingResponse(media_type='text/event-stream')` with `Cache-Control: no-store`; disconnect surfaced through `request.scope['luminfest_disconnect']`.

**Existing WKWebView surface (for the snapshotter, no dependency required).**

- `native/Sources/LearningHarness/MediaTools.swift:139-150` — an `NSViewRepresentable` hosting `WKWebView`; `MediaTools.swift:157` shows a `decidePolicyFor` navigation delegate already exists, which is where navigation-event triggers would hook. The design below keeps the browser unit independent: the monitor takes a protocol `SnapshotSource` that a WKWebView wrapper, a SwiftUI `ImageRenderer` of sim workbooks, or nothing (text-only) can satisfy.

## Vision provider recommendation

Current state: **no vision-capable provider is configured, and the provider module cannot send images.** Recommendation: add a *second, independent* provider slot for the monitor so the tutor stays on deepseek-chat while vision is a strictly opt-in operator decision (mirroring the `media_enabled` philosophy at `config.py:97-100` — outbound calls carrying learner data should be a decision, and an image of a student's screen is more sensitive than a media search).

New env vars (names only, no values): `HARNESS_MONITOR_PROVIDER` (`off|openai`), `HARNESS_MONITOR_URL`, `HARNESS_MONITOR_MODEL`, `HARNESS_MONITOR_KEY`, plus `HARNESS_MONITOR_ENABLED` (master switch) and `HARNESS_MONITOR_TIMEOUT_SECONDS`. When `HARNESS_MONITOR_PROVIDER` is unset/`off`, the monitor runs in text-fallback mode using the existing tutor settings — deepseek-chat with URL+title+extracted text. This is the default and the required degradation path.

Concrete OpenAI-compatible vision options (all speak `chat/completions` with `image_url` content parts, so one small extension to `provider.py` — allowing content-part messages — serves all three):

| Option | Endpoint base (env: `HARNESS_MONITOR_URL`) | Model (`HARNESS_MONITOR_MODEL`) | Notes |
|---|---|---|---|
| Alibaba DashScope (Qwen-VL) | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-vl-plus` (budget) or `qwen-vl-max` | Cheap, strong OCR on Chinese + English workbook content; fits an operator already using DeepSeek CN endpoints. **Recommended primary.** |
| Zhipu GLM-4V | `https://open.bigmodel.cn/api/paas/v4` | `glm-4v-flash` (free tier) or `glm-4v-plus` | Free-tier option makes a good **fallback** and a zero-cost pilot. |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | Best general vision quality; most expensive; data leaves to a US provider — flag in privacy review. |
| Local (Ollama) | existing ollama URL | `qwen2.5vl` / `llava` | Fully private, but requires adding the Ollama `images` field path to `provider.py`; list as a later enhancement, not v1. |

**Primary:** Qwen-VL (`qwen-vl-plus`). **Fallback chain:** `glm-4v-flash` → text-only (URL + title + DOM/page text extract through `learner_block`, `provider.py:234-237`, on deepseek-chat). Vision capability is verified at call time: if the provider returns 4xx on an image-bearing request, the monitor marks the provider non-vision for the process lifetime and drops to text — never retries images, never fails the session.

## Loop design

**Who snapshots:** the app, never the backend. Sources behind one `SnapshotSource` protocol:

1. `webview` — `WKWebView.takeSnapshot(configuration:)` triggered by (a) navigation events — hook the existing `decidePolicyFor`/`didFinish` delegate path (`MediaTools.swift:157`) — and (b) a periodic idle timer.
2. `workbook` — SwiftUI sim/practice views rendered with `ImageRenderer` (student sim workbooks need no WKWebView).
3. `text` — always available: current URL, page title, and a text extract (≤ 4 000 chars, wrapped in `learner_block`) harvested from the same source, with zero image cost.

**Cadence:** navigation-event snapshots throttle to ≥ 1 per 30 s; periodic timer every 120 s while a session is active. Everything is additionally gated on the same conditions as `activeSeconds` (`Core.swift:751`): authenticated, app foregrounded, student consented, teacher has an active monitoring window, question not paused (no snapshots during assessments — extension of the existing exam-blocking posture, cf. `block_exam_help`, `main.py:2234`). Budget cap: ≤ 60 snapshot uploads per student per hour, enforced client-side first, server-side via `rate_limit`.

**Image budget:** downscale to ≤ 1280 px long edge, JPEG quality 0.55, target ≤ 150 KB per frame (base64 ≈ 200 KB on the wire). Skip-identical: cheap pixel-hash diff against the previous frame; a static screen re-sends nothing. Snapshots exist in memory only until POSTed; nothing is cached client-side.

**Consent model (two-key, and both must be true):**

- *Student consent:* a dedicated `monitor_consent` flag on the user profile, surfaced in settings via the `updateSettings` pattern (`Core.swift:672-680`), with plain language about what a snapshot is, where it goes, and for how long it is kept. Gated client-side before capture (the `Core.swift:534/751` pattern) *and* server-side on POST.
- *Teacher opt-in:* the teacher enables monitoring per student/cohort and for a time window; observations are produced only while the window is open.
- Silence semantics: either key false → no capture at all (not "capture without guidance"). Analysis result `SILENT` → no event, no UI, nothing persisted beyond a counter. A suggestion is **never** delivered as an interruption: no modal, no focus steal, no audio.

## Endpoints

All under the existing `API` prefix (`/api/v1`), all `auth=Depends(authenticated)` (`main.py:529`).

**`POST /api/v1/monitor/observation`** — app → backend. Role: authenticated learner (any role may submit *only for themselves*; `db, user = auth` and the row is stamped `user_id=user.id`, satisfying the user-scope guard). Body:

```
{ "session_id": str, "source": "webview"|"workbook"|"text",
  "url": str?, "title": str?, "text_excerpt": str?,   // text path
  "image_b64": str? }                                  // vision path, ≤ 300 KB decoded
```

Server behavior: rate-limit (`security.py:168`, e.g. 60 per 300 s per user); verify `monitor_consent` + teacher window → 403 fail-close otherwise; route to `app/monitor.py` (new) which calls the vision provider or the text fallback; parse strict JSON reply `{"state": "SILENT"|"SUGGEST", "note": "≤ 240 chars", "reason": ...}` via the `chat_json` discipline (`provider.py:214-231`); on `SILENT` return `{"state": "SILENT"}` and persist only a counter; on `SUGGEST` insert a `monitor_observations` row (user_id, teacher_id, source, url/title excerpt, image path or null, note, created_at, expires_at) and return `{"state": "SUGGEST", "note": ...}` synchronously. Provider failure/timeout → `{"state": "SILENT"}` (fail silent, never fail loud into the student's session), consistent with the never-raise provider contract (`provider.py:65`).

**`GET /api/v1/monitor/feed?since=`** — teacher dashboard polling (v1; simplest and matches the app's non-streaming `ApiClient` style). Role: `require_role(user, {'teacher','staff','admin'})` — a new helper modeled on `require_admin` (`main.py:2249-2251`); returns only observations whose `teacher_id` is the caller (or their cohort), notes and metadata only, images excluded by default. Poll every 15–30 s. An SSE variant `GET /api/v1/monitor/stream` can reuse the `/agent/stream` shape (`main.py:2240-2245`) later if polling proves too chatty.

**`GET /api/v1/monitor/observations/{id}/image`** — teacher-only, **fail-close**: 403 unless (a) caller role is teacher/staff/admin, (b) the observation belongs to their cohort, (c) the student's `monitor_consent` is *still* true at read time, and (d) `now < expires_at`. Each image view writes an `AdminAuditLog` row (`db.py:625`) with actor, target, and reason.

**Student UI:** the synchronous `SUGGEST` response renders a non-dismiss-blocking banner in Studio using the `notice` pattern (`Studio.swift:468-469`) — small, tertiary-colored text, auto-fades after ~10 s, tap to expand. No badge count, no red styling, nothing that reads as an alarm.

## Privacy

- **Storage:** image bytes on disk under `HARNESS_DATA_DIR/monitor/{yyyy-mm}/{uuid}.jpg` (inside the data directory so existing export/delete flows cover it, mirroring the `media_cache_dir` reasoning at `config.py:104-106`); the DB row stores only the relative path + sha256. Text excerpts live in the row itself, truncated to 500 chars.
- **Retention:** default 72 h, env-tunable `HARNESS_MONITOR_RETENTION_HOURS` (hard cap 168 h = 7 days). `expires_at` stamped at insert; a periodic purge deletes expired rows and files. Snapshots are never inputs to training exports; the training-consent ledger (`db.py:84`) semantics are explicitly out of scope for snapshots.
- **Who can view:** images — teacher of record only, fail-close on any doubt (consent revoked, expired, wrong cohort ⇒ 403), every view audited. Students can see and delete their own observations via the standard per-user data export/delete flows (their table is user-scoped, so those flows must include it).
- **User-scope guard:** `monitor_observations` must be added to `USER_SCOPED_TABLES` (`user_scope.py:67-89`) on day one, so any unscoped cross-student SELECT raises `UnsafeQueryError` in dev and prod alike; the teacher feed's cohort query takes the audited `unscoped()` hatch explicitly (`user_scope.py:111-118`) or, better, filters by `teacher_id` so no hatch is needed.
- **Third-party exposure:** images are sent to the configured vision provider only when `HARNESS_MONITOR_*` is explicitly set (operator decision, `media_enabled` precedent, `config.py:97-100`); text fallback keeps analysis within the already-chosen tutor provider. The privacy policy / Terms copy must name screen snapshots, retention, and the recipient provider before the feature ships.

## Change list

None — read-only unit. Files *touched*: none. Files *read* for evidence: `backend/.env` (names only), `backend/app/config.py`, `backend/app/harness/provider.py`, `backend/app/main.py`, `backend/app/user_scope.py`, `backend/app/db.py`, `backend/app/security.py`, `native/Sources/LearningHarness/Core.swift`, `Studio.swift`, `MediaTools.swift`. Only file created: this report (`docs/fanout/fan2_monitor.md`).

## Risks

1. **Vision provider claim is third-party-dependent.** DeepSeek is text-only today; Qwen/GLM vision endpoints could change pricing/availability. Mitigation: capability probe + text fallback is the always-working path; vision is an enhancement, matching the provider module's own philosophy (`provider.py:1-11`).
2. **`provider.py` needs a content-part extension** (its signature says `dict[str, str]`). Small change but touches the most safety-reviewed module; keep the tutor path byte-identical and add a separate vision entry point.
3. **Current `.env` would run the whole tutor offline** (no `HARNESS_TUTOR_PROVIDER` set, `config.py:151`). The monitor inherits whatever the operator configured; the design must not silently assume a live provider.
4. **Consent races:** a teacher viewing an image seconds after the student revokes consent is prevented by the read-time consent check, but the retention purge and revocation should also delete outstanding images immediately, not just expire them.
5. **False-positive nudges** from a vision model could feel like surveillance. Mitigation: ≤ 240-char neutral wording, low suggestion rate (cap per session), SILENT by default, teacher sees observations not verdicts.
6. **Snapshot scope:** a full-window capture may include other apps' content if the wrong capture API is used — restrict to `WKWebView.takeSnapshot` / `ImageRenderer` of in-app views only, never `CGWindowList` screen capture.
7. **Latency/cost:** vision calls on every navigation could be costly; the throttle, dedupe, and 60/hour cap bound worst case to ~7 MB/hour/student.
