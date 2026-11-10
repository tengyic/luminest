# Multimodality: configuration reference

Operator-facing. Everything here is a setting or a row the operator controls; turning
multimodality on is flipping `HARNESS_MEDIA_ENABLED=1`, and charging for it is
granting entitlements (see `pay-to-enable.md`). No code change is required for
either, and none is required to switch a capability off after an incident.

The matrix itself lives in `app/capabilities.py` and is served at
`GET /api/v1/capabilities`, so what the client shows and what the server enforces is
literally the same table. This document is the human-readable copy.

## The settings

All settings are environment variables, read once by `Settings.from_env()`
(`app/config.py`). Defaults shown are the shipped defaults; `production` flips a few
of them (noted). Restart the API after changing any of them.

| Setting | Env var | Default | What it turns on / off |
|---|---|---|---|
| Network media master switch | `HARNESS_MEDIA_ENABLED` | `1` in dev/test, `0` in production | Images, video probes, speech, web search and page fetch all refuse with a reason when off. This is the kill switch for every outbound media call. |
| Media timeout | `HARNESS_MEDIA_TIMEOUT_SECONDS` | `12` (1–60) | Per search/download. A slow image API must not hold a lesson. |
| Image cache location | `HARNESS_MEDIA_CACHE_DIR` | data dir | Where cached images live; export and delete cover this directory. |
| Commercial use | `HARNESS_COMMERCIAL_USE` | `0` | Declares the instance paid. Non-commercial sources (Khan Academy, PhET, MIT OCW) are then withheld by evaluation, not by memory. Set this **before** charging. |
| YouTube Data API key | `HARNESS_YOUTUBE_API_KEY` | empty | Authoritative embeddability check (`status.embeddable`) and teacher video search. Without it: keyless oEmbed probe and no search. |
| Openverse credentials | `HARNESS_OPENVERSE_CLIENT_ID`, `HARNESS_OPENVERSE_CLIENT_SECRET` | empty | Lift Openverse from 20 req/min and 200/day to 10,000/day. |
| Browser switch | `HARNESS_BROWSER_ENABLED` | `0` | The teacher-only Playwright page-snapshot tool. Off everywhere until an operator decides. |
| Language model | `HARNESS_TUTOR_PROVIDER` (+ `HARNESS_TUTOR_URL`, `HARNESS_TUTOR_MODEL`, `HARNESS_TUTOR_KEY`), or Settings → Language model | unset (`model-required`) | Required. The single cost driver behind course creation and model-improved generation. There is no offline mode; an unconfigured instance reports `model-required` and shows only declared grounded fallbacks. |
| Operator comps | `HARNESS_ENTITLEMENTS` | empty | Comma-separated `selector:capability,capability`. Selector is an email or `*`. Grants paid capabilities with no payment provider at all. |
| Paid monthly ceiling | `HARNESS_PAID_MONTHLY_REQUESTS` / `HARNESS_PAID_MONTHLY_TOKENS` | `2000` / `2000000` | The `quota_policies` row a grant installs. Soft enforcement: it records and reports, it does not block. |

There is no `HARNESS_MULTIMODALITY` flag, and that is deliberate: there is no single
switch that means "all of it", because each capability has its own provider, its own
cost and its own fallback. The master switch for the paid network capabilities is
`HARNESS_MEDIA_ENABLED`; `HARNESS_BROWSER_ENABLED` covers the one capability that is
not a media fetch.

## The matrix

`status` is the code reality, determined by reading the call site that would have to
run — not by reading a roadmap. `tier` is one of exactly two values, because a tier
the quota machinery cannot enforce is a label rather than a fact.

| id | tier | provider (cost driver) | readiness knob | fallback when unavailable | status |
|---|---|---|---|---|---|
| `images` | plus | Openverse / Wikimedia / Met / NASA, keyless HTTPS through the licence gate; Openverse anonymous cap 20/min, 200/day | `HARNESS_MEDIA_ENABLED` (+ optional Openverse credentials) | Deterministic figures from the symbolic engine; only real photographs are withheld, and the lesson says which is which | implemented |
| `video` | plus | YouTube oEmbed keyless probe; Data API key for authoritative embeddability and teacher search (100 units/query of a 10,000/day quota) | `HARNESS_MEDIA_ENABLED` (+ optional `HARNESS_YOUTUBE_API_KEY`) | Curated allowlist renders as plain outbound links; an unverified video is never embedded | implemented |
| `audio_tts` | plus | Local VoiceStudio backend (`POST /v1/audio/speech` on loopback, default `http://127.0.0.1:3900`). No cloud call, no per-character cost, no key — the learner's text does not leave the host. The readiness probe tries `/.well-known/voicestudio-speech` then `/v1/models` and reports an absent service as `degraded` | `HARNESS_MEDIA_ENABLED` + a running VoiceStudio (`HARNESS_VOICE_*`) | Lesson stays text; deck speaker notes remain. No audio is faked | implemented |
| `web_search` | plus | DuckDuckGo via the `ddgs` package, every result licence-gated. Installed and live. (`duckduckgo-search` was renamed to `ddgs`; its final 8.1.1 release is a rename stub whose backend returns zero results, so `ddg_provider` resolves `ddgs` first) | `HARNESS_MEDIA_ENABLED` + the `ddgs` package | No live search; local material-pack search and citations to what was actually read | implemented |
| `browser_snapshot` | plus | Playwright headless Chromium over the open network, teacher-only | `HARNESS_BROWSER_ENABLED` + teacher role | None — the tool refuses. A snapshot is a copy of pixels; there is nothing honest to substitute | implemented |
| `course_creation` | plus | The configured OpenAI-compatible model, metered in tokens | A configured model (Settings or `HARNESS_TUTOR_*`) | None — the builder refuses a plan it cannot ground | implemented |
| `vision_understanding` | plus | Would need image content parts on the chat API; the provider adapter is text-only | none yet | None. The image still shows with attribution; the tutor cannot comment on it | **missing** (listed so the UI hides it) |
| `simulations` | free | none — mathkit builds validated, self-contained HTML locally | none | Not applicable: fully offline | implemented |
| `whiteboard_rich` | free | none — local SVG document state | none | Not applicable | implemented |
| `flashcards_auto` | free | Model improves prose when configured; cards are grounded and FSRS-6 scheduled | A configured model (Settings or `HARNESS_TUTOR_*`) | Grounded curriculum cards when a configured model fails. With no model the instance reports `model-required` | implemented |
| `pptx_export` | free | `python-pptx`, installed locally | none | The HTML/SVG deck remains | implemented |

