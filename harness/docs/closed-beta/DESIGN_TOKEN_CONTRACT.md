# Design token contract — fieldnotes variant

**Run:** f339c01d · **Date:** 2026-11-16 · **Scope:** `body.variant-fieldnotes` only.
Design A (`/`) and Design B (`?variant=conversation`) keep their existing CSS.
Tokens below are transcribed from Tengyi's supplied reference specification; the
main thread wrote this contract because all three producer nodes were
`not available`. No subagent output was fabricated.

## 1. Typography

| Token | Exact value | CSS variable | Luminest use |
| --- | --- | --- | --- |
| `type-title-display` | `2rem → 3rem` | `--type-title-display:clamp(2rem,4vw,3rem)` | `#heroTitle` in fieldnotes |
| `type-heading-1` | `1.875 → 2.625rem` | `--type-heading-1:clamp(1.875rem,3vw,2.625rem)` | stat numerals, final CTA H2 |
| `type-heading-2` | `1.5 → 2rem` | `--type-heading-2:clamp(1.5rem,2.4vw,2rem)` | audience headings, mobile stat numerals |
| `type-heading-3` / `title-lg` | `1.375 → 1.75rem` | `--type-heading-3:clamp(1.375rem,2vw,1.75rem)` | thesis / feature / FAQ headings |
| `type-lead` | `1.125 → 1.25rem` | `--type-lead:clamp(1.125rem,1.6vw,1.25rem)` | `#heroLead` |
| `type-body` | `1rem` | `--type-body:1rem` | body, audience list items |
| `type-small` | `.875rem` | `--type-small:.875rem` | captions, feature copy, fineprint |
| `type-eyebrow` | `.75rem` | `--type-eyebrow:.75rem` | `.micro`, stat labels, `.fn-num` |

## 2. Palette

| Role | Token | Exact value | Use |
| --- | --- | --- | --- |
| Page background | `--palette-sand-1` | `#fdfdfc` | body background, card surfaces, tags |
| Body text (ink) | `--palette-sand-12` | `#21201c` | body copy and explanatory text |
| Brand / primary | `--palette-umber-9` | `#261608` | H1/H2/H3, stat numerals, borders, star bullets |
| Brand surface (light) | `--palette-umber-3` | `#f6efea` | hero panel, audience cards, final CTA |
| Inverse / footer | `--palette-umber-12` | `#2c1c0e` | reserved for dark inverse contexts; not forced into A/B |
| Theme-color | `meta[name=theme-color]` | `#fdfdfc` | mobile browser chrome |

### Machine-readable palette block

```css
--palette-sand-1:#fdfdfc;
--palette-sand-12:#21201c;
--palette-umber-9:#261608;
--palette-umber-3:#f6efea;
--palette-umber-12:#2c1c0e;
```

## 3. Grid, radii, containers

| Family | Exact values | Use |
| --- | --- | --- |
| 4px base grid | `--space-1:.25rem`, `--space-2:.5rem`, `--space-3:.75rem`, `--space-4:1rem`, `--space-5:1.5rem`, `--space-6:2rem`, `--space-7:2.5rem`, `--space-8:3rem`, `--space-9:4rem` | section padding uses space-8/9; card gaps/space-5/6; inline spacing space-1/4 |
| Radii | `--radius-sm:.25rem`, `--radius-md:.5rem`, `--radius-lg:.75rem`, `--radius-xl:1rem`, `--radius-pill:9999px` | cards use lg/xl; CTA and tags use pill; no sharp corners in fieldnotes |
| Containers | `--container-narrow:40rem`, `--container-default:64rem`, `--container-shell:72rem`, `--container-wide:80rem` | `.wrap` uses shell; hero title uses default; final CTA uses narrow |

## 4. Motion and texture

| Token | Exact value | Use |
| --- | --- | --- |
| Durations | `--dur-1:.12s`, `--dur-2:.18s`, `--dur-3:.28s`; `--ease-out:ease-out` | card transform / shadow transitions; CTA hover |
| Hover tilt | `rotate(-.75deg)` on `.fn-line:hover`, `.fn-person:hover`, `.fn-feature:hover` | subtle handmade movement |
| Reduced motion | `@media (prefers-reduced-motion:reduce)` sets `transition-duration:.01ms!important; animation:none!important; transform:none!important` inside fieldnotes only | accessibility |
| Rough paper edge | `<filter id="fn-rough-paper">` with `feTurbulence fractalNoise baseFrequency=0.04 numOctaves=2 seed=17` + `feDisplacementMap scale=1.5` | applied to thesis lines, audience cards and feature cards only |

## 5. Acceptance checklist

