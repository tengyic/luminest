# Reference format → Luminest content map

**Run:** e4ce4b2a · **Date:** 2026-11-16 · **Status:** producer artifact, pending adversarial verification.

This document maps the visual and editorial structure of the user-supplied
reference landing page onto truthful Luminest content. The reference is used for
**format only**; its brand, pricing, subject counts, testimonials, institution
logos and product claims are not copied. The shipped site must contain zero hits
for the terms in `package_beta.py::BANNED_BRAND_TERMS`.

## 1. Reference page structure (format inventory)

| # | Reference block | What it does | Visual / asset role | Editorial rhythm |
| --- | --- | --- | --- | --- |
| 1 | Nav | Product, subjects, about, research, blog, sign in, CTA | Small serif wordmark + flat sans links | Short labels, one primary CTA |
| 2 | Hero | One-sentence category claim + schedule/availability subclaim | Warm off-white ground, large serif H1, figure collage at right | H1 → subhead → "try" button → inline proof row |
| 3 | Proof stats | Three numeric trust markers under hero | Hairline dividers, oversized numerals, tiny labels | `N+ sessions` / `4.7/5` / `N minutes` pattern; **numbers must be real for Luminest** |
| 4 | Three-part thesis | "not X / not Y / built to teach" | Alternating text blocks, small hand-drawn marks, paper scraps | One否认 per line, then positive claim, then "learn more" link |
| 5 | Features grid | Eight capability tiles, two columns on desktop | Each tile pairs one line of copy with one paper-cut/sticker/whiteboard image | Verb-first title, one explanatory sentence |
| 6 | Audience triptych | Students / Parents / Teachers, each with 3 cards | Full-bleed tinted sections, large hand-drawn figure, three stacked paper cards | "X is for [audience]" → 3 short benefit cards → CTA |
| 7 | Testimonials | Social proof carousel | Quotation cards, tiny attribution | **Do not copy; Luminest has no verified testimonials** |
| 8 | FAQ | Ten expandable questions | Two-column list, hairline rules | Question → direct answer, no hedging |
| 9 | Final CTA | Emotional closer + blog cards | Large centered serif line, cloud/landscape motif | "A little help. A lot to learn." → CTA |
| 10 | Footer | Product / resources / company / legal columns | Quiet sans links, paper-cloud motif | Plain routing and legal links |

## 2. Reusable format tokens

| Token | Reference behaviour | Luminest-safe implementation |
| --- | --- | --- |
| Ground | Near-white `#fdfdfc` with paper grain | Keep current cream ground; add CSS radial/repeating gradients, no external texture needed |
| Type pairing | Display serif + neutral sans | Use local `Georgia, 'Times New Roman', serif` for display, system sans for body; no proprietary webfont |
| Scale | H1 ~64–80px, section H2 ~40–52px, body ~16–18px | Same ratios with `clamp()` so mobile stays readable |
| Spacing | Wide vertical rhythm, generous side gutters | `clamp(56px, 8vw, 120px)` between sections, max-width ~1180px |
| Paper scraps | Torn edge, slight rotation, drop shadow | CSS `clip-path` + subtle `box-shadow`; reuse `assets/art/*` PD scans |
| Stickers / stars / checks | Hand-drawn marks punctuate claims | CSS `clip-path` stars/checks; open-licensed scans from `outputs/reference-style-assets/` after verification |
| Dotted path | Curves through audience cards | Inline SVG with dashed stroke, no tracking, decorative only |
| Buttons | Small pill or underlined CTA | Keep existing share-code and web CTA buttons; do not introduce purchase CTA |
| Stats | Big numerals, tiny labels | Use only measurable Luminest numbers: 12 captures, 8 PD works, beta cohort facts |

## 3. Section-by-section Luminest mapping

