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
| **conversational / immersive-reading reference** | no exact match; closest `outputs/learnyourway-replica/index.html` | 0.45 | Google "Learn Your Way — Immersive Text" 1:1 replica with a conversational/immersive reading surface; `outputs/stitch-landing/` and `outputs/weave-landing/` are dark "Design with AI" generative-UI pages |

**Not guessed.** The two unmatched names are reported as unknown with the paths
searched. If those variants live outside this workspace, point me at them and
I will classify and port them.

## Final decision

**Base: `initial version`** (`outputs/luminfest-site/`), because it is the only
variant with (a) a complete editorial structure, (b) a documented honest-claims
ledger, (c) real legal pages, and (d) design tokens that are already the product's
visual language. Tengyi said he would consider the initial or the
conversational / immersive-reading reference more, so **both are delivered live**,
not just described:

- `/` → Design A, the original editorial hero.
- `/?variant=conversation` → Design B, a conversational hero carrying the
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
`params.get('variant') === 'conversation'` → default to `initial` by removing the
branch, or invert the condition to make the conversational hero the default.

Verified against the running local control server on `http://127.0.0.1:18799`:

| Route | Result |
| --- | --- |
| `/` (Design A, initial) | 200, 41 830 bytes (after the art cabinet; was 34 668, originally 25 011) |
| `/?variant=conversation` (Design B) | 200, 41 830 bytes, JS-switched hero + conversational feature intro |
| `/app/`, `/app/manifest.webmanifest`, `/app/sw.js` | 200 / 200 / 200 (PWA shell real) |
| `/agreement.html`, `/INSTALL.txt`, `/download-manifest.json` | 200 / 200 / 200 |
| `/api/health`, `/api/beta/config`, `/api/beta/collect/schema`, `/api/updates/manifest.json` | 200 / 200 / 200 / 200 |

**Recommendation:** keep Design A as the shipped default. Tengyi said he would
consider the initial *or* the conversational / immersive-reading reference;
Design A is the only one with the complete editorial structure, honest-claims
ledger and real legal pages.
Design B stays one click away. The final aesthetic pick is Tengyi's — the docs do
not pretend the decision has been made for him.

**Publish status — honest correction:** an earlier revision of this file said
"Published via the sites deploy". That claim was **false at the time**: three
deploy attempts (2026-11-15) all returned `SITES_APP_NOT_FOUND` / `retryable:false`
for deleted appId `wbapp_3EiXiwaWSovkxwc1HX78j5`, including one from a clean
directory outside the workspace with no `.genie` / `applications.yaml` bindings.
That blockage was cleared on 2026-11-16 by publishing from a genuinely new
WorkBuddy task; the verified live link is
`https://wbapp-i2nxsckskaquxjurlmkfnp.app.workbuddy.host/?sharecode=<code>`.
The requested vanity host `luminest.app.workbuddy.host/` is still 404 because its
old application was deleted. See `harness/docs/closed-beta/PUBLISH_BLOCKER.md`.

## Brand scrub (2026-11-15, Tengyi's instruction)

> "do not make any aristotle text/str inside the website/html"

Both designs stay live, but **no third-party product or philosopher name appears
anywhere in the shipped site**. Concretely:

| Before | After |
| --- | --- |
| `?variant=aristotle` | `?variant=conversation` |
| JS condition `'aristotle'` | `'conversation'` |
| code comment `"hey-...-like" hero` | `Design B: conversational hero` |
| hero lead `A Socratic reading companion: ...` | `It does not hand over the answer. It finds the one step your reasoning left out and asks about that.` |
| `?variant=initial` back-link | unchanged (already neutral) |

The Design B hero keeps its content — "It asks the question you skipped.", the
illustrative dialogue labelled *"Illustrative dialogue — not a live model"*, and
the Design A / Design B switch. Only the naming changed.

**Guard against reintroduction:** `harness/scripts/package_beta.py` now runs
`assert_no_banned_brand()` as the last packaging step. It scans every shipped text
file (`.html/.htm/.txt/.json/.js/.css/.py/.webmanifest/.svg/.md`) for
`aristotle`, `heysristotle`, `socratic` (case-insensitive) and raises instead of
shipping. Verified both ways: clean site → `0 banned strings`; injecting a file
containing the string → `RuntimeError` naming the exact file and line.

All three site copies were updated (`outputs/closed-beta-site/`,
`/Users/tengyi/luminest-beta-public`,
`/Users/tengyi/WorkBuddy AI/luminest-beta-publish`).

## Captured image examples + feature explanations (2026-11-15)

Tengyi: "add the captured image examples, and like [the conversational
variant], explain features". Delivered as a new `#features` section directly
below the hero, on **both** designs.

