# UNIT-1 Design Report: In-App Browser for Luminfest Learning Harness

Worker: fan-1 · Scope: native WKWebView browsing surface + snapshot pipeline + safety posture.
Read-only constraint honored: the only file written is this report.

## Findings (with file:line evidence)

### App shell and page structure
- `native/Package.swift:1-16` — Swift tools **6.0**, `swiftLanguageModes: [.v5]`, platform **macOS .v14**, executable target `LearningHarness`, `resources: [.process("Resources")]`. So: Swift 5-mode concurrency, no iOS-only APIs (`mediaType`/`limitsNavigationsToAppBoundDomains`), macOS 14 WKWebView API only. There is no App Sandbox / network entitlement file under `native/` (no `Info.plist`/entitlements in the target), so App Transport Security and sandboxing follow the executable defaults — note as a risk below.
- Page switching is enum-driven, not NavigationStack-based: `Core.swift:130-145` (`enum Page: String, CaseIterable` — today, studio, map, review, teacher, projects, insights, settings) and `Core.swift:398-418` (`AppStore.navigate(_:)` → `loadPage()` switch). The shell renders it in `LuminfestApp.swift:319-328` (`switch store.page { case .studio: StudioView() ... case .teacher: TeacherPage() ... }`) inside `AppShell` (`LuminfestApp.swift:286-334`); the sidebar builds items from `Page.allCases` (`LuminfestApp.swift:354-358`). Adding a page means one enum case + one switch branch + sidebar automatic inclusion. There is **no explicit "teacher/student" page split** in the app: all authenticated users see all pages; role is server-side (`main.py:2100` `acting_role = str(getattr(user, 'role', '') or 'learner')`; `creation_gate.py:22-29` fail-close "unknown role is a student").
- Studio's existing web surface: `MediaTools.swift:137-167` — `EmbeddedLessonWebView: NSViewRepresentable` wrapping `WKWebView`, with a `WKNavigationDelegate` coordinator that **cancels any navigation off the `MediaEmbed.hosts` allowlist** (`MediaTools.swift:121-133`: only `youtube-nocookie.com`, `youtube.com`, `phet.colorado.edu`) and forwards it to `NSWorkspace.shared.open`. `MediaTools.swift:300-310` — `InlineSVGView` is a second WKWebView loading local HTML strings. Existing WebKit imports are already in place (`MediaTools.swift:8`).
- Style system to match: `Design.swift` (Palette, Card, Tag, Eyebrow, SectionHeading, LuminfestButtonStyle, RailIconButton — all used in `Studio.swift` e.g. `Studio.swift:96-112, 160-166`), base font 13 (`LuminfestApp.swift:63`), window min 1000×700 (`LuminfestApp.swift:64`), default 1320×860 (`LuminfestApp.swift:33`). Views are dense single-expression style; sheets are used for focused surfaces (`Studio.swift:88-89`).

### Client transport patterns (for the snapshot pipeline)
- `APIClient` (`Core.swift:77-128`) sends **JSON only**: `data(_:method:body:query:)` builds `{endpoint}/api/v1{path}`, sets `Authorization: Bearer` (line 113), `Content-Type: application/json` (line 114). There is **no multipart code anywhere** in the app or backend (grep for `multipart|UploadFile|Form\(|File\(`: only unrelated hits). The only binary transfer in the app is a *download* (`exportAccount`, `Core.swift:704-714`). ⇒ base64-in-JSON is the consistent transport; introducing multipart would be a new pattern for one endpoint.
- Event/telemetry precedent: `AppStore.recordExternalSimulationOpened` (`Core.swift:533-541`) and the heartbeat (`Core.swift:762-767`) POST to `/events` with client event id, ISO8601 timestamp, payload dict, and are **consent-gated** on `user["telemetry_consent"].bool`. A snapshot upload should follow the same shape and gate.

