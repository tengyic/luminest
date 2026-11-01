# fan-3 — Tool-parity audit: what the Luminfest harness tutor is missing vs "WorkBuddy-class" capabilities

Scope: `harness/backend/app/harness/toolbox.py` registry (verified **26 tools** at runtime via
`toolbox.REGISTRY`), the ingest licence gate (`app/ingest/policy.py`), the creation gate
(`app/harness/creation_gate.py`), media/video plumbing, and the runtime venv
(`/Users/tengyi/.workbuddy/binaries/python/envs/default/bin/python`, Python 3.13.12).
Read-only audit; no code was modified. All network probes were single lightweight requests.

---

## Inventory

The 26 registered tools (name → purpose, posture in brackets). Verified live, not from docs:

| # | Tool | Purpose (from spec/code) | Posture |
|---|------|--------------------------|---------|
| 1 | `search_concepts` | Term search over the course knowledge graph | internal |
| 2 | `read_concept` | One concept: classification, prerequisites, dependants, authored lesson | internal |
| 3 | `inspect_prerequisites` | Which prerequisites are measurably weak, with evidence strength | personal |
| 4 | `recall_learner_memory` | Durable learner notes with time decay | personal |
| 5 | `read_learner_evidence` | Recent scored attempts + error categories | personal |
| 6 | `search_material` | Search internal + audited external sources; non-cleared → link only | ingestible |
| 7 | `fetch_material_text` | Outside text only when licence clears it; otherwise first-class refusal | link_only |
| 8 | `prepare_case_study` | Case study with tasks + rubric from authored curriculum | internal |
| 9 | `build_figure` | Interactive figure (symbolic engine for maths, concept map otherwise) | internal |
| 10 | `check_understanding` | One authored retrieval item (MCQ) for a concept | internal |
| 11 | `compose_content` | Multimodal artifact: explanation, flashcards, quiz, deck, figure… | internal |
| 12 | `find_image` | Licence-cleared internet photo (Openverse/Wikimedia via media.py) | ingestible |
| 13 | `find_video` | Curated video, per-video oEmbed/Data-API embeddability verification | embed_only |
| 14 | `find_simulation` | PhET/Gizmos simulation card or named gap; unobservable by construction | embed_only |
| 15 | `build_presentation` | Narrated deck: slides + script + WebVTT + self-contained HTML | internal |
| 16 | `run_in_workspace` | Execute code in the restricted learner workspace | sandboxed |
| 17 | `list_workspace` | List learner workspace files | sandboxed |
| 18 | `write_workspace_file` | Persist artifact into learner workspace | sandboxed |
| 19 | `read_workspace_file` | Read learner workspace file | sandboxed |
| 20 | `write_simulation` | Teacher-gated creation of self-contained HTML simulation (creation_gate → provider → validate → version) | sandboxed |
| 21 | `edit_simulation` | Scoped change request (bug/wrong_info/ugly/ux student; create/restructure teacher-only); revertible versions | sandboxed |
| 22 | `generate_slides` | Deterministic printable HTML deck + .pptx twin (python-pptx) | internal |
| 23 | `text_to_speech` | Cached mp3 via a local VoiceStudio backend; honest refusal when disabled/not running | internal |
| 24 | `image_search` | Open image APIs through media.py, embed_only, nothing downloaded | embed_only |
| 25 | `web_search` | Open-web search via duckduckgo-search; every hit through the licence gate; non-cleared domains come back link_only | ingestible |
| 26 | `image_generate` | Keyless pollinations.ai provider chain; reports serving provider | internal |

Architecture notes that constrain every addition:
- Spec shape: `ToolSpec(name, summary, arguments, posture, returns)` registered via
  `_register(spec, fn)`; handlers are `fn(ctx: ToolContext, **args) -> ToolResult`.
  `POSTURES = internal / personal / ingestible / embed_only / link_only / sandboxed`.
