#!/usr/bin/env python3
"""Assemble a publishable release directory from an already-packaged build.

Why this exists
---------------
``scripts/package.py`` produces a ``.app``, a DMG and a zip. Those are *build*
artifacts: unversioned filenames, no checksums, no installation instructions, and no
explanation of what a recipient should do when Gatekeeper refuses an unnotarized app.

A *release* is a directory someone else can act on. This script turns one into the
other, and it is deliberately strict about the one thing that matters: it refuses to
assemble a release from a build whose own record says it is not shippable. That check
is the difference between "we forgot" and "the pipeline would not let us".

The Apple Developer question
----------------------------
Notarization cannot be faked. ``spctl`` will reject an ad-hoc signed app that carries a
quarantine flag, and no amount of configuration changes that — it is a cryptographic
fact, not a missing setting. What *can* be solved is distribution: the quarantine flag
is metadata, and a legitimate installer removes it. This script ships that installer,
so the product is distributable without a Developer ID, at the cost of one extra step
that the user never has to type by hand.

Usage
-----
    python scripts/release_kit.py --version 1.1.16
    python scripts/release_kit.py --version 1.1.16 --base-url https://example.test/v1.1.16
    python scripts/release_kit.py --version 1.1.16 --verify
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
OUTPUTS = HARNESS.parent / "outputs"
WORK = OUTPUTS / ".packaging"
RESULT = WORK / "package-result.json"

APP_NAME = "Luminfest"

#: Installed verbatim. POSIX sh, no bashisms: a tester's shell is not our business.
INSTALL_SH = r'''#!/bin/sh
# Luminfest installer.
#
# Use it when macOS says the app "is damaged and can't be opened", or when you would
# rather not drag anything into /Applications by hand. This build is ad-hoc signed and
# not notarized, so macOS quarantines it on download; this script removes that flag
# after copying the bundle, which is the whole difference between a blocked app and a
# working one.
#
#   sh install.sh                             # uses the .dmg sitting beside this script
#   sh install.sh path/to/Luminfest-arm64.dmg
#   INSTALL_DIR=~/Applications sh install.sh  # install somewhere else
set -eu

APP="Luminfest"
DEST_DIR="${INSTALL_DIR:-/Applications}"
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="${1:-}"

if [ -z "$SRC" ]; then
  for candidate in "$HERE"/*.dmg; do
    if [ -f "$candidate" ]; then SRC="$candidate"; break; fi
  done
fi

if [ -z "$SRC" ] || [ ! -e "$SRC" ]; then
  echo "install.sh: give me the Luminfest .dmg, or put it in the same folder as this script." >&2
  exit 1
fi

MOUNT=""
cleanup() {
  if [ -n "$MOUNT" ]; then hdiutil detach "$MOUNT" -quiet >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT INT TERM

case "$SRC" in
  *.dmg)
    MOUNT=$(mktemp -d "${TMPDIR:-/tmp}/luminfest-mnt.XXXXXX")
    hdiutil attach "$SRC" -mountpoint "$MOUNT" -nobrowse -quiet
    APP_SRC="$MOUNT/$APP.app"
    ;;
  *)
    APP_SRC="$SRC"
    ;;
esac

if [ ! -d "$APP_SRC" ]; then
  echo "install.sh: there is no $APP.app inside $SRC" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
TARGET="$DEST_DIR/$APP.app"

# Refuse to delete anything that is not the bundle this script installed.
case "$TARGET" in
  */"$APP.app") ;;
  *) echo "install.sh: refusing to write to $TARGET" >&2; exit 1 ;;
esac

if [ -d "$TARGET" ]; then
  echo "Replacing the existing copy at $TARGET"
  rm -rf "$TARGET"
fi

# ditto, not cp: it preserves symlinks, permissions and extended attributes, which is
# what a signed bundle needs to stay intact.
/usr/bin/ditto "$APP_SRC" "$TARGET"

# The point of the whole script. Gatekeeper blocks an unnotarized bundle by setting
# com.apple.quarantine on it at download time; clearing it here means the app opens
# with no dialog, exactly as a notarized build would.
/usr/bin/xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null || true
/usr/bin/xattr -cr "$TARGET" 2>/dev/null || true

if ! /usr/bin/codesign --verify --strict "$TARGET" >/dev/null 2>&1; then
  echo "warning: the bundle signature did not verify. Re-download rather than trusting it." >&2
fi

echo ""
echo "Installed: $TARGET"
echo ""
echo "Open it:            open \"$TARGET\""
echo "Your data lives in: ~/Library/Application Support/Luminfest Learning Harness/"
echo ""
echo "The first launch starts a local backend and can take up to a minute."
'''

INSTALL_TXT = """Luminfest {version} — installing it
=======================================

This build is signed ad-hoc, not notarized by Apple. That is a statement about a
certificate that costs US$99 a year, not about the software: the app runs, and the
signature still verifies locally. What it means in practice is that macOS quarantines
the download and may refuse to open it with a message about an unidentified developer,
or about the app being "damaged".

