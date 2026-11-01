# Merged Implementation Plan — Luminfest Learning Harness (fan1–fan4 synthesis)

Synthesizer merge of UNIT-1 (app browser), UNIT-2 (teacher monitor), UNIT-3 (tool parity), UNIT-4 (game/video sources). All four units retained; overlapping edits to `toolbox.py` / `policy.py` / `config.py` deduplicated into one sequence below.

## Conflict resolutions (explicit)

1. **fan-3 Playwright vs fan-1 WKWebView browser — COMPLEMENTARY, keep both, sequenced.** Server-side Playwright (`app/harness/browser.py`) serves the tutor's *tool loop* (works headless, cross-platform, chromium already cached, teacher-only). App-side WKWebView (`Browser.swift` page) serves the *teacher/student browsing surface* in the desktop app. Ship Playwright first (P1-A); the native browser (P2) reuses the same role-scoped policy model so governance stays unified.
2. **`HARNESS_BROWSER_ENABLED` name collision.** fan-1 and fan-3 both claim it. Resolve: `HARNESS_BROWSER_ENABLED` = Playwright tool gate (ships first, `config.py`); `HARNESS_APP_BROWSER_ENABLED` = native browser backend endpoints (fan-1 §12). Both default **off**, fail-close.
3. **`browser_snapshot` name collision** (fan-3 tool vs fan-1 endpoint `/browser/snapshot`): distinct surfaces, keep both names; document in code comments.
4. **fan-2 monitor hooks `MediaTools.swift` delegate**: hook from new monitor code only; `EmbeddedLessonWebView`/`MediaEmbed` invariant ("lesson surface never becomes a general web view") stays untouched — fan-1 agrees (§5: no MediaTools change).
5. **YouTube search**: fan-3 says don't build `youtube_search`; fan-4 says build teacher-only `search_videos` with operator-approved landing. Resolved: build fan-4's version as **teacher-only, candidates-not-content** — every result must pass `video.verify()` and land in `media/video_allowlist.json` via teacher "attach to concept" before students ever see it. This satisfies fan-3's quota/curation rationale (fan-3 P2 item 4 merges into this).

## Fail-close invariants (MUST NOT break)