| Reference block | Luminest content | Evidence source | Must not claim |
| --- | --- | --- | --- |
| Nav | Luminest · Closed beta · See it working · Get access · Downloads · Platforms · Web version | Current `index.html` nav | Pricing, sign-in-only flow, subject catalogue |
| Hero | "The AI that refuses to think for you." / "It chooses your next move, and shows you why — including when it isn't sure." | Current hero + `BRAND_DECISION.md` | "world's first", tutor rankings |
| Proof stats | `12` real app captures · `8` public-domain works · `0` billing in beta · `share-code` gated | `assets/captures.json`, `assets/art.json`, `ACCESS.md` | Sessions tutored, average rating, minutes taught |
| Three-part thesis | "Not a chatbot." / "Not an answer engine." / "Built to show its reasoning." | Current `Why this is different`, grounded tutor copy | Any competitor product name or comparative score |
| Features grid | Decision card; knowledge map; submitted answers only; grounded tutor; projects; review queue; insights; consent controls | Current six You/Luminest dialogues + `assets/captures.json` | Whiteboard, 65 subjects, PDF upload, voice tutoring claims not present in Luminest |
| Audience: Students | Next concept with reason; course map; practice evidence; project feedback; review queue; web fallback | Current captures + `DISTRIBUTION.md` | Guaranteed grades, SAT/AP coverage |
| Audience: Parents | Share-code access; consent controls; no silent collection; session evidence; no billing; web path | `ACCESS.md`, `agreement.html` | Parent dashboard that does not exist; email reports |
| Audience: Teachers | Curriculum evidence; concept mapping; local-first app; no student-data sale; no payment | Current site + `DISTRIBUTION.md` | Classroom rollout, institution logos, free-teacher programme |
| Testimonials | Replace with "Evidence, not anecdotes": 12 unretouched captures + licence record | `outputs/app-screenshots/MANIFEST.md` | Invented parent/student quotes |
| FAQ | Share code? Email? Billing? Which devices? Updates? Data? How is this different? | `ACCESS.md`, `DISTRIBUTION.md`, `agreement.html`, `WEBCLIENT.md` | Pricing tiers, magic links, phone support |
| Final CTA | "A little help. A lot to learn." style closer, but Luminest wording: learning stays visible | Current hero CTA | Third-party tagline verbatim |
| Footer | Downloads / agreement / install / licence record / web version / platform matrix | Current footer | Legal pages that do not exist |

## 4. Asset-role inventory for the user-supplied images

| Supplied image class | Intended role in reference | Ship decision |
| --- | --- | --- |
| `cream-paper.png`, `map-paper.png`, `parent-paper.png`, `teacher-paper.png`, `student-header-paper.png` | Paper texture, torn backgrounds | Use CSS gradients/`clip-path`; do not copy the supplied PNGs |
| `access-for-all-hires.png`, `parent-dashboard-hires.png`, `study-plans-hires.png`, etc. | Audience cards showing product UI | Replace with Luminest's 12 real release-build captures |
| `student-header-figure.png`, `teacher-figure.png`, `parent-family.png` | Hand-drawn audience figures | Use open-licensed Commons figures or CSS silhouettes |
| `*-star-*.png`, `teacher-check-*.png`, `teacher-grade.png`, `teacher-books.png`, `student-header-bulb.png` | Small decorative marks | Use open-licensed scans from `outputs/reference-style-assets/` after verification, or CSS shapes |
| `map-paper.png` + antique map | Dotted journey / exploration metaphor | Existing verified PD map in `assets/art/map.jpg` |

The supplied images are design assets from the reference project. They are **not**
shipped unless an independent licence record is produced; the fail-close posture
matches `fetch_art_assets.py` and the harness media policy.

## 5. Acceptance checklist for the implementer

1. Three live variants: `/` (A), `?variant=conversation` (B), `?variant=fieldnotes` (new).
2. New variant is scoped; A and B render byte-identically to their previous behaviour.
3. Zero hits for `BANNED_BRAND_TERMS` in shipped text files.
4. No invented statistics, testimonials, pricing, subject counts or institution logos.
5. All stats trace to `assets/captures.json`, `assets/art.json` or `ACCESS.md`.
6. All image `src` resolve locally; no reference-project path is shipped.
7. Share-code form, download gating, lightbox, art cabinet and PWA links still work.
8. Mobile layout keeps one column; no horizontal overflow at 390px.
9. New variant uses the reference *rhythm*, not the reference brand.
10. Build and `assert_no_banned_brand()` pass before any publish.

## 6. Producer honesty

The orchestration node for this artifact was unavailable; the main thread wrote
this document from direct reads of the reference HTML, current shipped HTML and
the cited evidence files. No subagent output was fabricated.