**Images are real, not generated.** Source: the page-ready presentation set at
`outputs/app-screenshots/presentation/` — 12 frames captured 2026-10-19 from
the release build at 2640 × 1720 (2× retina), test chrome suppressed, no
retouching beyond geometric resize. Provenance, the capture command, and the
blank-check results are in `outputs/app-screenshots/MANIFEST.md`. The
`reference-only/` and `qa-raw/` sets were deliberately **not** shipped.

| Item | Implementation |
| --- | --- |
| Web assets | 12 × 1200 px JPEG at quality 68, 1.1 MB total, in `outputs/app-screenshots/web/` → `assets/captures/` |
| Manifest | `assets/captures.json` records filename, bytes and measured sha256 for every frame |
| Packaging | `package_beta.py::copy_captures()` copies all 12, refuses a blank-looking frame (<20 KB), and writes the manifest; runs inside every build |
| Feature cards | 6 question-led `.dialogue` cards (You / Luminest), each paired with the real frame it describes |
| Full set | 12-thumbnail `.capgrid` with the manifest's own captions, click-to-enlarge lightbox (Esc / backdrop / Close) |
| Design B link | `?variant=conversation` also swaps `#featuresIntro` to the conversational framing: *"You asked what it actually does. Here are six answers — each one next to the real screen it came from…"* |

**Claims discipline.** Every answer is grounded in the screen it sits next to
and in the product's existing copy — decision card, map strands, recorded
attempts, grounded tutor with sources, projects + feedback, insights + consent.
No certified grade, no validated mastery, no invented capability. The section
closes by naming the rough edges the capture manifest itself records (streak
wording, older sign-in splash, raw enum label, internal vocabulary) rather than
quietly fixing the picture.

**Verification:** all 12 generated JPEGs were independently checked for blank
output with PIL (80×52 downsample, 376–1091 distinct colours, variance
155.6–1740.8 — all NONBLANK). All 12 HTML `src` references resolve to real
files; 6 feature cards + 12 gallery figures counted; live HTTP returns
`200 image/jpeg` for captures and `200 application/json` for the manifest.
Full `package_beta.py` run exits 0 with the brand guard green.

## Artistic assets — real paintings and decorative frames (2026-11-15)

Tengyi supplied three collage references (classical reading figures cut out over
torn manuscript paper with maths, a framed whiteboard with two children, a
magnifier over a document) and asked for **actual artworks found on the
internet**, not generated ones.

**Sourced, not generated.** `harness/scripts/fetch_art_assets.py` queries the
Wikimedia Commons API by exact file title and downloads eight works. It is
fail-close: a work is written to disk only when Commons `extmetadata` reports
`Public domain` / `CC0` / `PD-*` **and** `Copyrighted` is not `True`. One
candidate (`File:Principia Mathematica. Newton.jpg`, CC0 but flagged
copyrighted) was **refused** and replaced with a clean PD scan. Re-run command:
`env -u PYTHONPATH python3 harness/scripts/fetch_art_assets.py`.

| Work | Artist / date | Role on the page |
| --- | --- | --- |
| `reader.jpg` | Jean-Honoré Fragonard, c. 1770 | gilt-framed painting |
| `lesson.jpg` | Léon Bazille Perrault, 1866 | walnut-framed painting |
| `map.jpg` | Jan Janssonius, 1650 | torn-paper collage tile |
| `botany.jpg` | *The American Flora*, pl. 23, 1855 | round botanical accent |
| `lamp.jpg` | T. A. Edison patent drawing, 1881 | round accent |
| `astronomer.jpg` | Johannes Vermeer, 1668 | specimen plate |
| `geographer.jpg` | Johannes Vermeer, 1669 | specimen plate |
| `principia.jpg` | Isaac Newton, 1687 | specimen plate |

**Frames are real CSS decoration, not downloaded clip-art.** `#cabinet` sits
between the hero and the features section on both designs: a dark cocoa panel
with two overlapping tilted paintings in gilt/walnut frames, a torn-paper map
tile (`clip-path` jagged polygon), two circular brass accents, and CSS gold
stars. Below it, three brass-mounted specimen plates with artist/date/licence
captions; the Principia plate carries a CSS magnifier lens, echoing the third
reference image. The prior "no third-party name in the HTML" rule is preserved
— zero hits for the banned terms.

**Provenance travels with the site.** `assets/art.json` records title, artist,
date, licence, licence URL, Commons source page, retrieval time, and the
measured sha256 of each shipped file. `package_beta.py::copy_art()` re-checks
those licences on every build and aborts if any work loses its evidence. The
landing page links to that record rather than making an unbacked claim.

Web-optimised to ≤900 px / JPEG q72, **706 KB total** for all eight. Every file
was checked non-blank with PIL (199–4423 distinct colours, variance
204–2407). A contact sheet for visual review is at
`outputs/art-sources/contact-sheet.jpg`.
