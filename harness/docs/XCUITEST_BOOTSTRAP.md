# XCUITest / native test bootstrap — capability boundary and CI steps

Read-only investigation of the existing targets and CI. **No native test file, runner,
project file or CI config was edited by this work.** Where something could not be run, it is
recorded as "documented, not executed" rather than as a pass.

## 1. Targets that exist

| Target | Location | What it is | Run today? |
| --- | --- | --- | --- |
| SwiftPM unit tests | `native/Package.swift` declares `.testTarget(name: "LearningHarnessTests", dependencies: ["LearningHarness"])`; 19 Swift files under `native/Tests/LearningHarnessTests/` (incl. `BackendLauncherTests.swift`, `InteractiveEvidenceTests.swift`, `SessionVaultTests.swift`) | XCTest **unit** tests. `BackendLauncherTests` parses `backend/app/db.py` to catch schema-version drift. | Buildable via SwiftPM; not executed in this audit. |
| XCUITest UI target | `ui-tests/NativeHarnessUI.xcodeproj`, scheme `NativeHarnessUI`, sources `ui-tests/Tests/NativeWorkflowTests.swift` + `RunnerConfiguration.swift`, `Application-Info.plist`, `generate_project.py` | A real XCUIApplication test that drives the app with accessibility identifiers. | **Cannot bootstrap on this machine** (see §2). |
| AX journey driver (not XCTest) | `scripts/native_qa.py` — docstring: "Run an already-built native app against an owned, isolated backend; never build or use XCTest." Summary driver: "in-process native AppKit accessibility (no external XCTest)". | Drives the ten golden journeys through a real window; this is what CI layer 3 actually executes. | Executed in CI; not re-run here. |

CI `layer-3-native` (`.github/workflows/quality.yml:185-218`, at the git root one level above
`harness/`) runs on `macos-14`, builds with `cd harness/native && swift build
--disable-sandbox`, then runs `python scripts/native_qa.py --journeys --app
native/.build/debug/LearningHarness --backend-python "$(command -v python)" --port 8891
--output "$RUNNER_TEMP/journeys" --timeout 900`. It uploads exactly three fixed evidence
files (`journeys.json`, `run-summary.json`, `backend-evidence.json`) with `if: always()`,
`retention-days: 7` and `if-no-files-found: error`. The workflow header notes that a runner
without a window server reports `blocked` and fails the job — a skipped UI test is not a
pass.

## 2. Current capability boundary

This environment cannot reliably boot XCUITest; the tree records the reason rather than
working around it (`docs/QUALITY_PROGRAM.md:99-113`):

- the XCTest runner is ad-hoc signed (`CODE_SIGN_IDENTITY = "-"`), and there is **no Apple
  Development identity** here (`security find-identity -v -p codesigning` → *0 valid
  identities*);
- Xcode 26 injects `com.apple.security.app-sandbox` into the UI-test runner regardless of
  `ENABLE_APP_SANDBOX = NO`;
- a sandboxed ad-hoc app cannot be granted a container, so `libsecinit` traps in
  `_libsecinit_appsandbox` during dyld initialisers — *"The test runner exited with code 1
  before establishing connection."*
- re-signing the runner without the sandbox entitlement moved the failure to a silent exit
  1, so re-signing alone is not a fix.

`docs/lesson-procedure.md:403` likewise states the release binary builds but the XCTest
suite is verified by review plus the backend suite. I did **not** attempt `xcodebuild test`,
provision a signing identity, or boot a Simulator here; that is "documented, not executed",
not a claim that XCUITest is green. Layer 3 remains the in-process AX driver, which the
quality program calls a genuine first-person test of the same application.

## 3. Exact steps required to run XCUITest on a provisioned runner

1. Use a macOS runner (e.g. `macos-14`) with Xcode installed and a window server. Confirm a
   usable signing identity: `security find-identity -v -p codesigning` must list at least
   one valid Apple Development identity (not the current 0). Import the certificate into a
   temporary keychain via CI secrets; never commit the identity or key.
2. Resolve the Xcode 26 sandbox injection for the UI-test runner so `libsecinit` no longer
   traps — i.e. provide a properly signed, non-sandboxed runner. Ad-hoc signing plus an
   injected app-sandbox entitlement is the known-broken combination.
3. Prepare a backend Python for the runner (the repository expects `harness/ui-tests/.venv`
   with backend dependencies, or pass `--backend-python`), then from the git root run:

   ```sh
   python3 scripts/ui_test.py --backend-python <path-to-venv-python>
   # inspect only:  python3 scripts/ui_test.py --generate-only
   ```

   `scripts/ui_test.py` writes `ui-tests/Tests/RunnerConfiguration.swift` with the endpoint
   and output dir, generates the xcodeproj via `ui-tests/generate_project.py`, starts an
   isolated backend (`HARNESS_ENV=test`, a fresh `HARNESS_DATA_DIR`, a random
   `HARNESS_SECRET`, loopback host), waits for `/api/v1/health` `ready`, then invokes:

   ```
   xcodebuild test -project ui-tests/NativeHarnessUI.xcodeproj \
     -scheme NativeHarnessUI -destination platform=macOS \
     -derivedDataPath ui-tests/DerivedData \
     -resultBundlePath outputs/ui/NativeWorkflow*.xcresult \
     -parallel-testing-enabled NO
   ```

   The script's exit code is xcodebuild's; it also runs `xcrun xcresulttool get
   test-results summary` and writes `outputs/ui/run-summary.json` plus
   `xcresult-summary.json`, `workflow-events.json`, `backend.log` and `xcodebuild.log`.
4. Add a CI job (separate from `layer-3-native`, or a gated variant of it) that performs
   steps 1-3, fails on a nonzero `xcodebuild` exit, and uploads `run-summary.json`,
   `xcresult-summary.json`, `workflow-events.json` and `xcodebuild.log` as evidence with a
   bounded retention. A `gap`/`blocked` result must remain visible, never folded into a
   pass (`docs/QUALITY_PROGRAM.md`).
5. Keep the existing `swift build --disable-sandbox` unit-test build and the AX journey job
   as separate layers; XCUITest does not replace them.

## 4. What was and was not fixed here

- **Fixed:** nothing in native test files, `ui-tests/`, `scripts/ui_test.py`,
  `scripts/native_qa.py`, `native/Package.swift` or CI. No signing identity, keychain or
  simulator was provisioned.
- **Added:** this document only, which records the boundary and the exact operator/CI steps.
- **Verified by reading:** the two distinct drivers (real XCUITest vs in-process AX), the
  19 SwiftPM unit-test files, the four blocker facts in `docs/QUALITY_PROGRAM.md`, and the
  exact CI `layer-3-native` commands and evidence list.
- **Not executed here:** `xcodebuild test`, Simulator boot, and the ten journeys. No claim
  of XCUITest coverage is made.
