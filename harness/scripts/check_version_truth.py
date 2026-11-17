#!/usr/bin/env python3
"""Check version truth across the legacy harness sources. READ-ONLY.

There is no single version number in this tree. Three namespaces are deliberately
distinct, and this checker encodes that distinction as an allowlist rather than
pretending the numbers are the same:

1. SCHEMA VERSION (structurally coupled): backend/app/db.py:75 and
   native/Sources/LearningHarness/BackendLauncher.swift:100 must both declare 13,
   because BackendLauncherTests parses db.py and the packager refuses a mismatch.
2. MARKETING VERSION (the shipped 1.4.0 line): scripts/package_beta.py VERSION and
   the CFBundleShortVersionString recorded for the closed-beta artifact. A beta
   prerelease (1.4.0-beta.1) is an allowlisted child of that line, not drift.
3. PACKAGING / ARTIFACT-RECORD VERSIONS: release_kit.py examples (1.1.16),
   DISTRIBUTION.md's observed artifact record (1.2.0), and package.py's dev-only
   --version default (1.0.0). These are historically distinct from the marketing
   version; they are checked against explicit allowlists, NOT against 1.4.0.

Exit status: 0 when every source agrees with its namespace, 1 on any drift,
missing source, or unparseable value. The script never writes to any file.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # .../harness

# --- The single expected value in each coupled namespace. -------------------------
EXPECTED_SCHEMA_VERSION = 13
EXPECTED_MARKETING_VERSION = "1.4.0"

# --- Allowlists encoding the legitimate marketing/packaging distinction. ----------
# A beta build of the 1.4.0 marketing line is not a competing version; it is the
# same line with a prerelease suffix. beta_control is operator-controlled and is
# read here only (this checker never edits it).
BETA_PRERELEASE_PREFIX = EXPECTED_MARKETING_VERSION + "-"
# Historical/observed artifact records, not the current marketing version. These
# exist in release examples and the distribution guide; drift to any OTHER value
# is a finding, but their difference from 1.4.0 is by design.
ALLOWED_PACKAGING_RECORDS = frozenset({"1.1.16", "1.2.0"})
# package.py's --version default is a developer fallback, not a release truth.
ALLOWED_PACKAGING_DEFAULTS = frozenset({"1.0.0"})


class Result:
    def __init__(self, namespace: str, source: str, observed: str | None,
                 expected: str, ok: bool, note: str = "") -> None:
        self.namespace = namespace
        self.source = source
        self.observed = observed
        self.expected = expected
        self.ok = ok
        self.note = note


def _text(rel: str) -> str | None:
    path = ROOT / rel
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _capture(pattern: str, text: str | None, *, flags: int = 0) -> str | None:
    if text is None:
        return None
    match = re.search(pattern, text, flags)
    return match.group(1) if match else None


def check() -> list[Result]:
    results: list[Result] = []

    def add(namespace: str, rel: str, pattern: str, expected: str,
            predicate, *, flags: int = 0, note: str = "") -> None:
        observed = _capture(pattern, _text(rel), flags=flags)
        ok = observed is not None and predicate(observed)
        results.append(Result(namespace, rel, observed, expected, bool(ok), note))

    # 1. Schema version: two coupled sources, one expected value.
    add("schema", "backend/app/db.py",
        r"^\s*SCHEMA_VERSION\s*=\s*(\d+)\s*$",
        str(EXPECTED_SCHEMA_VERSION), lambda v: v == str(EXPECTED_SCHEMA_VERSION),
        flags=re.MULTILINE,
        note="authoritative; imported by init_db and packaging")
    add("schema", "native/Sources/LearningHarness/BackendLauncher.swift",
        r"expectedSchemaVersion\s*=\s*(\d+)",
        str(EXPECTED_SCHEMA_VERSION), lambda v: v == str(EXPECTED_SCHEMA_VERSION),
        note="compile-time expectation; BackendLauncherTests parses db.py")

    # 2. Marketing version. Cross-namespace equality to 1.4.0 is REQUIRED here;
    #    the packaging allowlists below are where a different number is legitimate.
    add("marketing", "scripts/package_beta.py",
        r"^\s*VERSION\s*=\s*[\"']([^\"']+)[\"']",
        EXPECTED_MARKETING_VERSION, lambda v: v == EXPECTED_MARKETING_VERSION,
        flags=re.MULTILINE, note="closed-beta bundle version")
    add("marketing", "docs/closed-beta/DISTRIBUTION.md",
        r"CFBundleShortVersionString`?\s*=\s*`?(\d+\.\d+\.\d+)",
        EXPECTED_MARKETING_VERSION, lambda v: v == EXPECTED_MARKETING_VERSION,
        note="recorded CFBundleShortVersionString for the shipped beta artifact")
    add("marketing/prerelease", "beta_control/server.py",
        r"LUMINEST_BETA_VERSION\"\s*,\s*[\"']([^\"']+)[\"']",
        "prefix " + BETA_PRERELEASE_PREFIX,
        lambda v: v.startswith(BETA_PRERELEASE_PREFIX),
        note="allowlisted prerelease of the marketing line; operator-owned")

    # 3. Packaging / artifact-record versions. Distinct from marketing by design.
    add("packaging/record", "DISTRIBUTION.md",
        r"records version\s+`?(\d+\.\d+\.\d+)`?",
        "one of " + ", ".join(sorted(ALLOWED_PACKAGING_RECORDS)),
        lambda v: v in ALLOWED_PACKAGING_RECORDS,
        note="observed historical artifact record, not the current version")
    add("packaging/record", "scripts/release_kit.py",
        r"--version\s+(\d+\.\d+\.\d+)",
        "one of " + ", ".join(sorted(ALLOWED_PACKAGING_RECORDS)),
        lambda v: v in ALLOWED_PACKAGING_RECORDS,
        note="CLI example version in the release kit")
    add("packaging/default", "scripts/package.py",
        r"--version\",\s*default=\"([^\"]+)\"",
        "one of " + ", ".join(sorted(ALLOWED_PACKAGING_DEFAULTS)),
        lambda v: v in ALLOWED_PACKAGING_DEFAULTS,
        note="dev-only CLI default, not a release truth")

    return results


def main() -> int:
    results = check()
    width = max(len(r.source) for r in results)
    print("Version truth check (read-only) — root:", ROOT)
    print(f"{'STATUS':<7} {'NAMESPACE':<22} {'SOURCE':<{width}}  OBSERVED / EXPECTED")
    print("-" * (7 + 1 + 22 + 1 + width + 2 + 40))
    for r in results:
        observed = r.observed if r.observed is not None else "<missing/unparseable>"
        print(f"{'OK' if r.ok else 'DRIFT':<7} {r.namespace:<22} {r.source:<{width}}  "
              f"{observed} / {r.expected}")
        if r.note and not r.ok:
            print(f"        note: {r.note}")
    failures = [r for r in results if not r.ok]
    print("-" * (7 + 1 + 22 + 1 + width + 2 + 40))
    if failures:
        print(f"FAIL: {len(failures)} version source(s) drifted. No files were modified.")
        for r in failures:
            print(f"  - {r.source}: observed {r.observed!r}, expected {r.expected}")
        return 1
    print(f"PASS: {len(results)} version sources consistent across their namespaces. "
          "No files were modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