- Role for gating is read **server-side from `ctx.user.role`** (`_principal_role` in
  tools_creation.py) — never from a tool argument; unauthenticated resolves to student (fail-close).
- `creation_gate.evaluate({role, category, note, selection}, approvals)` approves students'
  bug/wrong_info/ugly/ux requests as scoped requirements; `create`/`restructure` are teacher-only.
- Network media is gated by `settings.media_enabled` (`HARNESS_MEDIA_ENABLED`); every outbound
  tool refuses honestly (a named `refused` reason, never a fabricated result) when off.

---

## Gap analysis vs WorkBuddy-class capabilities

### (a) Web search (text) — **already exists; one real gap in retrieval depth**
`web_search` (tools_creation.py:521) is real: duckduckgo-search 8.1.1 is installed and pinned in
requirements.txt. Results are gated through `_WEB_DOMAIN_RIGHTS` (wikipedia/wikimedia/nasa/met/
gutenberg cleared; openstax link_only; khanacademy prohibited; **everything unlisted → link_only**).

The gap: **there is no tool that fetches and returns page text from a cleared URL.**
`fetch_material_text` only names *declared policy sources* and even returns `'text': ''`
(ingestion is an operator step). So the loop can search, see a Wikipedia/NASA/Gutenberg hit is
ingestible, and still cannot read one sentence of it. Correct class-material search therefore
stalls at titles. Fix: a `fetch_page_text` tool gated on the same domain-rights table
(§ Proposed tools, T1).

### (b) Browser automation (playwright) — **missing, and feasible today**
No browser tool exists. Feasibility verified in the runtime venv:
- `playwright` **1.62.0 is already installed** (not yet pinned in requirements.txt).
- Chromium binaries are **already cached** in `~/Library/Caches/ms-playwright`
  (chromium-1228/1234/1248 + headless shells + ffmpeg) — **no `playwright install` download needed**.
- Live probe: `p.chromium.launch(headless=True)` → `new_page()` → `set_content` →
  `screenshot()` returned **5,720 bytes, exit clean**. Headless rendering works on this machine.
- What is genuinely missing: a policy posture for "render an external page" (screenshots are
  copies of rendered pixels, though ephemeral — see § Browser automation tradeoff), a K12-safe
  navigation allowlist, and a `HARNESS_BROWSER_ENABLED`-style gate alongside `media_enabled`.

### (c) Richer asset generation — **mostly covered; two honest non-gaps**
- Image **search**: `find_image` (cache-capable, licence-gated per asset) + `image_search`
  (embed_only) — covered.
- Image **generation**: `image_generate` via keyless pollinations.ai with an honest provider
  chain — covered; a key-carrying production provider is deliberately an operator decision.
- **Audio**: `text_to_speech` via a local VoiceStudio backend (self-hosted, loopback) —
  covered for narration, and it keeps the learner's text on the host. Full music/voice-clone
  generation does **not** fit a K12 harness (rights, voice-likeness
  consent, content risk); recommend *not* adding it.
- **Video generation**: does not fit. GenAI video carries model-content provenance issues,
  non-determinism in teaching material, and cost with no key available. The harness's existing
  philosophy (deterministic, licence-audited, honest-degradation) argues against it. Skip.
- **Deck/document**: `generate_slides` (HTML + pptx) and `build_presentation` (narrated, VTT)
  — covered. PDF export is the only plausible increment and is low priority.
- **Interactive**: `write_simulation`/`edit_simulation` with server-side validation and
  versioning — covered, and arguably ahead of a generic WorkBuddy.

### (d) YouTube integration — **audited; intentionally curated, not searched** (`harness/video.py`)
`video.py` is a model of the house style and is **not missing WorkBuddy features so much as
deliberately refusing two**:
- Playback: allowlist-curation → per-video oEmbed probe (`<iframe>` presence) or Data API
  `status.embeddable` when a key exists → youtube-nocookie embed → `VERIFY_TTL_SECONDS` (14 d)
  re-verification → operator revocation file → NC/commercial withholding. Fail-close throughout:
  unverifiable ⇒ downgraded to `link_only`, never embedded.
