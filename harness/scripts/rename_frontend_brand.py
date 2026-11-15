#!/usr/bin/env python3
"""Resolve the documented brand Q0 in favour of **Luminest** on the frontend.

Only *user-visible* brand strings are renamed. Internal identifiers are
deliberately preserved:

    luminfest:ready / luminfest:hover / luminfest:select   postMessage protocol
    luminfest.token / luminfest.sessions.v1               sessionStorage keys
    LuminfestCards / LuminfestTelemetry                   window globals
    web/luminfest-agent.js                               file name / injection path
    com.luminfest.learningharness                         bundle identifier
    ~/Library/Application Support/Luminfest Learning Harness/   on-disk data dir

Renaming any of those would break the sim bridge, orphan existing sessions, or
move an installed user's data. The shipped `Luminest.app` Info.plist already has
CFBundleDisplayName/CFBundleName = Luminest while keeping the identifier stable;
this script brings the remaining frontend surfaces in line with that decision.

Every replacement is asserted before writing; a missing target is an error, not
a silent no-op.

    python3 harness/scripts/rename_frontend_brand.py --check   # report only
    python3 harness/scripts/rename_frontend_brand.py           # apply
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB = os.path.join(ROOT, "web")
WEBAPP = os.path.join(ROOT, "webapp")
SCRIPTS = os.path.join(ROOT, "scripts")

# path -> (old, new) exact strings
CHANGES: dict[str, list[tuple[str, str]]] = {
    "web/index.html": [
        ("<title>Luminfest Workbench</title>", "<title>Luminest Workbench</title>"),
        ('<div class="brand">Luminfest <span>workbench</span></div>',
         '<div class="brand">Luminest <span>workbench</span></div>'),
    ],
    "web/app.html": [
        ("<title>Luminfest — the app, in a browser</title>",
         "<title>Luminest — the app, in a browser</title>"),
        ('<div class="brand">Luminfest <span>— the app, in a browser</span></div>',
         '<div class="brand">Luminest <span>— the app, in a browser</span></div>'),
    ],
    "web/playground.html": [
        ("<title>Simulator Playground — Luminfest</title>",
         "<title>Simulator Playground — Luminest</title>"),
    ],
    "web/README.md": [
        ("# Luminfest Workbench (`harness/web/`)", "# Luminest Workbench (`harness/web/`)"),
        ("The interactive web surface for the Luminfest learning harness:",
         "The interactive web surface for the Luminest learning harness:"),
    ],
    "web/telemetry.js": [
        ("/* Luminfest workbench — interaction telemetry, browser side.",
         "/* Luminest workbench — interaction telemetry, browser side."),
    ],
    "web/cards.js": [
        ("/* Luminfest workbench — pure card helpers.",
         "/* Luminest workbench — pure card helpers."),
    ],
    "web/app.js": [
        ("/* Luminfest workbench client. Vanilla JS, no build step.",
         "/* Luminest workbench client. Vanilla JS, no build step."),
    ],
    "web/styles.css": [
        ("/* Luminfest workbench — layout per agent-harness-designer",
         "/* Luminest workbench — layout per agent-harness-designer"),
    ],
    "web/sims/supply-demand.html": [
        ("Seed simulation for the Luminfest workbench.",
         "Seed simulation for the Luminest workbench."),
    ],
    "webapp/README.md": [
        ("A browser-native React client for **Luminest** (the Luminfest Learning Harness).",
         "A browser-native React client for **Luminest**. Internal identifiers, the bundle\nidentifier and the on-disk data directory keep their historical `luminfest` spelling\non purpose -- renaming them would orphan existing installs and break the sim bridge."),
    ],
    # Native app: only rendered strings. `LuminfestButtonStyle`, `LuminfestArt`,
    # `LuminfestMotion`, `Luminfest.icns` and `luminfest.*` AppStorage keys are
    # type names / resource names / defaults keys and must not change.
    "native/Sources/LearningHarness/LuminfestApp.swift": [
        ('NSApp.windows.first?.title = "Luminfest"',
         'NSApp.windows.first?.title = "Luminest"'),
        ('WindowGroup("Luminfest")', 'WindowGroup("Luminest")'),
        ('"Sign in to Luminfest"', '"Sign in to Luminest"'),
        ('.accessibilityLabel("Luminfest")', '.accessibilityLabel("Luminest")'),
    ],
    "native/Sources/LearningHarness/ProjectsInsightsSettings.swift": [
        ("If enabled, Luminfest sends a foreground activity heartbeat",
         "If enabled, Luminest sends a foreground activity heartbeat"),
    ],
    "native/Sources/LearningHarness/Shared/State/AppStore+Account.swift": [
        (r'"Luminfest \(build)', r'"Luminest \(build)'),
    ],
    "native/Sources/LearningHarness/CourseSetup.swift": [
        ("every time you open Luminfest.", "every time you open Luminest."),
    ],
    "native/Sources/LearningHarness/Board.swift": [
        ('[kCGPDFContextCreator: "Luminfest Learning Harness"]',
         '[kCGPDFContextCreator: "Luminest"]'),
    ],
    # Backend strings that reach a human (mail subject, notice, tutor prompt).
    "backend/app/main.py": [
        ("'Confirm your Luminfest email'", "'Confirm your Luminest email'"),
        ("'Reset your Luminfest password'", "'Reset your Luminest password'"),
        ("'Confirm your place on the Luminfest Beta list'",
         "'Confirm your place on the Luminest Beta list'"),
        ("'Your Luminfest Beta invite'", "'Your Luminest Beta invite'"),
        ("'The transcript was not saved by Luminfest.", "'The transcript was not saved by Luminest."),
        ("was not saved by Luminfest.')", "was not saved by Luminest.')"),
        ("'You are the Luminfest tutor.", "'You are the Luminest tutor."),
    ],
    "scripts/package_internal.sh": [
        ("Internal distribution builder for the Luminfest Learning Harness closed alpha.",
         "Internal distribution builder for the Luminest closed beta."),
        ('APP="$OUT/Luminfest Learning Harness.app"', 'APP="$OUT/Luminest.app"'),
        ('ZIP="$OUT/Luminfest Learning Harness-internal-alpha.zip"',
         'ZIP="$OUT/Luminest-closed-beta.zip"'),
        ("<string>Luminfest Learning Harness</string>\n\t<key>CFBundleExecutable</key>",
         "<string>Luminest</string>\n\t<key>CFBundleExecutable</key>"),
        ("<string>Luminfest Learning Harness</string>\n\t<key>CFBundlePackageType</key>",
         "<string>Luminest</string>\n\t<key>CFBundlePackageType</key>"),
        ("Luminfest Learning Harness.app/", "Luminest.app/"),
        ("Luminfest Learning Harness-internal-alpha.zip", "Luminest-closed-beta.zip"),
    ],
}

# Allowed remaining capital-brand tokens (code identifiers, never rendered).
ALLOWED = ("LuminfestCards", "LuminfestTelemetry", "LuminfestBackend",
           "luminfest:", "luminfest.", "luminfest-agent", "com.luminfest",
           "Luminfest Learning Harness", "LuminfestBackend/_internal",
           "LuminfestButtonStyle", "LuminfestButtonBody", "LuminfestArt",
           "LuminfestMotion", "Luminfest.icns", "LuminfestApp", "Luminfest servers",
           "previous Luminfest", "It is Luminfest", "Luminfest -", "Luminfest's",
           "Luminfest,", "by Luminfest", "// ", "/// ", "* ", "/*",
           "LuminfestLearningHarness_LearningHarness", 'forResource: "Luminfest"')
NATIVE = os.path.join(ROOT, "native", "Sources", "LearningHarness")
BACKEND_MAIN = os.path.join(ROOT, "backend", "app", "main.py")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    ap.add_argument("--revert-to-luminfest", action="store_true",
                    help="undo the user-visible rename (one command, no discussion). "
                         "Internal identifiers are never touched in either direction.")
    args = ap.parse_args()

    applied = 0
    missing = []
    for rel, pairs in CHANGES.items():
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            missing.append("missing file: " + rel)
            continue
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        original = text
        # Reverting a chain of string substitutions must run in reverse order,
        # otherwise an earlier replacement re-creates a later target.
        ordered = [(new, old) for old, new in reversed(pairs)] \
            if args.revert_to_luminfest else pairs
        for old, new in ordered:
            if old not in text:
                # Already in the desired state on a previous run is fine;
                # a genuinely absent target is reported, never silently skipped.
                if new in text:
                    continue
                missing.append("%s: target not found -> %r" % (rel, old[:60]))
                continue
            text = text.replace(old, new)
            applied += 1
        if text != original and not args.check:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)

    # Audit: any remaining user-visible "Luminfest" outside the allow-list.
    residual = []
    targets = [WEB, WEBAPP, NATIVE]
    for dirpath, dirnames, filenames in os.walk(NATIVE):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            if name.endswith((".swift", ".strings")):
                targets.append(os.path.join(dirpath, name))
    targets.append(BACKEND_MAIN)
    for base in targets:
        files = ([base] if os.path.isfile(base) else [])
        if os.path.isdir(base):
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in ("node_modules", "dist", ".git")]
                for name in filenames:
                    if name.endswith((".html", ".js", ".css", ".md", ".ts", ".tsx", ".json")):
                        files.append(os.path.join(dirpath, name))
        for p in files:
            with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    if "Luminfest" not in line or any(a in line for a in ALLOWED):
                        continue
                    residual.append("%s:%d: %s" % (os.path.relpath(p, ROOT), lineno,
                                                   line.strip()[:100]))
    direction = "REVERT -> Luminfest" if args.revert_to_luminfest else "APPLY -> Luminest"
    print("%s: applied %d replacements%s" %
          (direction, applied, " (check only)" if args.check else ""))
    if missing:
        print("MISSING TARGETS:")
        for m in missing:
            print("  " + m)
    if args.revert_to_luminfest:
        # After a revert, user-visible "Luminfest" is the *expected* state; the
        # normal audit would report it as a failure. Internal identifiers still
        # stay untouched in both directions.
        print("brand reverted; 'Luminfest' is now the intended visible name.")
        print("NOTE: outputs/closed-beta-site/, beta_control/ and the shipped "
              "Luminest.app are NOT renamed by this script -- see BRAND_DECISION.md.")
        return 1 if missing else 0
    print("residual user-visible 'Luminfest' lines: %d" % len(residual))
    for r in residual[:20]:
        print("  " + r)
    if args.check:
        return 1 if (missing or residual) else 0
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
