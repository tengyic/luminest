# Landing page — variant classification and final design

## Variant map (classified against files on disk, 2026-11-15)

Tengyi named six variants. Three map cleanly, one maps to a broken folder, and
two have **no exact on-disk match** — recorded as unknown rather than invented.

| User's name | Best match | Confidence | Evidence |
| --- | --- | --- | --- |
| **initial version** | `outputs/luminfest-site/index.html` | 0.95 | 891 lines, 2026-10-22, title "Luminfest — The AI that refuses to think for you. Algebra I · macOS beta"; warm-paper tokens; `legal/`, `assets/graph.json`; the site the website prompt pack §0.2 calls "the existing site" |
| **web version** | `harness/web/index.html` (+ `app.html`, `playground.html`) | 0.80 | "Luminfest Workbench", vanilla JS, no build; the product's in-browser workbench |
| **today's recreated version (disliked)** | `outputs/luminest-beta/` **and** `outputs/luminest-download-site/` | 0.85 | both created 2026-11-15; `luminest-beta/` has **no `index.html`** (only png + privacy/terms) → blank page; the download site says "learning infrastructure for thinking" |
| **base44 version** | no exact match | 0.0 | searched `outputs/**`, `reference/**`, `LUMINEST-WEBSITE-PROMPT-PACK.md`, `05_LANDING_PAGE_PROMPT.md`; no base44-named asset. Closest stylistic candidates are the dark generative-UI landings below |
| **ploy version** | no exact match | 0.0 | same search; no ploy-named asset. `outputs/vela-landing/` is an **empty** directory |
| **heysristotle like version** | no exact match; closest `outputs/learnyourway-replica/index.html` | 0.45 | Google "Learn Your Way — Immersive Text" 1:1 replica with a conversational/immersive reading surface; `outputs/stitch-landing/` and `outputs/weave-landing/` are dark "Design with AI" generative-UI pages |

**Not guessed.** The two unmatched names are reported as unknown with the paths
searched. If those variants live outside this workspace, point me at them and
I will classify and port them.

## Final decision

**Base: `initial version`** (`outputs/luminfest-site/`), because it is the only
variant with (a) a complete editorial structure, (b) a documented honest-claims
ledger, (c) real legal pages, and (d) design tokens that are already the product's
visual language. Tengyi said he would consider the initial or the
heysristotle-like version more, so **both are delivered live**, not just described:

- `/` → Design A, the original editorial hero.
- `/?variant=aristotle` → Design B, a Socratic-conversation hero carrying the
  "it asks the question you skipped" idea from the immersive-text replica,
  explicitly labelled *"Illustrative dialogue — not a live model"* so no
  capability is implied.

Switching is a query parameter, so finalising is a one-line default change, not
a rebuild. `/` currently defaults to Design A.

## What was carried over / removed

| Carried from initial | Removed / fixed |
| --- | --- |
| Warm-paper tokens (`--paper #F7F5F0`, `--pine`, `--sage`, serif/sans/mono stack, `.micro` letterspaced labels, 1200px wrap) | "You're in the queue — Double opt-in — check your inbox" contradiction (§0.6 B3) |
| "What it will not claim" trio: certified grade / validated mastery / a guess is an observation | `beta@luminfest.example` placeholder address |
| Anti-hype, evidence-first stance | "macOS only / Windows and web are not in beta" — now false, the web version ships |
| No third-party requests, no trackers | "Free while in beta. No card" kept, but now backed by `billing_required: false` |

## New sections required by the closed beta

1. **Access** — real `POST /api/beta/redeem` form; no false success message. Demo
   code `LUMINEST-DEMO-2026` opens the browser build only.
2. **Downloads** — DMG/ZIP with measured sha256 (from the server manifest) and
   Gatekeeper instructions; links carry a server-verified token.
3. **Platforms** — honest matrix: native = macOS 14+/arm64; iPad, Intel Mac,
   older macOS, Windows, Linux → web version.
4. **Data & consent** — live schema link, explicit checkbox, fail-closed.
5. **Remote updates** — live manifest read + "check now".
6. **Terms** — `agreement.html`: non-commercial, PhET CC BY-NC, no
   redistribution, share-code rules, no billing, 90-day retention.

## Deliverable

`outputs/closed-beta-site/` — a single self-contained directory (landing page,
`app/` browser build, `downloads/`, `updates/`, `server.py`, legal pages).
See `DISTRIBUTION.md` for the distribution contract.

## Finalisation status (2026-11-15, run 03621090)

Both designs are **live and verified**, not described. The switch is the query
parameter only (`index.html:306`), so locking the default is a one-line edit:
`params.get('variant') === 'aristotle'` → default to `initial` by removing the
branch, or invert the condition to make the conversational hero the default.

Verified against the running local control server on `http://127.0.0.1:18799`:

| Route | Result |
| --- | --- |
| `/` (Design A, initial) | 200, 25 011 bytes |
| `/?variant=aristotle` (Design B) | 200, 25 011 bytes, JS-switched hero |
| `/app/`, `/app/manifest.webmanifest`, `/app/sw.js` | 200 / 200 / 200 (PWA shell real) |
| `/agreement.html`, `/INSTALL.txt`, `/download-manifest.json` | 200 / 200 / 200 |
| `/api/health`, `/api/beta/config`, `/api/beta/collect/schema`, `/api/updates/manifest.json` | 200 / 200 / 200 / 200 |

**Recommendation:** keep Design A as the shipped default. Tengyi said he would
consider the initial *or* the heysristotle-like version; Design A is the only one
with the complete editorial structure, honest-claims ledger and real legal pages.
Design B stays one click away. The final aesthetic pick is Tengyi's — the docs do
not pretend the decision has been made for him.

**Publish status — honest correction:** an earlier revision of this file said
"Published via the sites deploy". That claim is **false**. Three deploy attempts
(2026-11-15) all returned `SITES_APP_NOT_FOUND` / `retryable:false` for deleted
appId `wbapp_3EiXiwaWSovkxwc1HX78j5`, including one from a clean directory outside
the workspace with no `.genie` / `applications.yaml` bindings. There is **no public
link** as of this revision. See `harness/docs/closed-beta/PUBLISH_BLOCKER.md`.
