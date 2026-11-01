# fan-4 — Verified sources for teacher game / video search (UNIT-4)

Worker: fan-4 · Date: 2026-10-11 · READ-ONLY run: no existing code was modified; this
document is the only output. Verification budget used: **6 lightweight HTTP checks**
(HEAD-equivalent `curl -o /dev/null -w '%{http_code}' -L --max-time 12`), all reported
below. Repo cross-checked at `/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness`.

## Math game sources table

Liveness column = actual HTTP status returned by my check on 2026-10-11.
Licence/cost statements marked ⚠︎ are from well-established knowledge of the product and
were **not** re-verified live (budget spent); treat them as strong priors, not evidence.

| Source | URL | Live? | Licence / cost | Embeddability | Age fit | Agent-searchable? |
|---|---|---|---|---|---|---|
| Mathigon / Polypad | https://mathigon.org/ (Polypad at mathigon.org/polypad) | **200** | ⚠︎ Proprietary (Amplify-owned), free to use; not open-licensed → `link_only`/`embed_only`, never cache | Polypad offers sanctioned iframe embed URLs; if embedded, host must be added to `MediaEmbed.hosts` **and** a policy entry created. Safest today: EMBED_ONLY deep-link card | Grades 3–12, excellent for manipulatives | Sitemap + curated topic pages exist; no public search API → curate a pack (like `media_packs/simulations.json`) or deep-link |
| Desmos Classroom | https://teacher.desmos.com/ | **200** | ⚠︎ Free; proprietary Desmos Inc. licence; free teacher account needed to *build*, most activities run without login | Activities are not iframe-friendly generally → deep-link card. Desmos Graphing Calculator API exists but needs a registered API key | Grades 6–12 | Public activity search on site (requires session for full results); no open search API → curated pack + deep link |
| PhET Interactive Simulations | https://phet.colorado.edu/ | (already integrated; live per repo evidence) | CC BY-NC 4.0; `commercial_ok=False`; `embed_only` policy `PHET_SIMULATIONS` in `ingest/policy.py:709` | Sanctioned iframe embed; already in Swift `MediaEmbed.hosts` (`phet.colorado.edu`) | Elem→HS | Mapped per-concept via `app/simulation_map.py` + `media_packs/simulations.json` (40 PhET / 31 Gizmos rows) — the model to copy for games |
| Gizmos (ExploreLearning) | https://gizmos.explorelearning.com/ | (integrated) | Proprietary, per-seat subscription; `link_only`, authenticated deep link only (`policy.py:727`) | Deep link only; embed refused by policy | MS/HS | Catalogue browsable, no public API; LTI/OneRoster institutional integrations only |
| NRICH (Univ. of Cambridge) | https://nrich.maths.org/ | **200** | ⚠︎ © University of Cambridge; free for classroom use, not openly licensed → `link_only` | No embedding granted → deep-link card | K–12, low-floor/high-ceiling tasks, strong "innovative math game" fit | Structured site search + sitemaps exist; scrapable titles, but rights say link-only citation, no text ingestion |
| Transum | https://www.transum.org/Software/ | **200** | ⚠︎ Free core + paid premium subscription; © Transum → `link_only` | No embedding; deep-link card | Primarily KS2–KS4 (ages 7–16) | Topic-indexed pages (e.g. /Software/Game/) are effectively a structured catalogue → good curated-pack source |
| Math Is Fun (games) | https://www.mathsisfun.com/games/index.html | **200** | ⚠︎ © Mathsisfun.com; free, ad-supported; linking allowed, copying not → `link_only` | In-page games, no embed grant → deep-link card | Elementary→MS | Flat, stable URL structure per game → easy curated pack |
| Prodigy Math | https://www.prodigygame.com/ | not checked (budget) | ⚠︎ Free with mandatory student/teacher accounts; freemium membership upsell; proprietary | App requires login → not embeddable; deep link only, and account wall makes it weak class material | Grades 1–8 | No public search API; not a good agent-searchable source — recommend excluding |
| Brilliant | https://brilliant.org/ | not checked (budget) | ⚠︎ Freemium with a hard paywall (most interactive courses are subscription); proprietary | No embeds → `link_only`; paywall makes it weak for a classroom | 13+ | No open API; recommend excluding or link-only reference |
| GeoGebra (recommended addition) | https://www.geogebra.org/ | not checked (budget) | ⚠︎ GeoGebra offers free materials; non-commercial-style licence on materials, calculator source under free software licence; embed codes sanctioned for many materials → best candidate for a **second** embed host after policy audit | iframe embed for materials (their own player/pages) → would need `MediaEmbed.hosts` + policy entry (embed_only, `commercial_ok=False` pending audit) | MS→HS | Materials have public search pages and a Materials API → genuinely agent-searchable |