Pick whichever of these matches how you got the file.

1. Let the script do it (recommended)
-------------------------------------
Put this folder somewhere convenient, then:

    sh install.sh

It mounts the DMG, copies Luminfest.app into /Applications, removes the quarantine
flag, and tells you what to do next. It is a short shell script — read it first if you
would rather not run something you have not read.

2. Drag it in, then clear the flag once
---------------------------------------
Open the DMG, drag Luminfest.app to Applications, then run:

    xattr -dr com.apple.quarantine /Applications/Luminfest.app
    open /Applications/Luminfest.app

You only need this once per install. macOS 15 removed most of the old
right-click-then-Open workaround, so the command above is the reliable route.

3. Homebrew
-----------
If a cask formula is included in this release folder:

    brew install --cask --no-quarantine ./luminfest.rb

Requirements
------------
Apple Silicon (arm64) Mac, macOS 14 or later. There is no Intel build.

Where your data goes
--------------------
Everything is stored locally in:

    ~/Library/Application Support/Luminfest Learning Harness/

Nothing is sent anywhere unless you add a tutor provider and key yourself. Deleting
that folder removes everything; uninstalling the app is not enough to delete it.

First launch
------------
The app starts a backend process on your own machine. A cold first start takes up to a
minute; later starts take about twenty seconds. If the window says the service is not
ready, wait — it usually is.
"""

RELEASE_NOTES = """# Luminfest {version}

Built {date} · {size_app} · macOS 14+ · Apple Silicon

## What this build is

{summary}

## Install

See `INSTALL.txt`. Short version: `sh install.sh`.

## Signature

{signature}

## Checksums

See `SHA256SUMS.txt`. Verify before you trust a download:

    shasum -a 256 -c SHA256SUMS.txt
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human(bytes_: int) -> str:
    return f"{bytes_ / 1e6:.1f} MB"


def read_result(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(
            f"release_kit: no build record at {path}. Run scripts/package.py first — "
            "a release assembled from a stale artifact is how a previous build shipped "
            "under a new version number.")
    return json.loads(path.read_text(encoding="utf-8"))


def assert_shippable(record: dict, version: str) -> None:
    """Refuse to publish anything the build record itself calls unshippable."""
    legal = record.get("legal_gate") or {}
    if not legal.get("ship_ready", False):
        raise SystemExit(
            "release_kit: the build record says legal_gate.ship_ready is false "
            f"({legal.get('placeholders', '?')} placeholders). This build must not be "
            "published. Fill backend/legal/ and repackage without --allow-template-legal.")

    if record.get("version") != version:
        raise SystemExit(
            f"release_kit: asked for {version} but the packaged build is "
            f"{record.get('version')}. Re-package, do not relabel.")

    smoke = record.get("backend_smoke") or {}
    if not smoke.get("passed", False):
        raise SystemExit("release_kit: the packaged backend failed its own smoke test; "
                         "this build is not releasable.")

    artifacts = record.get("artifacts") or {}
    for key in ("dmg", "archive"):
        raw = record.get(key)
        if not raw:
            raise SystemExit(f"release_kit: the build record lists no {key} artifact.")
        path = Path(raw)
        if not path.is_file():
            raise SystemExit(f"release_kit: {key} is recorded but missing on disk: {path}")
        recorded = artifacts.get(path.name)
        if not recorded:
            raise SystemExit(f"release_kit: {path.name} is not in the build record's artifacts.")
        if sha256(path) != recorded["sha256"]:
            raise SystemExit(
                f"release_kit: {path.name} has changed since it was packaged. Refusing to "
                "publish bytes that no build produced.")


def quarantine(path: Path) -> None:
    """Mark a file the way a browser or chat app would after a download."""
    subprocess.run(["/usr/bin/xattr", "-w", "com.apple.quarantine",
                    "0081;00000000;Safari;", str(path)], check=True)


def verify_installer(dmg: Path, workdir: Path) -> dict:
    """Prove install.sh works on a quarantined DMG, without touching /Applications."""
    target_root = workdir / "Applications"
    target_root.mkdir()

    staged = workdir / dmg.name
    shutil.copy2(dmg, staged)
    quarantine(staged)

    script = workdir / "install.sh"
    script.write_text(INSTALL_SH, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)

    env = dict(os.environ, INSTALL_DIR=str(target_root))
    completed = subprocess.run(["/bin/sh", str(script), str(staged)],
                               capture_output=True, text=True, env=env)

    installed = target_root / f"{APP_NAME}.app"
    if completed.returncode != 0 or not installed.is_dir():
        raise SystemExit("release_kit: install.sh failed on a quarantined DMG.\n"
                         f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")

    left = subprocess.run(["/usr/bin/xattr", "-p", "com.apple.quarantine", str(installed)],
                          capture_output=True, text=True)
    if left.returncode == 0:
        raise SystemExit("release_kit: install.sh left the quarantine flag in place; "
                         f"the app would still be blocked. Value: {left.stdout.strip()}")

    signed = subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(installed)],
                            capture_output=True, text=True)

    return {
        "install_sh_ok": True,
        "quarantine_cleared": True,
        "signature_verifies": signed.returncode == 0,
        "installed_bundle": installed.name,
    }