### Backend endpoint patterns
- Every route follows `@app.get/post(API+'/path')` with `auth=Depends(authenticated)` (e.g. `main.py:887-888, 1421-1422, 1607`); `authenticated` (`main.py:529-548`) validates the bearer, rate-limits per token (`rate_limit(factory, 'api:'+digest(raw), 180)`, line 534), yields `(db, user)`, and commits. `user_json` stamps `role` server-side (`main.py:62`).
- Audit precedent: `AdminAuditLog` (`db.py:625-696`, actor_user_id + target_type/target_id + created_at, indexed). Consent precedent: `ConsentLedger` rows written at register (`main.py:602-605`).
- Licence posture is real, not decorative: `ingest/policy.py:65` defines `LicenceClass.EMBED_ONLY`; `EMBEDDABLE = frozenset({LicenceClass.EMBED_ONLY})` (line 84); `harness/video.py:107-119` `assert_extraction_allowed` **always raises** — transcription/caption harvesting/model ingestion of video is refused unconditionally ("not a configuration flag"). `harness/media.py` image pipeline: `filter_candidates` (`media.py:501-544`) returns (accepted, rejected) with annotated reasons, `search`/`acquire` return refusal dicts with reasons when `HARNESS_MEDIA_ENABLED` is off (`media.py:427-431, 633-637`); operator kill switch `settings.media_enabled` defaults off in production (`config.py:100, 189-200`).
- `Settings.from_env` (`config.py:124-207`) is the place for new operator flags; production validation pattern is fail-close on missing config.

### What the browser must NOT become
- `MediaTools.swift:114-119` states the existing design invariant explicitly: a compromised backend "cannot turn the lesson surface into a general web view" — the allowlist is the whole gate. The in-app browser is a deliberate, new, *smaller-trust* surface; the design below must state its own equivalent invariant.

## Design

### 1. Where the browser lives
Add a new `Page.browser` case in `Core.swift:131` and a `BrowserView()` branch in `LuminfestApp.swift:319-328` (sidebar inclusion is automatic via `Page.allCases`, `LuminfestApp.swift:354`). A dedicated page beats a sheet: a browsing session is long-lived, wants window width (min 1000pt), and survives page switches like every other destination. A *sheet* presentation (`Studio.swift` style) is reserved for the **snapshot send** confirmation, not the browser itself.

Home page = sandboxed local page, not a URL bar defaulting to the open web:
- `BrowserView` loads a bundled HTML home (`LearningHarness/Resources/BrowserHome.html`, picked up by the existing `resources: [.process("Resources")]`, `Package.swift:11`) via `loadFileURL(_:allowingReadAccessTo:)`. The home page lists **teacher-pinned or concept-scoped links the backend returned** (see §3) — students start from a curated surface, never a blank address bar.

Chrome (all reusing existing Design components):
- URL field: `FormFieldContainer`-styled `TextField` + `Go` (`LuminfestButtonStyle(primary: false)`), showing current URL read-only while loading.
- Back / Forward / Reload / Home: `RailIconButton` (chevrons) + `HeaderRefreshButton`-style reload (`LuminfestApp.swift:543-564`); disable when `webView.canGoBack/canGoForward` is false. Buttons drive a `BrowserModel` (below), not the NSViewRepresentable directly, keeping the SwiftUI/store pattern.
- Progress: thin `SegmentedProgressBar`-style linear indicator (`Studio.swift:102` precedent) bound to `WKWebView.estimatedProgress` via KVO or `isLoading`.

WebView plumbing — new `BrowserWebView: NSViewRepresentable` (separate from `EmbeddedLessonWebView`, whose invariant is "never navigates anywhere else"; do not weaken it):
- `func makeNSView(context:) -> WKWebView` with a `WKWebViewConfiguration` that sets `websiteDataStore = .nonPersistent()` (no cookies/localStorage survive a session — K12 hygiene, and prevents cross-session sign-in persistence into provider accounts).
- Coordinator: `WKNavigationDelegate` implementing `decidePolicyFor navigationAction` **and** `decidePolicyFor navigationResponse`; the policy consults the role-scoped rules from the store (§3). Same-host-only exception as `EmbeddedLessonWebView` is replaced here by rule evaluation per navigation.
- `@MainActor final class BrowserModel: ObservableObject`: published `urlText`, `canGoBack/Forward`, `isLoading`, `lastDecision`; holds a weak reference to the live `WKWebView` via the coordinator. Matches the `@MainActor` store style (`Core.swift:77, 147`).