1. `:root` contains every exact token value above.
2. `meta[name=theme-color]` is `#fdfdfc`.
3. `body.variant-fieldnotes` uses sand-1 / sand-12 / umber-9 / umber-3.
4. Fieldnotes section padding resolves to space-8/9 (3–4rem).
5. Fieldnotes `.wrap` resolves to 72rem shell; CTA copy to 40rem narrow.
6. All fieldnotes cards use radius lg/xl; CTA and tags use pill.
7. Hover tilt is exactly `-.75deg`; reduced-motion rule neutralizes it.
8. SVG filter id `fn-rough-paper` exists and is referenced only inside fieldnotes.
9. A/B hero text and behaviour are unchanged.
10. `package_beta.py::BANNED_BRAND_TERMS` count is 0 in shipped text.
11. The brand palette scale in §6 is present verbatim (80 tokens),
    `palette_scale.py --check` exits 0, and **no colour-list section exists** —
    the ramp appears only as `.tint-*` on real content blocks.
12. Decoration is balanced per §7: no more than two consecutive sections without
    artwork or ornament, and at least two plates below the fold.

---

## 6. Brand palette scale (2026-11-16)

Scope: **all three variants**. §1–§5 stay fieldnotes-scoped and unchanged; this
section adds the eight brand hues as usable ramps so components stop reusing a
single tone for surface, border, accent and text.

### 6.1 The nine brand colours stay literal

| Alias | Value | Ramp step it lands on |
| --- | --- | --- |
| `--sage` | `#E7EDE3` | `sage-200` |
| `--pine` | `#2B3A2E` | `pine-900` |
| `--lilac` | `#E6E3F2` | `lilac-100` |
| `--clay` | `#B5725A` | `clay-500` |
| `--olive` | `#7C8B6B` | `olive-600` |
| `--iris` | `#8E86A8` | `iris-500` |
| `--amber` | `#D89A3F` | `amber-500` |
| `--sand` | `#EDE3D8` | `sand-200` |
| `--sage-bar` | `#8FA383` | literal only (progress bar) |

The aliases are not re-pointed at ramp steps — they stay as shipped so no
existing rule changes. The table only records where each one sits.

### 6.2 Derivation rule

Ten steps per hue (`050 100 200 300 400 500 600 700 800 900`), generated by
`harness/scripts/palette_scale.py`:

1. The brand hex is converted to HSL.
2. A fixed lightness ladder is laid over the steps:
   `.97 .94 .88 .79 .68 .57 .46 .36 .27 .19`.
3. Hue is preserved exactly. Saturation is only nudged — `×1.25` at
   `L ≥ .85` (capped at `.46`), `×0.90` at `L ≤ .35`.
4. The brand hex is **pinned** at the ladder step closest to its own lightness,
   so that step renders the literal brand colour. Neighbouring steps are pushed
   at least `.02` L apart, keeping the ramp monotonic.

Because of §6.2 step 4 the pinned step differs per hue: `sage-200`, `pine-900`,
`lilac-100`, `clay-500`, `olive-600`, `iris-500`, `amber-500`, `sand-200`. On
the page those eight swatches carry a `.is-brand` ring and the hue label reads
`brand hex pinned at <step>`.

### 6.3 Role of each step

| Steps | Role |
| --- | --- |
| `050`–`300` | surfaces, cards, borders |
| `400`–`600` | accent rules, fills, decorative bars |
| `700`–`900` | text, solid chips, deep inverse blocks |

### 6.4 Chip rule (computed, not chosen)

A solid chip (`900`-weight family colour, `paper` text at 11 px mono) uses the
**lightest step of that hue that still clears 4.5:1 against `paper`**:

| Hue | Chip step | Ratio |
| --- | --- | --- |
| sage | `sage-700` | 5.04 |
| pine | `pine-700` | 5.55 |
| lilac | `lilac-600` | 6.55 |
| clay | `clay-700` | 6.49 |
| olive | `olive-700` | 5.41 |
| iris | `iris-600` | 5.17 |
| amber | `amber-800` | 7.03 |
| sand | `sand-700` | 5.48 |

`clay-600` (4.48) and `amber-700` (4.47) were *rejected* by this rule — they
miss 4.5:1 by a hair. That is the reason the chips are not all on the same step.

### 6.5 Semantic roles

```css
--role-meta:var(--olive-700);
--role-accent:var(--clay-500);
```

Only the two roles the page reads. Block colour does **not** go through a global
role — it goes through the per-block tint below.

### 6.6 The palette lives inside the blocks

There is no colour list, swatch book or palette section on the page. The ramp
exists only as the way real content surfaces are painted. A block declares one
hue and derives five steps from it:

```html
<div class="card tint-lilac"> … </div>
```

```css
.tint-lilac{--tint-bg:var(--lilac-050);--tint-soft:var(--lilac-100);
            --tint-line:var(--lilac-200);--tint-accent:var(--lilac-600);
            --tint-ink:var(--lilac-900)}
```

| Role | Step by hue family | Used for |
| --- | --- | --- |
| `--tint-bg` | `050` (pale hues) / `100` (sage) | the block surface itself |
| `--tint-soft` | one step darker | tutor bubble, table head |
| `--tint-line` | two steps darker | border, list rules |
| `--tint-accent` | `600`–`800` (computed for AA) | 3 px top rule, `who` labels, captions |
| `--tint-ink` | `900` | headings and bubble text inside the block |