def cask_text(version: str, base_url: str, digest: str) -> str:
    return f'''cask "luminfest" do
  version "{version}"
  sha256 "{digest}"

  url "{base_url.rstrip('/')}/Luminfest-{version}-arm64.dmg"
  name "Luminfest"
  desc "Adaptive study harness with a local, offline-first tutor"
  homepage "{base_url.rstrip('/')}"

  depends_on macos: ">= :sonoma"
  depends_on arch: :arm64

  app "Luminfest.app"

  caveats <<~EOS
    This build is ad-hoc signed and not notarized by Apple. Install it with

        brew install --cask --no-quarantine luminfest

    so that macOS does not quarantine the bundle. Without that flag the app may be
    reported as damaged on first launch.
  EOS
end
'''


def write(path: Path, text: str, executable: bool = False) -> Path:
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble a publishable Luminfest release directory")
    parser.add_argument("--version", required=True, help="the version already packaged")
    parser.add_argument("--base-url", default=None,
                        help="public URL the artifacts will be served from; enables the Homebrew cask")
    parser.add_argument("--result", default=str(RESULT), help="path to package-result.json")
    parser.add_argument("--out", default=None, help="output directory (default outputs/release/<version>)")
    parser.add_argument("--verify", action="store_true",
                        help="install the quarantined DMG with install.sh in a temp directory")
    args = parser.parse_args(argv)

    record = read_result(Path(args.result))
    assert_shippable(record, args.version)

    out = Path(args.out) if args.out else OUTPUTS / "release" / args.version
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    dmg = Path(record["dmg"])
    zip_ = Path(record["archive"])

    shipped_dmg = out / f"{APP_NAME}-{args.version}-arm64.dmg"
    shipped_zip = out / f"{APP_NAME}-{args.version}-arm64.zip"
    shutil.copy2(dmg, shipped_dmg)
    shutil.copy2(zip_, shipped_zip)

    write(out / "install.sh", INSTALL_SH, executable=True)
    write(out / "INSTALL.txt", INSTALL_TXT.format(version=args.version))

    digest = sha256(shipped_dmg)
    lines = [f"{digest}  {shipped_dmg.name}", f"{sha256(shipped_zip)}  {shipped_zip.name}",
             f"{sha256(out / 'install.sh')}  install.sh"]
    write(out / "SHA256SUMS.txt", "\n".join(lines) + "\n")

    distribution_file = Path(record["app"]) / "Contents" / "Resources" / "distribution.json"
    distribution = (json.loads(distribution_file.read_text(encoding="utf-8"))
                    if distribution_file.is_file() else {})

    signature = ("Signed ad-hoc and **not notarized**. macOS will quarantine the download; "
                 "`install.sh` removes the flag. No Apple Developer account is required to "
                 "distribute this build.")
    if distribution.get("notarized"):
        signature = "Signed with a Developer ID and notarized by Apple."

    summary = record.get("summary") or "See the release notes for what changed."
    built = datetime.datetime.fromtimestamp(shipped_dmg.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    write(out / "RELEASE.md", RELEASE_NOTES.format(
        version=args.version,
        date=built,
        size_app=human(shipped_dmg.stat().st_size),
        summary=summary,
        signature=signature))

    if args.base_url:
        write(out / "luminfest.rb", cask_text(args.version, args.base_url, digest))

    verification = None
    if args.verify:
        with tempfile.TemporaryDirectory(prefix="luminfest-verify-") as tmp:
            verification = verify_installer(shipped_dmg, Path(tmp))

    report = {
        "version": args.version,
        "directory": str(out),
        "artifacts": {
            "dmg": {"file": shipped_dmg.name, "bytes": shipped_dmg.stat().st_size, "sha256": digest},
            "zip": {"file": shipped_zip.name, "bytes": shipped_zip.stat().st_size,
                    "sha256": sha256(shipped_zip)},
        },
        "cask": bool(args.base_url),
        "verification": verification,
        "signed": distribution.get("signing", "ad-hoc"),
        "notarized": bool(distribution.get("notarized", False)),
    }
    write(out / "release.json", json.dumps(report, indent=2) + "\n")

    print(f"release {args.version} -> {out}")
    for key in ("dmg", "zip"):
        info = report["artifacts"][key]
        print(f"  {info['file']}  {human(info['bytes'])}  sha256 {info['sha256'][:16]}…")
    if verification:
        print(f"  install.sh verified: {verification}")
    if not args.base_url:
        print("  no cask emitted (needs --base-url); install.sh and INSTALL.txt cover the "
              "offline case")
    return 0


if __name__ == "__main__":
    sys.exit(main())