- **Search is deliberately not a tool**: `DATA_API_SEARCH_COST = 100` units vs 10,000/day —
  a search-per-question over the 524-concept catalogue exhausts a day's quota in ~100 queries
  (`search_quota()` documents this). Curation is an operator data file
  (`media/video_allowlist.json`), seeded with oEmbed-verified 3Blue1Brown entries for
  `integrated_math_1`.
- Extraction is structurally impossible: `assert_extraction_allowed()` unconditionally raises —
  no captions/transcripts/audio-to-model, ever.
- Audit verdict: **keep as-is.** A `youtube_search` tool would contradict the module's own
  documented rationale. If ever wanted: teacher-only, quota-metered, results become *allowlist
  candidates* requiring an operator to approve — not learner-reachable content.

---

## Proposed tools table

| # | Name | Spec (args → returns) | Implementing module | New policy.py entry needed | Audience | Fail-close behavior |
|---|------|----------------------|---------------------|---------------------------|----------|---------------------|
| T1 | `fetch_page_text` | `url: str, max_chars: int = 4000` → `{url, title, text?, licence_class, mode}` or refusal | **new** `fetch` logic inside `app/harness/tools_creation.py` (or small `app/harness/webfetch.py`) reusing `_domain_rights` + `policy.INGESTIBLE` | No new *source*; extend `_WEB_DOMAIN_RIGHTS` only via audit. Wikipedia should gain a formal `WIKIPEDIA_REST` SourcePolicy (CC BY-SA) so `fetch_material_text` can also name it | Teacher + student (posture `ingestible`) | Refuses when `media_enabled` off; unlisted/unclear domain → `link_only` (url+title, no body) with named refusal; robots-uncertain hosts skipped; response size & content-type checked; never caches text |
| T2 | `browser_snapshot` | `url: str, full_page: bool = false` → `{screenshot_path, title, text_excerpt, status}` or refusal | **new** `app/harness/browser.py` (playwright sync API, single shared launch, per-call page, 20 s nav timeout) | No ingestion (screenshot is ephemeral render, posture `embed_only`/`sandboxed`); **add `HARNESS_BROWSER_ENABLED` setting** + domain allowlist reusing `_WEB_DOMAIN_RIGHTS` + a K12 blocklist hook | **Teacher-only** (`_principal_role(ctx) == 'teacher'` via creation_gate-style check) | Refuses when browser disabled, `media_enabled` off, domain not allow-listed, or launch fails; reports provider absence honestly (playwright import guarded); screenshots cached under media dir with TTL, never shown as ingestible text |
| T3 | `wikipedia_summary` (thin variant of T1) | `title: str, lang: str = 'en'` → `{title, extract, url, licence}` or refusal | `tools_creation.py`, hitting `https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}` | **Yes: `WIKIPEDIA_REST` SourcePolicy** — `licence_class=CC_BY_SA`, `INGESTIBLE`, attribution "Wikipedia contributors, CC BY-SA 4.0", evidence_id recorded. Add to the audited ordered list in `registry()` | Teacher + student (`ingestible`) | `assert_ingestible`-style gate; network error → honest error ToolResult; extract truncated; section-level fetching stays out of scope (leads to quote-farming) |
| T4 | `simulate_screenshot` (validation nicety, optional) | `artifact_id: str` → `{thumbnail_path, console_errors: []}` | `app/harness/browser.py`, renders `sims_store.raw_url(artifact_id)` locally | None (localhost render) | Teacher-only | Fails closed on render errors; console errors reported into `write_simulation` notes, never silently dropped |

**Explicitly not proposed:** `youtube_search` (contradicts video.py's documented quota/curation
rationale — if ever added: teacher-only + operator-approval of candidates); video generation
and music generation (rights/content-risk fit is poor for K12; audio narration already covered
by `text_to_speech`); `searxng` self-host (no instance available; DDG suffices, see below).