- **Every new external source registered in `app/ingest/policy.py`** (`MEDIA_SOURCES` at `policy.py:787`) — unknown `policy_name` ⇒ card withheld by `reapply_media_policy` (`policy.py:840-889`).
- Role read server-side only (`_principal_role`, `creation_gate.py:22-29`): unknown/missing role ⇒ student; `create`/`restructure` teacher-only.
- `assert_extraction_allowed` (`video.py:107-119`) stays unconditional — no caption/transcript/audio-to-model, ever.
- All new network features default off (`media_enabled` precedent, `config.py:97-100`); refusals are named, never fabricated.
- `monitor_observations` added to `USER_SCOPED_TABLES` (`user_scope.py:67-89`) on day one.
- Monitor provider failure ⇒ `{"state": "SILENT"}` — never fail loud into a student session.
- Redirect targets re-trigger the domain-rights gate at fetch time (classify the fetched domain, not the search result's).

## P0 — unlock existing value + fail-close prerequisites (~2.5–3.5 dev-days)

**P0.1 · requirements fix (trivial).** `backend/requirements.txt`: add `duckduckgo-search==8.1.1` (currently absent — `web_search` silently refuses without it; verified by fan-4 grep) and pin `playwright==1.62.0` (already installed locally, needed for P1-A reproducibility).

**P0.2 · Wikipedia policy entry + text fetch (fan-3 T3/T1).**
- `backend/app/ingest/policy.py`: `WIKIPEDIA_REST = SourcePolicy(name='Wikipedia (REST API)', licence_class=LicenceClass.CC_BY_SA, ...)`; append to ordered `registry()` list. `backend/evidence.json`: `wikipedia_rest_cc_by_sa` record.
- `backend/app/harness/tools_creation.py`: `def fetch_page_text(ctx, url: str, max_chars: int = 4000) -> ToolResult` (gated on `_WEB_DOMAIN_RIGHTS` + `policy.INGESTIBLE`; unlisted domain → `link_only` refusal); `def wikipedia_summary(ctx, title: str, lang: str = 'en') -> ToolResult` (REST summary API, honest descriptive UA, re-probe before shipping).
- `backend/app/harness/toolbox.py`: `_register(ToolSpec('fetch_page_text', …, 'ingestible', …), …)` and same for `wikipedia_summary`.
- **Gate**: `media_enabled` off ⇒ refuse; policy entry missing ⇒ withheld (test asserts refusal *before* entry lands).
- Tests: `backend/tests/test_fetch_page_text.py`, `test_wikipedia_policy.py` (refusal-first, redirect re-gating, size/content-type checks, never caches text).
- Effort: 1–1.5 days.

**P0.3 · Curated math-game pack + `find_game` (fan-4).**
- `backend/app/ingest/policy.py`: audited entries `DESMOS_CLASSROOM`, `NRICH`, `TRANSUM`, `MATH_IS_FUN` (all `link_only`); `MATHIGON_POLYPAD` + optional `GEOGEBRA` as `link_only` **pending embed/licence audit** (user decision, see Blockers). All appended to `MEDIA_SOURCES`.
- `backend/app/harness/game_search.py` (new): pack loader mirroring `simulation_map.py`; `backend/app/media_packs/games.json` (slug, title, url, licence, policy_name, topics) seeded from fan-4's live-verified hosts (mathigon 200, desmos 200, nrich 200, transum 200, mathsisfun 200).
- `backend/app/harness/toolbox.py`: `find_game(ctx, query)` — teacher-only via `_principal_role`; returns deep-link cards (`integration_mode: 'deep_link'`, `policy_name` stamped); excludes Prodigy/Brilliant (account walls).
- Tests: `test_game_search.py` — unknown policy_name withheld, student call refused, named-gap honesty.
- Effort: 1–1.5 days.

## P1 — video search, Playwright tool, monitor loop (~7–10 dev-days)

**P1-A · `browser_snapshot` + `simulate_screenshot` (fan-3 T2/T4).** New `backend/app/harness/browser.py`: `def snapshot(url: str, *, settings, out_dir: Path, allow_hosts: Sequence[str], timeout: float = 20.0) -> dict`, `def render_artifact(artifact_id: str, *, settings) -> dict` (playwright sync API, route()-block non-allow-listed hosts, no cookies persisted). `tools_creation.py`: `browser_snapshot(ctx, url, full_page=False)`, `simulate_screenshot(ctx, artifact_id)` — **teacher-only**. `config.py`: `browser_enabled: bool = False` (env `HARNESS_BROWSER_ENABLED`). Posture `embed_only`/`sandboxed`; screenshots TTL'd, never fed to the model as source text. Docker: `playwright install --with-deps chromium`. Tests: `test_browser_snapshot.py` (mock playwright). Effort: 1.5–2 days.

**P1-B · `search_videos` (fan-4, merged with fan-3 P2).** New `backend/app/harness/video_search.py`: Data API `search.list` when `settings.youtube_api_key` set (**verified present at `config.py`** — `youtube_api_key: str = ''`, `HARNESS_YOUTUBE_API_KEY` already read in `from_env`; no key in `.env` today ⇒ ships dormant, DDG fallback active), DDG `site:youtube.com` fallback; every candidate through `video.verify()`; quota metering via `search_quota()`. `toolbox.py`: `search_videos(ctx, query, limit)` teacher-only; teacher "attach to concept" persists via `video.save_allowlist` into `media/video_allowlist.json`. Tests: `test_video_search.py` (keyless fallback, unverified ⇒ plain link). Effort: 1.5–2 days.

**P1-C · Monitor backend (fan-2, text-fallback path ships now).** New `backend/app/monitor.py`; `main.py`: `POST /api/v1/monitor/observation` (rate_limit 60/300s, `monitor_consent` + teacher window verified server-side, 403 fail-close), `GET /api/v1/monitor/feed?since=` (`require_role(user, {'teacher','staff','admin'})` helper modeled on `require_admin`, `main.py:2249`), `GET /api/v1/monitor/observations/{id}/image` (read-time consent + expiry + cohort checks, every view audited). `db.py`: `MonitorObservation` (user_id, teacher_id, source, url/title/text ≤500 chars, image path+sha256, note ≤240, expires_at) — register in `user_scope.py` **same commit**. `config.py`: `HARNESS_MONITOR_*` set (provider defaults `off` ⇒ text-only via tutor provider + `learner_block`). Provider failure ⇒ SILENT. `provider.py`: separate vision entry point allowing content-part messages; tutor path byte-identical. Retention 72h (cap 168h), purge deletes files on revoke. Tests: consent fail-close, user-scope guard, SILENT-on-failure. Effort: 3–4 days. **Vision path gated on user decision (Blocker 1).**

**P1-D · Monitor client (fan-2).** `Core.swift`: `monitor_consent` in `updateSettings` (`Core.swift:672-680` pattern), consent-gated before any capture (`Core.swift:534/751` pattern); `SnapshotSource` protocol (`webview` via existing `decidePolicyFor`/`didFinish` hook + idle timer, `workbook` via `ImageRenderer`, `text` always). Cadence: nav-event ≥30s throttle, 120s timer, ≤60/hour; ≤1280px JPEG q0.55, pixel-hash dedupe, in-memory only. `Studio.swift`: SUGGEST renders as tertiary `notice` banner (`Studio.swift:468-469` pattern), auto-fade ~10s, never modal; no capture during exams/`questionPaused`. Effort: 1.5–2 days.

## P2 — native browser page + ergonomics (~6–9 dev-days)

**P2-A · App-side WKWebView browser (fan-1 full design).** New `native/Sources/LearningHarness/Browser.swift` (`BrowserView`, `BrowserModel`, `BrowserWebView: NSViewRepresentable`, `enum BrowserPolicy.allows(_:role:rules:) -> BrowserDecision`), `Resources/BrowserHome.html`; modify `Core.swift` (`case browser`, `loadBrowserPolicy/loadBrowserPins/sendBrowserSnapshot`), `LuminfestApp.swift:319-328`, `NativeQA.swift` hooks. Backend: `backend/app/browser.py` (`register(app, factory, settings)`; policy/pins/snapshot endpoints), `schemas.py` (`BrowserSnapshot`, `BrowserPin`, `BrowserPolicyOut`), `config.py`: `browser_enabled`→`app_browser_enabled` (env `HARNESS_APP_BROWSER_ENABLED`), `browser_student_allowlist`. Rules: teacher = operator `browser_policy.json` (https-only, no file:, no credentials-in-URL); student = default-deny + pinned links + seeded allowlist (MediaEmbed hosts + phet/khan/nasa); students: no URL entry, no JS extraction, EMBED_ONLY extraction refused; exam mode ⇒ deny-all. Server re-validates snapshot URLs (patched-client can't bypass). Consent-gated like `/events`. Tests: `backend/tests/test_browser.py` (unknown-role fail-close, size caps, learner deny-by-default). Do **not** touch `MediaTools.swift`. App Sandbox network-client entitlement confirmed at next packaging. Effort: 4.5–6.5 days.

**P2-B · Curation ergonomics.** Teacher panel for allowlist management (`video.revoke()`/`verify_all()` workflow); optional teacher-only DDG candidate-proposal endpoint requiring operator approval. Effort: 1–1.5 days.

**P2-C · Deferred/optional.** SSE monitor stream (reuse `/agent/stream` shape, `main.py:2240`); PDF export for decks; Ollama local vision (`images` field). Not proposed: `youtube_search` student tool, yt-dlp, scraping, video/music generation, searxng self-host.

## Blockers requiring user decisions

1. **Vision provider key (fan-2)**: configured endpoint is DeepSeek (text-only; `.env` has only `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`; `HARNESS_TUTOR_PROVIDER` unset ⇒ tutor runs offline by default). Decide: enable Qwen-VL DashScope (recommended primary) / GLM-4V free tier / OpenAI gpt-4o-mini, or stay text-fallback. Until decided, P1-C ships text-only — monitoring still works, no images.
2. **YouTube API key**: plumbing **verified present** (`config.py` field `youtube_api_key`, env `HARNESS_YOUTUBE_API_KEY` already read); no key in `.env`. Decide: supply key (Data API primary, ~100 searches/day) or accept DDG-fallback-only quality.
3. **Embed-host widening** (Mathigon Polypad / GeoGebra → `MediaEmbed.hosts` + `embed_only` policy): requires live licence/terms audit — blocks only the embed change, not deep-link cards.
4. **App Sandbox/ATS entitlements** for the packaged app (fan-1 risk) — confirm before P2-A ships.