JavaScript evaluation (read-only page-text extraction):
- One capability only: `webView.evaluateJavaScript("document.body ? document.body.innerText : ''")` after `decidePolicyFor navigationResponse` allows a top-frame navigation, gated on (a) the session being allowed to browse that host, and (b) **teacher role only** (students never get script evaluation — see §3), and (c) an explicit user action ("Extract page text") so nothing is harvested passively.
- The extracted text is shown in a local disclosure ("Page text extracted by you; nothing was sent") and may be inserted into the tutor draft (`TutorPanel`, `Studio.swift:656`) — it is **never auto-uploaded**. This respects `video.py:107-119`'s extraction-refusal spirit for embeds: a learner manually quoting a page is a learner action; automated harvesting is not built.
- No `WKUserScript` injection, no `WKScriptMessageHandler`, no custom scheme handlers — the surface stays read-only toward the page.

Snapshot capture:
- `webView.takeSnapshot(with: nil) { image, _ in ... }` on macOS 14 (available since macOS 10.13). Convert via `NSBitmapImageRep(cgImage:)` → `representation(using: .png, properties: [:])`. Cap the requested rect to the visible frame (nil rect = full view is fine, but scale to ~1600px wide max to bound size).

### 2. Snapshot pipeline
Transport decision: **base64 in JSON**, not multipart.
- Evidence: the app has zero multipart code (`Core.swift:106-128` is the only HTTP path; JSON-only), and the backend has zero `UploadFile`/`Form` handlers. A JSON body matches `APIClient.data(_:_:body:)` as-is — no new client networking code.
- Client flow: `takeSnapshot` → PNG `Data` → base64 → `store.sendBrowserSnapshot(...)` calling `api.json("/browser/snapshot", method: "POST", body: ["url": ..., "title": ..., "image_base64": ..., "captured_at": ISO8601, "client_event_id": UUID().uuidString, "concept_id": store.selectedConcept])`. Consent-gated like `/events` (`Core.swift:533-541` precedent): if `user["telemetry_consent"]` is false, the endpoint is not called and the button explains why.
- Endpoint: `POST /api/v1/browser/snapshot` (new module `backend/app/browser.py`, mounted from `main.py` inside the existing route-builder function alongside the other `@app.post(API+...)` registrations).
  - Signature: `def browser_snapshot(payload: schemas.BrowserSnapshot, request: Request, auth=Depends(authenticated))` — the exact pattern at `main.py:887-888`.
  - `schemas.BrowserSnapshot` (pydantic): `url: str`, `title: str = ''`, `image_base64: str`, `captured_at: str`, `client_event_id: str`, `concept_id: str = ''`. Validators: url must parse with an https-or-loopback scheme; base64 size cap (decode and reject > ~3 MB); `client_event_id` required (idempotency key, matches the `/events` event-id pattern).
  - Server behavior: re-validate the URL against the same role rules the client used (server is authoritative — fail-close for learners, mirrors `creation_gate.py:22-29`); store the PNG under `settings.data_dir / 'browser' / sha256.png` (content-addressed like `media.py:673`); write a JSONL manifest row alongside (URL, title, user_id, sha256, bytes, captured_at) in the style of `media.py:549-571`; append an `AdminAuditLog` row only when the acting user is a teacher acting on content they pinned (target_type='browser_snapshot'); return `{ok: true, sha256, bytes, stored: true}`. Snapshot bytes stay under `data_dir` so `/export` and account deletion already cover them (same argument as `media.py:222-230`).
  - Rate limit: reuse `rate_limit(factory, ...)` inside the handler for a tighter budget (e.g. 20/60s per user) — snapshots are large.
  - **Not accepted**: the endpoint never stores extracted page text and never forwards snapshots or text to the model provider (video.py refusal posture).

