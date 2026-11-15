# Luminfest Learning Harness — Closed Alpha

Internal, **non-commercial** testing program. This folder is the single entry point for
internal testers and the operator standing up the cohort.

## What you received

- `../outputs/internal-distribution/Luminfest Learning Harness-internal-alpha.zip` — the
  ad-hoc-signed macOS app (**not notarized**; bypass Gatekeeper once, see INSTALL.md).
- `../outputs/internal-distribution/STAGING-MARKER.md` — the UNSIGNED / INTERNAL-ALPHA-ONLY stamp.
- `../outputs/internal-distribution/sha256.txt` — integrity hash of the zip.
- `../scripts/package_internal.sh` — rebuilds the archive from a release build (operator use).

## Read in this order

1. **ADMISSION.md** — you must be on **macOS 14+ / Apple Silicon**.
2. **INTERNAL_ALPHA_AGREEMENT.md** — the non-commercial testing terms (sign it).
3. **CONFIG.md** — how the operator stands up the backend + LLM provider + alpha-free flag.
4. **INSTALL.md** — install the app and bypass Gatekeeper.

## Hard constraints

- **Native app:** macOS 14 (Sonoma) or newer on Apple Silicon (M1/M2/M3/M4) only. Intel Macs
  and older macOS are not supported by the native build. The **Web workbench** is the
  cross-platform fallback.
- **Non-commercial only.** PhET simulations are CC BY-NC; this build may not be used
  commercially. Khan / MIT OCW carry their own non-commercial constraints.
- **Not shippable.** No Developer-ID codesign, no notarization, no public release.
- **All Plus capabilities are free for the cohort** (`HARNESS_ALPHA_FREE=1`) — see CONFIG.md.
  This makes the capability matrix match what the routes actually allow, closing the
  "withheld but usable" contradiction found in the readiness audit.