**Source-class verdict.** The only host already cleared for in-app rendering is
`MediaEmbed.hosts = {youtube-nocookie.com, youtube.com, phet.colorado.edu}`
(`native/Sources/LearningHarness/MediaTools.swift:121-133`). Everything in the table
except PhET lands as a **deep-link card** today; making Mathigon Polypad or GeoGebra an
embedded host is a two-file rights change (policy.py + MediaTools.swift), never a
frontend-only change.

## YouTube search options

Constraints already in code: `video.py` is curated-allowlist-first because one Data API
search costs 100 of the 10,000 default daily units (`DATA_API_SEARCH_COST`,
`video.py:56-57`); `settings.youtube_api_key` already exists (`config.py:113`) and is
used for authoritative `status.embeddable` probing, falling back to keyless oEmbed
(`video.py:310-307`). Any search feature must keep videos EMBED_ONLY: no download, no
transcript, per `assert_extraction_allowed` (`video.py:107`).

| Option | Practicality for this local backend | Verdict |
|---|---|---|
| **YouTube Data API v3 search** | Key needed. `youtube_api_key` already plumbed in config + `video.py`. 100 units/query → ~100 searches/day free. Returns clean structured results incl. `status.embeddable` | **Recommended primary** behind optional env var (e.g. `HARNESS_YOUTUBE_API_KEY` → settings field). Metered, honest about quota, reuses existing verify pipeline |
| **DuckDuckGo `site:youtube.com` search** | `web_search` in `tools_creation.py:521` already runs `duckduckgo_search.DDGS()` — a `query + " site:youtube.com"` hit list costs zero quota and zero new dependency. **Gap found:** `duckduckgo-search` is NOT listed in `backend/requirements.txt`, so the tool silently refuses where it isn't installed — add it to requirements when wiring this | **Recommended fallback.** Fragile-ish (DDG HTML scraping underneath), result quality lower than the Data API, but fail-honest today |
| yt-dlp search (`ytsearchN`) | `yt-dlp` is pip-installable and its search extractor returns structured results without downloading, but the project ships no yt-dlp and its association with downloading is exactly the posture `assert_extraction_allowed` refuses; automated access sits uneasily with YouTube ToS | **Do not add.** ToS/mission mismatch; gains little over DDG fallback |
| Scraping youtube.com result pages (`ytInitialData`) | No key, but brittle markup, consent walls, and explicit ToS prohibition on scraping | **Reject** |
| Invidious/Piped public instances | Live check: `https://inv.nadeko.net/` → **200** today, with `/api/v1/search?q=` JSON API. But public instances are volunteer-run, rate-limited, and frequently blocked by YouTube; reliability is unsuitable for a shipped feature. Could be tolerated as a best-effort tertiary probe only | **Not recommended as primary or fallback**; note as opportunistic |

**Recommendation:** primary = Data API v3 (env-var key, quota metered, per-video
embeddability probe reused); fallback = DDG `site:youtube.com` through the existing
licence-gated `web_search` path. Either way, every candidate video passes
`video.verify()` (oEmbed iframe probe, fail-closed) before a card can carry an
`embed_url`; unverifiable → plain link. Never download/transcribe.

## Flow into class material today (traced) + proposal

**Existing path (verified in code):**

1. Teacher types in the Studio/agent chat → `/agent/chat` turn → harness loop
   (`backend/app/harness/loop.py`) → tool dispatch through
   `REGISTRY` (`backend/app/harness/toolbox.py:695`). 26 registered tools, including
   `image_search` (openlicence image APIs via `media.py`), `web_search` (DDG, licence
   gate `_WEB_DOMAIN_RIGHTS`, `tools_creation.py:502`), `find_video`
   (**curated allowlist only** — no live search), `find_simulation`
   (`simulation_map.py` pack), plus `build_figure`, `compose_content`,
   `write_simulation`, etc.
2. Tool results are `ToolResult` payloads serialised into the agent message; media cards
   use the `media_card` shape (`video.VideoRef.to_media_card`) carrying
   `embed_url` / `watch_url` / `status` / `licence_class`.
3. Student/teacher client renders embeds only after the Swift gate
   `MediaEmbed.url` (`MediaTools.swift:127`): https-only, host in `MediaEmbed.hosts`,
   non-empty path; the WKWebView navigation delegate refuses off-host navigations and
   opens them in the system browser (`MediaTools.swift:154-166`).
4. Licence provenance: any card whose `policy_name` does not resolve in
   `ingest/policy.py` is **withheld** by `reapply_media_policy` (`policy.py:840-889`) —
   so a new game source must be registered there or its card dies at render time.

**Proposal — where a teacher search result lands:**