---

## Browser automation tradeoff

| Dimension | A: Playwright (backend, headless) | B: Reuse the app's WKWebView via new backend endpoints |
|---|---|---|
| Where it runs | Server-side in FastAPI; works for any client (web, desktop, headless CI) | Requires the desktop app to act as a rendering service; backend↔app IPC bridge to design and keep alive |
| Platform | Cross-platform, already proven on this machine (chromium cached, launch verified) | macOS-only (WKWebView); dead on Linux/Docker deploys (`backend/Dockerfile`) |
| Install cost | **Zero here**: playwright 1.62.0 installed, chromium binaries cached. Only add to requirements.txt for reproducibility | Zero install, but large new native surface (Swift handlers, URL scheme/auth for local endpoints) |
| Determinism/control | Full: viewport, waits, JS-disable, per-navigation timeouts, block non-allowlisted hosts at route level | Matches learner's real browser, but harder to sandbox/restrict; user profile cookies leak into renders |
| Safety gating | Route-level URL allowlist + `HARNESS_BROWSER_ENABLED` + teacher-only, all server-side and testable | Gating split between server policy and native app; harder to audit |
| Fit for the loop | Tool returns bytes/path the model can cite; works unattended | Tool would need the app to be running; agentic loop on server cannot rely on that |
| Verdict | **Recommended** | Only attractive for interactive learner-facing preview, which already exists in the client |

---

## Search provider probe result

`.env` (values redacted) contains exactly two keys: `DEEPSEEK_API_KEY=<set>`,
`DEEPSEEK_BASE_URL=<set>`. No Google/Bing/Serper/YouTube keys — so the recommendation must be
keyless.

| Provider | Probe | Result |
|---|---|---|
| DuckDuckGo HTML endpoint (`html.duckduckgo.com/html/?q=…`) | 1 GET, 10 s timeout, custom UA | **200 OK, 33,459 bytes, 10 result anchors in 1.7 s** — reachable and parseable |
| Wikipedia Action API (`en.wikipedia.org/w/api.php?action=query&list=search`) | 1 GET | **Failed** (HTTP response was not JSON — likely bot-blocking of the bare probe UA/endpoint). Do not build on this path untested; prefer the **REST summary API** (`/api/rest_v1/page/summary/`) which is the documented, bot-policy-friendly surface, and re-probe before wiring |
| duckduckgo-search library (`DDGS().text`) | Not re-probed live; it is already the pinned `web_search` backend (duckduckgo-search 8.1.1 in requirements.txt) | Already in production use by tool 25 |

**Recommendation:** keep duckduckgo-search as the general web-search backend (keyless, already
integrated, gate-compatible), and use the DDG HTML endpoint only as a fallback fetch target.
For class-material *text*, rely on T3/T1 against Wikipedia REST + the already-cleared domains
(nasa.gov, gutenberg.org, metmuseum.org, wikimedia). A self-hosted searxng would be the
rate-limit-proof upgrade but requires infrastructure this instance does not have; note it as an
operator option, not a code default.

---

## Change list (priority order; exact files + signatures)

1. **P0 — `fetch_page_text` (T1)** — unlocks the value of the existing `web_search`.
   - `backend/app/harness/tools_creation.py`: add
     `def fetch_page_text(ctx, url: str, max_chars: int = 4000) -> ToolResult`
     (+ extend `_WEB_DOMAIN_RIGHTS` only with audited entries).
   - `backend/app/harness/toolbox.py`: `_register(ToolSpec('fetch_page_text', …, 'ingestible', …), _tools_creation.fetch_page_text)`.
