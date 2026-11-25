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
CAPTURES_SRC = os.path.join(OUTPUTS, "app-screenshots", "web")
ART_SRC = os.path.join(OUTPUTS, "art-sources")
ART_WEB = os.path.join(ART_SRC, "web")
REFERENCE_ASSETS_SRC = os.path.join(OUTPUTS, "reference-style-assets")
REFERENCE_ASSETS_WEB = os.path.join(REFERENCE_ASSETS_SRC, "web")
VERSION = "1.4.1"

# The published site uses one public port. server.py proxies /api/v1/* to a
# FastAPI backend on loopback:8766; publishing the site without starting that
# backend is exactly what produced 502 "backend unreachable" on the web client.
# This launcher starts both processes and gates the public port on backend
# health. Provider key comes from the operator's environment, never from a file
# under SITE, so nothing secret is published.
_START_SH = r'''#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
: "${PORT:=8788}"
: "${BACKEND_PORT:=8766}"
PYTHON=${PYTHON:-python3}
if [ -x "$HERE/venv/bin/python" ]; then PYTHON="$HERE/venv/bin/python"; fi
if [ ! -f "$HERE/backend/app/main.py" ]; then
  echo "start.sh: backend source missing at $HERE/backend" >&2; exit 1
fi
export HARNESS_ENV="${HARNESS_ENV:-production}"
export HARNESS_DATA_DIR="${HARNESS_DATA_DIR:-$HERE/.data}"
export HARNESS_TUTOR_PROVIDER="${HARNESS_TUTOR_PROVIDER:-}"
mkdir -p "$HARNESS_DATA_DIR"
echo "start.sh: starting backend on 127.0.0.1:$BACKEND_PORT"
cd "$HERE/backend"
"$PYTHON" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!
cleanup() { kill "$BACKEND_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
echo "start.sh: waiting for backend health"
i=0
while [ "$i" -lt 60 ]; do
  if "$PYTHON" - "$BACKEND_PORT" <<'PY' >/dev/null 2>&1
import sys, urllib.request
with urllib.request.urlopen("http://127.0.0.1:%s/api/v1/health" % sys.argv[1], timeout=2) as r:
    sys.exit(0 if r.status == 200 else 1)
PY
  then echo "start.sh: backend healthy"; break; fi
  i=$((i + 1)); sleep 1
done
if [ "$i" -ge 60 ]; then echo "start.sh: backend failed to become healthy after 60s" >&2; exit 1; fi
echo "start.sh: starting control server on 0.0.0.0:$PORT"
cd "$HERE"
export LUMINEST_BACKEND_URL="http://127.0.0.1:$BACKEND_PORT"
exec "$PYTHON" server.py
'''

# Real app captures, not renders. Source: outputs/app-screenshots/presentation/
# (2640x1720 release-build captures), downscaled to 1200px JPEG for the web.
# Provenance and blank checks live in outputs/app-screenshots/MANIFEST.md.
CAPTURE_NAMES = [
    "01-today", "02-knowledge-map", "03-practice-question",
    "04-practice-feedback", "05-grounded-tutor", "06-projects",
    "07-project-feedback", "08-daily-review", "09-insights",
    "10-course-picker", "11-setup-goal", "12-setup-pace",
]