- New tools `find_game(ctx, query)` and `search_videos(ctx, query, limit)`, registered
  in `toolbox.py` like the others and surfaced as **teacher-only** (follow the
  `creation_gate` role pattern used by `write_simulation`; students should consume
  curated results, not run live searches).
- `find_game` returns deep-link cards (`kind: 'game'`, `status: 'reference_link'`,
  `integration_mode: 'deep_link'`, licence + `policy_name` stamped) → rendered in chat
  as a card with a `SafeLessonLink` (already https-enforced) opening in the system
  browser — matching the Gizmos posture, since only PhET/YouTube embed.
- `search_videos` returns `VideoRef.to_media_card`-shaped cards; embeddable-verified
  candidates render as `verified_embed` iframe cards (YouTube already whitelisted);
  the teacher can then **attach to concept** — persisting the row into
  `media/video_allowlist.json` via `video.save_allowlist` so the curated path
  (`find_video`, student-facing) picks it up. That is the "attach to concept" landing
  spot: the allowlist file, not a new storage surface.
- Web-search results for games reuse `web_search`'s link-only semantics; extend
  `_WEB_DOMAIN_RIGHTS` with the audited game domains (all `link_only` except PhET).

## Change list (exact files)

1. **`backend/app/ingest/policy.py`** — add audited `SourcePolicy` entries:
   `MATHIGON_POLYPAD` (embed_only **or** link_only pending a live embed-code audit,
   `commercial_ok=False` — Amplify/NC question), `DESMOS_CLASSROOM` (link_only),
   `NRICH` (link_only), `TRANSUM` (link_only), `MATH_IS_FUN` (link_only),
   optional `GEOGEBRA` (embed_only, pending audit); append them to `MEDIA_SOURCES`
   (`policy.py:787`) so `reapply_media_policy` resolves their cards.
2. **`backend/app/harness/game_search.py` (new)** — a curated games pack loader
   mirroring `simulation_map.py` + a JSON pack **`backend/app/media_packs/games.json`**
   (slug, title, URL, licence, policy_name, topics), with the same "named gap" honesty.
3. **`backend/app/harness/toolbox.py`** — register `find_game` and `search_videos`
   `ToolSpec`s (embed_only / link_only classes, teacher-gated).
4. **`backend/app/harness/video_search.py` (new) or `video.py` extension** — Data API
   `search.list` when `settings.youtube_api_key` set, DDG `site:youtube.com` fallback;
   every candidate through `video.verify()`; quota note via `search_quota()`.
5. **`backend/app/config.py`** — optional env var for the YouTube key (field
   `youtube_api_key` exists at `config.py:113`; wire `HARNESS_YOUTUBE_API_KEY`).
6. **`backend/requirements.txt`** — add `duckduckgo-search` (currently missing; web
   search silently refuses without it — verified by grep, no match in the file).
7. **`native/Sources/LearningHarness/MediaTools.swift`** — update `MediaEmbed.hosts`
   **only if** a new embed host (Mathigon Polypad / GeoGebra) survives the policy audit;
   deep-link game cards need no Swift change (`SafeLessonLink` already handles https
   links).
8. **`backend/app/main.py`** — expose the two tools to the teacher role in the
   `/agent/chat` tool list; optional Studio teacher-panel button follows existing
   `find_video` route at `main.py:1837`.

## Verified vs unverified

**Verified live (2026-10-11, HTTP status):**
`mathigon.org` 200 · `teacher.desmos.com` 200 · `nrich.maths.org` 200 ·
`transum.org/Software/` 200 · `mathsisfun.com/games/index.html` 200 ·
`inv.nadeko.net` (Invidious) 200.

**Verified in repo (read, not fetched):** `ingest/policy.py` source registry incl.
PhET/Gizmos/YouTube policies and `reapply_media_policy` fail-closed behaviour;
`video.py` EMBED_ONLY posture, oEmbed/Data-API verification and quota maths;
`toolbox.py` 26-tool registry and `find_video`/`find_simulation`/`web_search`
implementations; `MediaTools.swift` `MediaEmbed.hosts` whitelist (youtube,
youtube-nocookie, phet.colorado.edu) and off-host navigation refusal;
`config.py:113` `youtube_api_key`; `duckduckgo-search` **absent** from
`backend/requirements.txt`.

**Could not verify (budget exhausted / out of scope):** live licence pages of Mathigon,
Desmos, NRICH, Transum, Math is Fun (licence cells are marked ⚠︎ priors); Prodigy and
Brilliant account/paywall status; a second Invidious/Piped instance; GeoGebra liveness
and Materials API; whether any of these sites' current terms permit iframing (must be
checked before any `MediaEmbed.hosts` widening). None of the unverified items block the
deep-link/link-only recommendation; every one of them blocks an embed whitelist change.