2. **P0 — Wikipedia policy entry (T3 prerequisite)** — the fail-close gate means a new external
   source **must** be added or the tool withholds:
   - `backend/app/ingest/policy.py`: add `WIKIPEDIA_REST = SourcePolicy(name='Wikipedia (REST API)', …, licence_class=LicenceClass.CC_BY_SA, evidence_id=…)` and include it in the ordered list inside `registry()` (and `search_material`'s external loop via the same tuple used at `toolbox.py:370`).
   - `backend/evidence.json`: add the evidence record for `wikipedia_rest_cc_by_sa`.
   - `backend/app/harness/tools_creation.py`: `def wikipedia_summary(ctx, title: str, lang: str = 'en') -> ToolResult`.
   - `backend/app/harness/toolbox.py`: register.
3. **P1 — `browser_snapshot` (T2) + `simulate_screenshot` (T4)** — teacher-only vibe-coding QA.
   - **new** `backend/app/harness/browser.py`:
     `def snapshot(url: str, *, settings, out_dir: Path, allow_hosts: Sequence[str], timeout: float = 20.0) -> dict` and
     `def render_artifact(artifact_id: str, *, settings) -> dict`.
   - `backend/app/harness/tools_creation.py`: `def browser_snapshot(ctx, url: str, full_page: bool = False) -> ToolResult` (teacher check via `_principal_role`), `def simulate_screenshot(ctx, artifact_id: str) -> ToolResult`.
   - Settings module: add `browser_enabled` (env `HARNESS_BROWSER_ENABLED`, default **off** — fail-close) and a teacher-only route allowlist setting.
   - `backend/app/harness/toolbox.py`: register both.
   - `backend/requirements.txt`: pin `playwright==1.62.0`.
4. **P2 — operator ergonomics for YouTube curation** (no new tool): document
   `media/video_allowlist.json` + `video.revoke()` + `verify_all()` as the teacher workflow;
   optionally a teacher-only FastAPI endpoint that *proposes* candidates via DDG and requires
   operator approval before they enter the allowlist — explicitly not a `youtube_search` tool.
5. **P2 — tests**: `backend/tests/test_fetch_page_text.py`, `test_browser_snapshot.py`
   (mock playwright), `test_wikipedia_policy.py` (assert refusal before policy entry exists).

---

## Risks

1. **Fail-close drift.** Every proposed tool touches `app/ingest/policy.py`; forgetting the
   entry means the tool is silently withheld (by design). Conversely, T1 must classify the
   *fetched page's* domain, not the search result's, at fetch time — a redirect to an uncleared
   host must re-trigger the gate.
2. **DDG HTML scraping fragility.** The HTML endpoint is unofficial and can rate-limit or change
   markup; duckduckgo-search already abstracts this, so prefer the library and keep the raw
   endpoint as fallback only. The failed Wikipedia Action-API probe shows keyless endpoints can
   block bare UAs — set an honest descriptive UA and re-probe before shipping T3.
3. **Playwright supply chain.** Chromium auto-updates via `playwright install`; pin the version
   in requirements.txt and, in Docker, run `playwright install --with-deps chromium` at build
   time. Headless browsing of allow-listed external pages can still execute third-party JS:
   mitigate with `route()` blocking of non-allow-listed hosts, JS where possible, no cookies
   persisted, teacher-only access.
4. **Screenshot = copy?** A rendered screenshot is ephemeral and not redistributed, but a cautious
   auditor may class it as a derivative display. Keep posture `embed_only`/`sandboxed`, TTL the
   cache, never feed screenshots to the model as source text, and record the domain + timestamp
   in the ToolResult notes.
5. **Student exposure.** `web_search` results are already student-visible link_only; T1 raises
   the ceiling by returning real text for cleared domains only. If the operator prefers, gate
   T1 behind the same `media_enabled` flag (recommended default) so an offline classroom
   instance refuses identically to `image_search`.
6. **Scope honesty.** This audit verified the venv on this machine (playwright + chromium
   cached); a fresh install or the Docker image does **not** currently include playwright —
   items 1–2 work without it, item 3 requires the requirements.txt + build change above.