### 3. Safety posture (K12)
Rules live **server-side first, client-enforced second**, mirroring the creation gate philosophy:

- Role model: `role` comes only from the DB via `authenticated` (`main.py:62, 2100`); exact `'teacher'` equality, unknown/missing ⇒ learner (fail-close, `creation_gate.py:22-29`).
- **Teacher**: may navigate any https URL the operator policy permits. Default policy: `browser_policy.json` under `data_dir` (operator-editable data file, `video.py:124-128` allowlist precedent). Default = allow all https, deny http (matching `APIClient.validateEndpoint`'s own http restriction, `Core.swift:101-103`), deny non-https schemes, deny `file:`, deny credentials-in-URL.
- **Student (learner)**: default-deny navigation except (a) hosts on the operator's student allowlist, seeded with the existing embed hosts (`MediaEmbed.hosts`, `MediaTools.swift:121-126`) plus `phet.colorado.edu`, `www.khanacademy.org`, `images.nasa.gov` — all sources already cleared through the licence pipeline — and (b) links a teacher explicitly pinned to the concept. Students get no URL bar entry (address field shows current URL read-only) and no JS extraction.
- Client enforcement: `decidePolicyFor` consults the fetched policy; a denied navigation cancels with a visible Card explaining the rule (never a silent cancel — the codebase's "degradation is visible by construction" doctrine, `Core.swift:543-549`). Server enforcement: `GET /api/v1/browser/policy` returns the role-scoped rules (allowlist, denylist, can_extract_text, can_send_snapshot) signed into the response the client must obey; the snapshot endpoint independently re-validates, so a patched client cannot bypass.
- Licence/embed posture applied to destinations: anything a *teacher* sends students to must be a link the backend has classified. Reuse `filter_candidates`-style reasoning: the pinned-link write path (`POST /api/v1/browser/pins`) runs the URL through the licence/EMBED_ONLY classification used by `ingest/policy.py:65-84` and stores the class; EMBED_ONLY sources are offered to students as **links that open in the sandboxed browser pointed at the rights-holder's own player** (provider serves the bytes — consistent with `video.py:115-119`), and extraction of their content (text/snapshot of embeds) is refused for students. Unclassified ⇒ withheld with a reason shown, never silently allowed (`media.py` "unknown licence is refused, not assumed", doc lines 20-22).
- Exam integrity: browser page is hidden or policy-set to deny-all while `store.question["mode"].string == "exam"` (the app already carries "No answers or tutor help are available inside an exam", `Studio.swift:661`).
- Audit: every denied navigation and every teacher pin writes an audit row (AdminAuditLog pattern, `db.py:625-696`); snapshots are auditable via the manifest, not hidden.

### 4. Effort estimate
| Slice | Estimate |
|---|---|
| BrowserWebView + BrowserModel + BrowserView chrome + home page | 1.5–2 days |
| Policy fetch + navigation gate + role rules (client) | 0.5–1 day |
| Snapshot capture + base64 upload + consent gate (client) | 0.5 day |
| Backend: browser.py module, 3 endpoints (policy, pins, snapshot), schemas, audit, tests | 1.5–2 days |
| NativeQA hooks + ui-test additions + polish | 0.5–1 day |
| **Total** | **~4.5–6.5 dev-days** |

## Change list (files to create/modify; signatures only, no code)

**Native (new):**
1. `native/Sources/LearningHarness/Browser.swift` (new)
   - `struct BrowserView: View` — chrome + `BrowserWebView` + snapshot/send UI + sheet for send confirmation.
   - `@MainActor final class BrowserModel: ObservableObject` — `@Published var urlText/canGoBack/canGoForward/isLoading/lastDecision/policy`; `func go(to:)`, `func reload()`, `func home()`, `func extractPageText()`, `func captureSnapshot()`.
   - `struct BrowserWebView: NSViewRepresentable` — `makeNSView/updateNSView/makeCoordinator`; `final class Coordinator: NSObject, WKNavigationDelegate`.
   - `enum BrowserPolicy { static func allows(_ url: URL, role: String, rules: JSON) -> BrowserDecision }` returning allow/deny-with-reason.
2. `native/Sources/LearningHarness/Resources/BrowserHome.html` (new) — sandboxed home page listing pinned links.

**Native (modify):**
3. `Core.swift` — add `case browser` to `enum Page` (line 131, title/icon/eyebrow/subtitle lines 133-144); add to `AppStore`: `@Published var browserPolicy: JSON = .null`, `@Published var browserPins: [JSON] = []`, `func loadBrowserPolicy() async`, `func loadBrowserPins() async`, `func sendBrowserSnapshot(url:title:png:) async`; branch `.browser` in `loadPage()` switch (line 407); reset browser state in `logout()` (line 726).
4. `LuminfestApp.swift` — add `case .browser: BrowserView()` to the `switch store.page` (line 319-328).
5. `MediaTools.swift` — **no change**; `EmbeddedLessonWebView`/`MediaEmbed` stay untouched (their invariant is load-bearing).
6. `NativeQA.swift` — add QA readback hooks (`browser.url`, `browser.decision`) matching the existing `NATIVE_QA_*` channel (`Core.swift:219`).
7. `native/Package.swift` — no change (Resources already processed).

**Backend (new):**
8. `backend/app/browser.py` — `def register(app, factory, settings)` (same mounting shape as the other feature modules registered from `main.py`); handlers `browser_policy`, `browser_pins`, `browser_snapshot`; helpers `load_policy(settings)`, `classify_destination(url)`, `store_snapshot(db, settings, user, payload)`.
9. `backend/tests/test_browser.py` (new) — policy fail-close for unknown role, snapshot size caps, learner deny-by-default, EMBED_ONLY refusal for student extraction.

**Backend (modify):**
10. `backend/app/schemas.py` — `BrowserSnapshot`, `BrowserPin`, `BrowserPolicyOut` models near the existing `Input`-based models (line ~303 precedent).
11. `backend/app/main.py` — register the browser router inside the existing app-builder (one line next to the other `@app.*` groups, ~line 560+); nothing else.
12. `backend/app/config.py` — `Settings` fields `browser_enabled: bool = False`, `browser_student_allowlist: str = ''` + `from_env` parsing (`HARNESS_BROWSER_ENABLED`, `HARNESS_BROWSER_STUDENT_ALLOWLIST`), production fail-close validation in the style of lines 138-150.

## Risks
- **Invariant tension**: `MediaTools.swift:114-119` promises the lesson surface can never become a general web view. A browser page is exactly that surface, one page over. Mitigation: separate representable, separate policy module, and a doc comment on `Browser.swift` stating the browser's own boundary (role-scoped, server-policy-driven) so the two invariants don't blur.
- **ATS/sandbox**: no entitlements file exists in the native target; WKWebView outbound requests run under the process defaults. Confirm App Sandbox network-client entitlement when the app is next packaged (`scripts/package.py` flow) — first delivery should flag this as open.
- **Patchable client**: any client-side gate is advisory; the design treats `GET /browser/policy` as convenience and makes `/browser/snapshot` and pin writes the enforcing points. Still, a student can *view* whatever the webview loads — the navigation gate is client-only by necessity (server never sees child-frame requests). Documented residual risk for K12: browser is an aid, not a filter appliance; operators should pair it with network-level filtering if that is a requirement.
- **Snapshot privacy**: PNGs may contain anything on screen within the webview (including third-party personal data). Size cap + content-addressed storage + consent gate + data_dir coverage by export/delete are the mitigations; no OCR/model ingestion is built (video.py posture).
- **Scope creep**: URL bar autocomplete, tabs, downloads are all explicitly out of scope; each would re-open the "general web view" problem and add review surface.