Painting is deliberately more specific than the component rule it must beat
(`.dl .item`, `.beta-sec`, `.panel`). That is not stylistic: the first pass used
a single-class `:is(...)` rule, `.dl .item{background:var(--surface)}` won on
specificity, and the download cards silently stayed white. The pixel audit caught
it; the selector list below is the fix.

```css
.card:is(...),.panel:is(...),.beta-sec:is(...),.dl .item:is(...),
.specimen:is(...),table:is(...){background:var(--tint-bg);border-color:var(--tint-line)}
```

Twenty blocks carry a tint, across all eight hues:

| Section | Blocks |
| --- | --- |
| hero | `.panel` sage |
| features | six capture cards — sage, lilac, amber, iris, clay, olive |
| access | `.beta-sec` sand |
| downloads | DMG sand, ZIP sage, install card pine |
| platforms | `<table>` olive |
| data | consent card lilac, never-collected card sand |
| updates | manifest card amber |
| limits | three cards — clay, iris, olive |
| terms | Use sand, Content licensing lilac |

### 6.7 Verifiers

```bash
python harness/scripts/palette_scale.py --check outputs/closed-beta-site/index.html
python harness/scripts/audit_tint_pixels.py
python harness/scripts/audit_page_balance.py
```

- `--check` reproduces the ramp, asserts all 80 tokens ship verbatim, requires
  every `.tint-*` class to declare the contracted steps, counts the tinted blocks
  and hue families in the markup, recomputes 36 text/background ratios, and
  **fails if a colour-list section or `data-token` swatch markup reappears**.
- `audit_tint_pixels.py` reads each tinted block's computed background and then
  screenshots it and samples a pixel, so a more specific rule winning is caught
  twice over.
- `audit_page_balance.py` counts artwork, plates and ornaments per section, fails
  on a bare stretch longer than two sections or a lower half with fewer than two
  plates, and renders every variant.

---

## 7. Artistic balance

The public-domain cabinet, the specimen plates and the twelve captures all sat in
the top third; every section below `#features` was plain text and flat cards.
Decoration is now carried down the page by the same vocabulary rather than by new
imagery:

| Element | Where | Notes |
| --- | --- | --- |
| Layered paper collage `article.collage` | `#who` (3 cards) | format borrowed from the reference page, assets are not — see §7.1 |
| Brass plate `figure.plate-sm` | `#downloads`, `#platforms`, `#data`, `#limits` | same eight PD works, different mount; `figure-wide` 158 px, `figure-narrow` 124 px, `.alt` walnut frame |
| Rule + stars `div.orn` | `#cabinet`, `#features`, `#platforms`, `#updates`, `#terms` | pure CSS, no asset cost |
| Tinted surfaces | 20 blocks, 8 hues | see §6.6 |

Measured (audit `page-balance-2026-11-16.json`): art/plate elements **14 in the
top half, 4 in the bottom half**; ornaments **2 / 3**; no run of more than two
consecutive sections without either. Seven of the eleven rendered sections carry
artwork, at 2, 3, 5, 6, 7, 9 and 10.

Captions carry artist, title and date for every plate, and all four plates reuse
works already listed in `assets/art.json` (public domain / CC0 only). No new
download, no new licence question.

### 7.1 Collage format, reference page, and the licence line

The referenced page (`heyaristotle/index.html`) builds each audience card as a
stack of absolutely-positioned transparent PNGs: a torn paper sheet, a map
fragment, a cut-out figure, gold stars, a hand-drawn red tick, a stack of books,
a bulb, an A+ scribble.

**The format is borrowed; the files are not.** Its PNGs are stock photographs of
objects (bell, compass, teapot, apples, envelope) and cut-outs whose licence is
nowhere in the bundle — no manifest, no source page, no rights statement. The
user's own condition was "as long as it's open licensed", so shipping them would
break it.

What is used instead:

| Layer in the reference | What this page ships |
| --- | --- |
| paper sheet | CSS gradient + inset rule, no file |
| cut-out figure | `assets/reference-style/{children-tree,woman-girl,reading-group}.jpg` — public-domain book illustrations, white dropped with `mix-blend-mode:multiply` |
| small object | `idea-patent`, `school-1904`, `books-plate` — same manifest |
| gold star | CSS `clip-path` star with a two-stop gradient |
| hand-drawn tick | inline SVG path, `stroke-linecap:round`, `rotate(-6deg)`, `--clay-500` |
| tape | `::before` strip, no file |

The card is a two-column grid (`minmax(0,1fr) 128px`), figure pinned bottom-right
inside the card, so nothing is bled outside and no text runs under the artwork.
A first pass placed the figure with `right:-14px; bottom:-18px`; the balance audit
caught both the text collision and the horizontal spill.

### 7.2 Licence gate

```bash
python harness/scripts/check_asset_licences.py
```

Every `assets/art/*` and `assets/reference-style/*` reference in `index.html` must
appear in the matching manifest with an explicit public-domain / CC0 licence, a
`copyrighted_flag` that is not true, and a source page; the file must exist on
disk, and none of the five reference-bundle names may be present. 14 references
checked, 0 refused.



