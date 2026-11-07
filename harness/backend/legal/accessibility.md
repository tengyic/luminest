# Accessibility Statement

**Version:** 2026-11 · **Effective:** 1 November 2026 · **Revised:** 7 November 2026

We want Luminest to be usable by as many people as possible, including learners who use a
screen reader, keyboard only, high contrast, larger text, or reduced motion.

## Our target

We aim to meet **WCAG 2.2 Level AA** for the application. This is a target we are working
towards, not a certification we hold. Where we fall short we would rather say so than
overclaim.

## What we have done

- **Keyboard reachable.** Every primary control is reachable and operable without a mouse;
  the main sections have keyboard shortcuts (⌘1…⌘8) and named accessibility identifiers.
- **Screen reader labelling.** Interactive controls carry labels and identifiers so assistive
  technology announces what they do.
- **No colour-only meaning.** Status is conveyed with text and icons, not colour alone.
- **Respectful motion.** Decorative motion is confined to onboarding and celebration moments;
  content screens do not animate gratuitously.
- **Readable typography.** Body text uses a legible size and line spacing; system text scaling
  is honoured.
- **Text alternatives.** Figures and diagrams ship with text descriptions.
- **Sound is never the only signal.** A correct answer, a streak and a celebration each have a
  visible counterpart; muting the app removes nothing you need.
- **Light and dark appearance.** The interface ships a dark theme built from the same palette
  at lower luminance rather than an inversion, plus a higher-contrast variant of both. They
  follow the macOS setting. The app reads that setting and does not offer a separate switch:
  an in-app imitation of a system accessibility preference is worse than honouring the real one.
- **Interface language.** English and Simplified Chinese, switchable in *Settings → Language*
  and applied immediately, with no relaunch. Dates, numbers and measurements follow the same
  choice, so a Chinese screen does not keep English dates.
- **Text scaling.** Text is sized from semantic text styles rather than fixed point sizes, so it
  grows with the system text size and containers reflow instead of clipping.
- **Honest failure states.** A server that is not running, one that is slow, an expired session
  and a request the server refused (HTTP 422) are reported as four different things. A refused
  request names the field the server objected to; it is never described as a connection problem.

## Known limitations

- **The language switch does not yet cover every screen.** Navigation, settings and the failure
  states above are bilingual. Several deeper surfaces — the Studio, the board and deck editors,
  the lesson procedure and the companion — still ship English copy while their translations are
  being written. They are readable, not translated, and we would rather say so than imply full
  coverage.
- **Contrast is measured, not audited.** Body-text pairs were measured against WCAG 2.2
  relative-luminance ratios in all four appearance variants (light, dark, and each at increased
  contrast); every pair clears 4.5:1. The weakest is tertiary text at 5.51:1, which was 2.93:1
  before this revision. Non-text contrast and focus-indicator contrast have not been measured
  the same way.
- **Increase Contrast and Reduce Motion follow macOS.** The app honours both settings but does
  not provide its own overrides, so a per-app preference that differs from the system one is
  not available.
- Some chart elements rely on the platform's default accessibility representation and have not
  been individually tuned.
- **No independent audit yet.** We have not commissioned a third-party accessibility audit, and
  the success-criterion-by-criterion review against WCAG 2.2 AA is incomplete. The criteria we
  have measured are the ones described above; the rest are neither claimed nor certified.

## Feedback

If you hit a barrier, use *Settings → Report a problem* and choose *Accessibility*. Please
describe the task you were trying to complete and the assistive technology you use — that
detail is what makes a report fixable.

We aim to respond within **ten business days** and will publish what we fixed in the release
notes. If a barrier makes the app unusable for you, say so in the first line of the report and
it will be treated as a defect rather than a feature request.
