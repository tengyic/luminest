#!/usr/bin/env python3
"""Assemble the Luminest closed-beta distribution site.

Verifies the real release artifacts, copies them (plus the browser build and the
beta control server) into one self-contained directory, and stamps a remote
update manifest with the *measured* sha256 of each artifact.

    python3 harness/scripts/package_beta.py
    python3 harness/scripts/package_beta.py --no-artifacts   # small upload, links stay relative

Nothing is invented: if a checksum disagrees with the recorded manifest, this
script raises instead of shipping a package nobody can verify.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HARNESS = os.path.join(WORKSPACE, "harness")
OUTPUTS = os.path.join(WORKSPACE, "outputs")
SITE = os.path.join(OUTPUTS, "closed-beta-site")
WEBAPP_DIST = os.path.join(HARNESS, "webapp", "dist")
BETA_SERVER = os.path.join(HARNESS, "beta_control", "server.py")
VERSION = "1.4.0"

ARTIFACTS = [
    ("Luminest-arm64.dmg", "050f5db45cbd3bb31a62e2f030ef25362e37cb6cd11d8093eb7065d7ef318838",
     96483349, "macOS disk image"),
    ("Luminest-arm64.zip", "d435e68f435604fcff243e105f600229c253be4cb0820c418f89bd05e0b6c284",
     91942918, "macOS app archive"),
]

DEMO_SEED = {
    "_comment": "Public demo code. Unlocks the browser demo only; downloads need an operator-issued beta code.",
    "codes": [
        {"code": "LUMINEST-DEMO-2026", "scope": "demo", "max_uses": 500,
         "note": "public landing-page demo, no download access"}
    ],
}

# The shipped site must never carry a third-party product or philosopher name.
# This is a brand/compliance guard, not a style preference: a rebuild that
# reintroduces one of these strings fails the package instead of shipping.
BANNED_BRAND_TERMS = ("aristotle", "heysristotle", "socratic")
SHIPPED_TEXT_SUFFIXES = (".html", ".htm", ".txt", ".json", ".js", ".css",
                         ".py", ".webmanifest", ".svg", ".md")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def copy_artifacts(no_artifacts: bool) -> list[dict]:
    dest = os.path.join(SITE, "downloads")
    os.makedirs(dest, exist_ok=True)
    rows = []
    for name, expected, expected_size, label in ARTIFACTS:
        src = os.path.join(OUTPUTS, name)
        ensure(os.path.isfile(src), "missing release artifact: " + src)
        actual_size = os.path.getsize(src)
        actual_sha = sha256(src)
        ensure(actual_size == expected_size,
               "%s size drift: %s != %s" % (name, actual_size, expected_size))
        ensure(actual_sha == expected,
               "%s checksum drift: %s != %s" % (name, actual_sha, expected))
        if not no_artifacts:
            shutil.copy2(src, os.path.join(dest, name))
        rows.append({
            "name": name,
            "label": label,
            "url": "downloads/" + name,
            "bytes": actual_size,
            "sha256": actual_sha,
            "present_on_site": not no_artifacts,
        })
        print("  verified %-24s %d bytes  sha256=%s…" % (name, actual_size, actual_sha[:12]))
    return rows


def copy_webapp() -> None:
    ensure(os.path.isfile(os.path.join(WEBAPP_DIST, "index.html")),
           "webapp not built: run `npm run build` in harness/webapp first")
    dest = os.path.join(SITE, "app")
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(WEBAPP_DIST, dest)
    print("  browser build -> app/ (%d files)" %
          sum(len(f) for _, _, f in os.walk(dest)))


def copy_static() -> None:
    assets = [
        (os.path.join(OUTPUTS, "luminfest-site", "favicon.svg"),
         os.path.join(SITE, "favicon.svg")),
        (os.path.join(OUTPUTS, "luminest-beta", "luminest-full.png"),
         os.path.join(SITE, "assets", "luminest-full.png")),
    ]
    for src, dst in assets:
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            print("  asset -> %s" % os.path.relpath(dst, SITE))
    shutil.copy2(BETA_SERVER, os.path.join(SITE, "server.py"))
    print("  control server -> server.py")


def write_manifest(rows: list[dict]) -> None:
    updates = os.path.join(SITE, "updates")
    os.makedirs(updates, exist_ok=True)
    body = {
        "product": "Luminest",
        "channel": "closed-beta",
        "version": VERSION,
        "published_at": int(time.time()),
        "min_macos": "14.0",
        "platform": "macOS 14+ / Apple Silicon (arm64)",
        "release_notes": "Closed beta 1. Share-code access, no billing, remote update manifest.",
        "artifacts": [{"url": r["url"], "sha256": r["sha256"],
                       "bytes": r["bytes"], "name": r["name"]} for r in rows],
        "web_version_url": "/app/",
        "check_endpoint": "/api/updates/manifest.json",
    }
    with open(os.path.join(updates, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(SITE, "download-manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "product": "Luminest",
            "bundle_name": "Luminest",
            "version": VERSION,
            "platform": "macOS 14+ / Apple Silicon (arm64)",
            "status": "closed-beta",
            "signed": "ad-hoc",
            "notarized": False,
            "artifacts": {r["name"]: {"file": r["url"], "bytes": r["bytes"],
                                      "sha256": r["sha256"]} for r in rows},
            "verification": {"bundle_smoke": True, "backend_smoke": True,
                             "public_release_ready": False},
        }, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(SITE, "SHA256SUMS.txt"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write("%s  %s\n" % (r["sha256"], r["url"]))
    with open(os.path.join(SITE, "seed_codes.json"), "w", encoding="utf-8") as fh:
        json.dump(DEMO_SEED, fh, indent=2)
        fh.write("\n")
    print("  updates/manifest.json + download-manifest.json + SHA256SUMS.txt + seed_codes.json")


def assert_no_banned_brand() -> None:
    """Fail the build if a banned brand string leaked into any shipped text file."""
    hits: list[str] = []
    for root, dirs, files in os.walk(SITE):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if not name.lower().endswith(SHIPPED_TEXT_SUFFIXES):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        low = line.lower()
                        for term in BANNED_BRAND_TERMS:
                            if term in low:
                                hits.append("%s:%d -> %r" % (
                                    os.path.relpath(path, SITE), lineno, term))
            except (UnicodeDecodeError, OSError):
                continue
    ensure(not hits,
           "shipped site contains banned brand strings: " + "; ".join(hits[:10]))
    print("  brand guard -> 0 banned strings in shipped site text")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-artifacts", action="store_true",
                    help="validate but do not copy the large dmg/zip (small publish)")
    args = ap.parse_args()
    os.makedirs(SITE, exist_ok=True)
    print("Assembling Luminest closed-beta site: %s" % SITE)
    rows = copy_artifacts(args.no_artifacts)
    copy_webapp()
    copy_static()
    write_manifest(rows)
    assert_no_banned_brand()
    print("Done. Version %s, %d verified artifacts." % (VERSION, len(rows)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print("FAILED: %s" % exc, file=sys.stderr)
        sys.exit(1)