### The tutor chat is not in the matrix, on purpose

`POST /api/v1/chat` is not gated by a capability row, and that is a product decision
with a cost consequence the operator should see before charging. A language model is
required; with none configured the instance reports `model-required` and a chat turn
returns a declared grounded fallback, not a lesson. With a model configured, every turn
is a token spend that is *metered* (`usage_ledger`, feature `tutor_chat`) but not
*ceilinged* by this matrix.

Before charging, pick one: (a) keep chat free and treat model tokens as the cost of
the free tier, (b) meter per-account spend before forwarding a turn, or (c) add a
`tutor_chat` row to `CAPABILITIES` and call `require_capability` in the chat route.
There is no option to serve a deterministic tutor as a product tier. Option (a) is what
ships today; (b) is a config change; (c) is the only one that enforces a ceiling, and
it is a data change plus one dependency on the route. None of the three requires
touching the teacher core, because the core is a pure function of evidence and
profile - it does not know or care who paid.

### What "implemented" meant

Determined by the call site existing today: `app/routes_media.py` for image fetch,
`app/harness/video.py` + `video_search.py` for video, `text_to_speech` /
`web_search` / `fetch_page_text` in `app/harness/tools_creation.py`, `browser.py`
gated in the toolbox, `app/routes_create.py` for course creation, `app/flashcards.py`,
`app/deck.py` and `app/mathkit` for the local rows. The one row whose readiness is a
*service* rather than a package (`audio_tts`) is honest about it: the code path is
complete, the probe reports an absent VoiceStudio as `degraded`, and no audio is
faked in the meantime. Nothing in the matrix is a stub; the one genuine gap says
`missing`.

## How a capability resolves

For one caller, each row lands in exactly one state, and the state carries a `reason`
the UI shows verbatim:

- `enabled` — entitled (or free) and the provider probe passes.
- `degraded` — entitled, but the provider is off or its package is absent. The reason
  names the knob and the declared fallback. This is a first-class outcome, never an
  error: the same contract the language-model adapter has always kept.
- `withheld` — not entitled. Anonymous callers are told to sign in; signed-in callers
  are told the capability is part of Plus; lapsed entitlements are told they expired.
  A `missing` capability is also `withheld`, so the UI hides it rather than sells it.

Probes are import checks and settings reads, plus one loopback readiness check for the
local speech service — never an outbound network call — so
`GET /api/v1/capabilities` stays fast and offline-safe. An unknown or unauthenticated
principal resolves to the free tier and nothing else: there is no default allow.

## Enforcing the matrix at a call site

The matrix is authoritative for what the client is told; adopting it at an existing
route is one line, using the dependency provided for exactly that:

```python
from .capabilities import require_capability

@router.post('/api/v1/images/fetch')
def fetch_images(payload: FetchInput, request: Request,
                 capability=Depends(require_capability('images'))):
    ...
```

A withheld caller gets `402` with the matrix's own reason (including the payment
seam), and a degraded caller gets `503` naming the fallback. The existing routes
predate the matrix and do not yet carry the dependency — that adoption is the one
code change left, it is mechanical, and `tests/test_capabilities.py` proves the
dependency works before anyone makes it.

## Verifying the configuration

```bash
cd harness/backend

# What this instance offers, as an anonymous caller (the storefront view).
curl -s localhost:8765/api/v1/capabilities | python3 -m json.tool | head -40

# One capability in full.
curl -s localhost:8765/api/v1/capabilities/images | python3 -m json.tool

# The health endpoint still reports provider vocabulary it always did:
curl -s localhost:8765/health | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['tutor'], d['harness']['generation_mode'])"
```

`generation_mode` reads `model-required` when no model is configured and
`provider:model` when one is; that is the same vocabulary the capability matrix uses
for `course_creation`. `/health` also reports `tutor.state`, `tutor.source` (runtime vs
environment) and `tutor.api_key_set`. A capability whose probe fails shows `degraded` with the knob
named — if `images` is `degraded` on a production instance, the answer is almost
always `HARNESS_MEDIA_ENABLED=0`.

The full behaviour is pinned by `tests/test_capabilities.py`:

```bash
export TMPDIR="$PWD/.pytest-tmp"
/Users/tengyi/miniconda3/bin/python3 -m pytest tests/test_capabilities.py -q
```