# 1.4.1 (2026-11-25) is a re-assembly of the 2026-11-24 release candidate, not a new
# compile: --skip-native-build --skip-backend-build reused the same arm64 executable and
# the frozen schema-13 backend. The version string had to change because publishing new
# bytes under 1.4.0 would leave installed 1.4.0 builds believing they were current.
# Hashes below are measured from the artifacts actually produced by that reassembly and
# recorded in outputs/.packaging/package-result.json; a drift still fails the build.
ARTIFACTS = [
    ("Luminest-arm64.dmg", "b08864a35b3ed666bc6c2ee7d469dc9ff47b196921bfcf2877442a7ae3e5f2ae",
     98443979, "macOS disk image"),
    ("Luminest-arm64.zip", "3f7f3035626db9007759228b37fef467b93ac607aaa13d737e4abebe957bdab0",
     94213522, "macOS app archive"),
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
    launcher = os.path.join(SITE, "start.sh")
    with open(launcher, "w", encoding="utf-8") as fh:
        fh.write(_START_SH)
    os.chmod(launcher, 0o755)
    print("  single-port launcher -> start.sh")


def copy_captures() -> None:
    """Ship the twelve real app frames and record their measured sha256."""
    dest = os.path.join(SITE, "assets", "captures")
    os.makedirs(dest, exist_ok=True)
    rows = []
    for name in CAPTURE_NAMES:
        src = os.path.join(CAPTURES_SRC, name + ".jpg")
        ensure(os.path.isfile(src), "missing real capture: " + src)
        size = os.path.getsize(src)
        # A blank frame compresses to a few KB; 20 KB is a deliberately loose
        # floor that still catches an empty or solid-colour capture.
        ensure(size > 20_000, "capture looks blank: %s (%d bytes)" % (src, size))
        shutil.copy2(src, os.path.join(dest, name + ".jpg"))
        rows.append({"name": name + ".jpg", "bytes": size, "sha256": sha256(src)})
    with open(os.path.join(SITE, "assets", "captures.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "source": "outputs/app-screenshots/presentation/*.png",
            "provenance": "outputs/app-screenshots/MANIFEST.md",
            "captured": "2026-10-19",
            "method": "release-build window capture, geometric resize only, no retouching",
            "frames": rows,
        }, fh, indent=2)
        fh.write("\n")
    print("  captures -> assets/captures/ (%d real frames, sha256 recorded)" % len(rows))


def copy_art() -> None:
    """Ship the decorative artworks, carrying their licence evidence with them.

    Fail-close: only works whose Commons metadata says Public domain / CC0 / PD-*
    and which are not marked copyrighted may be written into the site. A missing
    provenance record or a missing file aborts the whole build.
    """
    manifest_path = os.path.join(ART_SRC, "art.json")
    ensure(os.path.isfile(manifest_path), "missing art provenance: " + manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as fh:
        provenance = json.load(fh)
    works = provenance.get("works", [])
    ensure(len(works) == 8, "expected 8 licensed works, found %d" % len(works))

    dest = os.path.join(SITE, "assets", "art")
    os.makedirs(dest, exist_ok=True)
    shipped = []
    for work in works:
        slug = work["slug"]
        lic = (work.get("licence", "") + " " + work.get("usage_terms", "")).lower()
        ensure(any(t in lic for t in ("public domain", "cc0", "pd-old", "pd-art")),
               "art licence not verifiably free: %s (%r)" % (slug, work.get("licence")))
        ensure(str(work.get("copyrighted_flag", "")).lower() not in ("true", "yes"),
               "art marked copyrighted: " + slug)
        ensure(work.get("source_page", "").startswith("https://commons.wikimedia.org/wiki/"),
               "art missing Commons source page: " + slug)
        src = os.path.join(ART_WEB, slug + ".jpg")
        ensure(os.path.isfile(src), "missing art asset: " + src)
        ensure(os.path.getsize(src) > 15_000, "art asset looks empty: " + src)
        shutil.copy2(src, os.path.join(dest, slug + ".jpg"))
        path = os.path.join(dest, slug + ".jpg")
        row = dict(work)
        row["shipped_file"] = "assets/art/" + slug + ".jpg"
        row["shipped_bytes"] = os.path.getsize(path)
        row["shipped_sha256"] = sha256(path)
        shipped.append(row)

    with open(os.path.join(SITE, "assets", "art.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "source": provenance.get("source"),
            "policy": provenance.get("policy"),
            "retrieved_at": provenance.get("retrieved_at"),
            "count": len(shipped),
            "works": shipped,
        }, fh, indent=2)
        fh.write("\n")
    print("  art -> assets/art/ (%d PD/CC0 works, licence evidence + sha256)" % len(shipped))


def copy_reference_style() -> None:
    """Ship the open-licensed reference-style assets with fail-close evidence."""
    manifest_path = os.path.join(REFERENCE_ASSETS_SRC, "assets.json")
    ensure(os.path.isfile(manifest_path), "missing reference-style provenance: " + manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as fh:
        provenance = json.load(fh)
    works = provenance.get("works", [])
    ensure(len(works) >= 8, "expected at least 8 reference-style assets, found %d" % len(works))

    dest = os.path.join(SITE, "assets", "reference-style")
    os.makedirs(dest, exist_ok=True)
    shipped = []
    for work in works:
        slug = work["slug"]
        lic = (work.get("licence", "") + " " + work.get("usage_terms", "")).lower()
        ensure(any(t in lic for t in ("public domain", "cc0", "pd-old", "pd-art", "pd-us")),
               "reference-style licence not verifiably free: %s (%r)" %
               (slug, work.get("licence")))
        ensure(str(work.get("copyrighted_flag", "")).lower() not in ("true", "yes"),
               "reference-style asset marked copyrighted: " + slug)
        ensure(work.get("source_page", "").startswith("https://commons.wikimedia.org/wiki/"),
               "reference-style asset missing Commons source page: " + slug)
        src = os.path.join(REFERENCE_ASSETS_WEB, slug + ".jpg")
        ensure(os.path.isfile(src), "missing reference-style asset: " + src)
        ensure(os.path.getsize(src) > 5_000, "reference-style asset looks empty: " + src)
        path = os.path.join(dest, slug + ".jpg")
        shutil.copy2(src, path)
        row = dict(work)
        row["shipped_file"] = "assets/reference-style/" + slug + ".jpg"
        row["shipped_bytes"] = os.path.getsize(path)
        row["shipped_sha256"] = sha256(path)
        shipped.append(row)

    with open(os.path.join(SITE, "assets", "reference-style.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "source": provenance.get("source"),
            "policy": provenance.get("policy"),
            "retrieved_at": provenance.get("retrieved_at"),
            "count": len(shipped),
            "works": shipped,
        }, fh, indent=2)
        fh.write("\n")
    print("  reference-style -> assets/reference-style/ (%d PD/CC0 works)" % len(shipped))


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
        "release_notes": ("1.4.1: rebuilt from the 2026-11-24 candidate with schema 13, "
                          "215 verified visual assets and the supervision fix that keeps "
                          "teacher directives out of Lumi's speech bubble. Version bumped "
                          "so installed 1.4.0 builds are told a new build exists."),
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
    copy_captures()
    copy_art()
    copy_reference_style()
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
