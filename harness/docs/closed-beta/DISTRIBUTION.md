# Distribution — another device, other OS, remote updates

## Verified release artifacts

Measured on 2026-11-15; the hashes match `outputs/luminest-download-site/download-manifest.json`
byte-for-byte.

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `outputs/Luminest-arm64.dmg` | 96,483,349 | `050f5db45cbd3bb31a62e2f030ef25362e37cb6cd11d8093eb7065d7ef318838` |
| `outputs/Luminest-arm64.zip` | 91,942,918 | `d435e68f435604fcff243e105f600229c253be4cb0820c418f89bd05e0b6c284` |

`outputs/Luminest.app/Contents/Resources/backend/LuminfestBackend/` confirms the
Python backend is **inside** the app. That is what makes the archive usable on
another Mac without installing or starting a separate server.
`Info.plist`: `CFBundleDisplayName`/`CFBundleName` = `Luminest`,
`CFBundleShortVersionString` = `1.4.0`, `LSMinimumSystemVersion` = `14.0`.

`harness/scripts/package_beta.py` refuses to assemble the site if a size or
checksum drifts — it hashes the real files rather than copying transcribed
numbers.

## "Downloadable and usable on another device"

- The control server gates `/downloads/*` **server-side**: no valid beta token →
  403, even though the file exists on disk. The landing page appends
  `?token=…` only after a successful redeem. A `demo`-scope token cannot
  download (tested).
- `INSTALL.txt` covers checksum verification, moving to Applications, and the
  one-app Gatekeeper approval (ad-hoc signed, **not** notarized — no global
  Gatekeeper disable).
- No model API key is bundled; without a provider the app serves retrieved
  curriculum and says why.

## Other OS / other macOS versions — honest answer

| Target | Feasible? | Path |
| --- | --- | --- |
| macOS 14+ / Apple Silicon | **Yes** | native DMG/ZIP |
| iPad / iPadOS | **Not as a `.app`** — different OS, and the embedded PyInstaller runtime is arm64 macOS | **web version** `/app/` as an installable PWA (`manifest.webmanifest` + service worker, "Add to Home Screen") |
| Intel Mac (x86_64) | **Not with this artifact** — SwiftPM release binary is arm64 and the bundled Python runtime is arm64-only | web version |
| macOS 13 or older | **Not with this artifact** — `Package.swift` declares `.macOS(.v14)` and `LSMinimumSystemVersion=14.0` | web version |
| Windows / Linux / Chromebook | **Not as a `.app`** | web version, no install |

This is not a downgrade of the request: the web version is a **real** client
(`harness/webapp`, React + Vite + TS) talking to the same FastAPI backend via
the control server's `/api/v1` reverse proxy. It covers register/login,
capabilities, curriculum, course creation, lesson viewer, quiz and settings.
What it does not cover is the native-only surfaces (Interactive Board drawing,
presentations, live voice) — those are additive, not stubbed fakes.

**Why no universal binary / older-macOS native build — measured, not assumed:**
A bounded experiment changed `Package.swift` to `.macOS(.v13)` and ran
`swift build -c release --disable-sandbox`. It **failed with 9 compile errors**:

| File | macOS 14-only API |
| --- | --- |
| `StateViews.swift:240` | `symbolEffect(_:options:isActive:)`, `.pulse` |
| `Studio.swift:103,104,291,447` | `onChange(of:initial:_:)` |
| `TodayKnowledge.swift:683` | `onChange(of:initial:_:)` |

`Package.swift` was restored to `.macOS(.v14)` immediately after the experiment
(verified). Supporting macOS 13 natively therefore requires rewriting those call
sites, a second x86_64 SwiftPM build, **and** a second PyInstaller backend build
with matching architectures, plus editing `LSMinimumSystemVersion` in the shipped
`Info.plist`. That is a separate release-engineering task. No partially working
binary is shipped as if it worked; the web version is the real path today.

## Remote updates in the bundle

Two layers, because the 1.4.0 artifact predates the Swift checker:

1. **Server / manifest** — `harness/beta_control/server.py` serves
   `GET /api/updates/manifest.json` and accepts `POST /api/updates/manifest`
   (admin token required). Every artifact must carry `sha256`; a publish without
   one returns 422. `package_beta.py` stamps `updates/manifest.json`,
   `SHA256SUMS.txt` and `download-manifest.json` with measured hashes.
2. **Client** —
   - `harness/native/Sources/LearningHarness/BetaUpdate.swift` (compiled into
     future builds): reads the manifest on launch (`BetaUpdate.checkOnLaunch()`
     from `LuminfestApp.swift`), records the verdict, and offers a
     `Learning → Check for updates` menu action. It resolves the URL from
     `Info.plist` `LuminestUpdateManifestURL` or UserDefaults
     `luminest.updateManifestURL`, accepts HTTPS (plus loopback HTTP), and
     **never self-installs**. `verifyDownloadedArchive(at:expectedSHA256:)`
     uses CryptoKit SHA256 for a user-downloaded archive.
   - `outputs/closed-beta-site/updates/check_update.py` works with the
     **already-shipped** 1.4.0 bundle today: reads `CFBundleShortVersionString`
     from `/Applications/Luminest.app`, fetches the manifest, and can verify a
     downloaded archive's sha256. Stdlib only, no install.

```bash
python3 outputs/closed-beta-site/updates/check_update.py \
  --server https://<link> --app /Applications/Luminest.app \
  --verify ~/Downloads/Luminest-arm64.zip
```

## Known release gates (unchanged)

Ad-hoc signed, not notarized; no Developer ID; PhET CC BY-NC requires a separate
licence for commercial use. These block **public distribution**, not a controlled
closed beta. Billing is not part of this release.
