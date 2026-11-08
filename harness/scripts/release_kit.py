#!/usr/bin/env python3
"""Assemble a public release from an already signed and notarized packaged build.

Build records are necessary provenance, not proof of Apple's acceptance. Every release
must pass live signature, expected Developer ID, Gatekeeper and stapled-ticket checks
on the app, DMG, and the app inside each downloadable artifact. This script does not
sign, submit to notarization, publish, or bypass Gatekeeper. Ad-hoc development builds
remain build artifacts and cannot be relabeled as public releases.

Usage:
    python scripts/release_kit.py --version 1.1.16
    python scripts/release_kit.py --version 1.1.16 --verify
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
OUTPUTS = HARNESS.parent / "outputs"
WORK = OUTPUTS / ".packaging"
RESULT = WORK / "package-result.json"
APP_NAME = "Luminest"

INSTALL_TXT = """Luminest {version} — installation
=======================================

This public release requires a verified Developer ID Application signature and Apple
notarization. Verify SHA256SUMS.txt, open the DMG, and drag Luminest.app to Applications.
Alternatively, extract the zip and move Luminest.app to Applications.

If macOS rejects the download, stop and contact the distributor or download a verified
replacement. Do not remove quarantine attributes or disable Gatekeeper. No bypass
installer is included. An included Homebrew cask uses the normal Gatekeeper checks:

    brew install --cask ./luminfest.rb

Requirements: Apple Silicon (arm64), macOS 14 or later. There is no Intel build.
Local data: ~/Library/Application Support/Luminfest Learning Harness/
Uninstalling the app does not delete that data.
"""

RELEASE_NOTES = """# Luminest {version}

Built {date} · {size_app} · macOS 14+ · Apple Silicon

## What this build is

{summary}

## Install

See `INSTALL.txt`. Open the DMG and drag Luminest.app to Applications.

## Signature

Verified Developer ID Application signature and Apple notarization, including stapled
app and DMG tickets. See `release.json` for the verification evidence.

## Checksums

See `SHA256SUMS.txt`. Verify before trusting a download:

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
        raise SystemExit(f"release_kit: no build record at {path}. Run scripts/package.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def verification_command(command: list[str]) -> str:
    """Run verification only; missing tools and failed checks refuse the release."""
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"release_kit: verification unavailable for {command[0]} "
                         f"({type(exc).__name__}); verify on macOS with Apple tools installed.") from exc
    output = completed.stdout + completed.stderr
    if completed.returncode:
        raise SystemExit(f"release_kit: verification failed: {' '.join(command)}\n{output.strip()}")
    return output


def verify_signed_artifact(path: Path, identity: str, *, app: bool) -> dict:
    flags = ["--deep"] if app else []
    verification_command(["/usr/bin/codesign", "--verify", *flags, "--strict", str(path)])
    details = verification_command(["/usr/bin/codesign", "--display", "--verbose=4", str(path)])
    fields = details.splitlines()
    team = identity.rsplit("(", 1)[1].rstrip(")")
    if f"Authority={identity}" not in fields or f"TeamIdentifier={team}" not in fields:
        raise SystemExit(f"release_kit: {path} is not signed by the expected Developer ID Application.")
    cdhash = next((line.removeprefix("CDHash=") for line in fields if line.startswith("CDHash=")), None)
    if not cdhash:
        raise SystemExit(f"release_kit: codesign supplied no CDHash for {path}.")
    assessment = ["/usr/sbin/spctl", "--assess", "--type", "execute" if app else "open"]
    if not app:
        assessment += ["--context", "context:primary-signature"]
    gatekeeper = verification_command([*assessment, "--verbose=2", str(path)])
    if "source=Notarized Developer ID" not in gatekeeper:
        raise SystemExit(f"release_kit: Gatekeeper did not confirm Notarized Developer ID for {path}.")
    verification_command(["/usr/bin/xcrun", "stapler", "validate", str(path)])
    return {"signature_verified": True, "sign_identity": identity, "team_id": team,
            "cdhash": cdhash, "gatekeeper": "Notarized Developer ID", "stapled_ticket_valid": True}


def read_distribution(app: Path) -> dict:
    path = app / "Contents" / "Resources" / "distribution.json"
    if not app.is_dir() or not path.is_file():
        raise SystemExit(f"release_kit: packaged app or distribution.json is missing: {app}")
    if (path.parent / "NOT_RELEASABLE.txt").exists():
        raise SystemExit(f"release_kit: {app} carries NOT_RELEASABLE.txt; rebuild without the legal override.")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_downloads(dmg: Path, archive: Path, identity: str, distribution: dict,
                     app_evidence: dict) -> dict:
    """The downloads must contain the same signed, stapled app, not just matching metadata."""
    evidence = {"dmg": verify_signed_artifact(dmg, identity, app=False)}
    verification_command(["/usr/bin/hdiutil", "verify", str(dmg)])
    with tempfile.TemporaryDirectory(prefix="luminest-release-verify-") as temporary:
        root = Path(temporary)
        mount = root / "mounted"
        mount.mkdir()
        verification_command(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse",
                              "-mountpoint", str(mount), str(dmg)])
        try:
            bundled = mount / f"{APP_NAME}.app"
            evidence["dmg_app"] = verify_signed_artifact(bundled, identity, app=True)
            if (read_distribution(bundled) != distribution
                    or evidence["dmg_app"]["cdhash"] != app_evidence["cdhash"]):
                raise SystemExit("release_kit: DMG does not contain the recorded signed app.")
        finally:
            verification_command(["/usr/bin/hdiutil", "detach", str(mount)])

        extracted = root / "archive"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as zipped:
            for item in zipped.infolist():
                name = item.filename
                if name.startswith("/") or ".." in name.split("/"):
                    raise SystemExit("release_kit: unsafe path in app archive.")
                if stat.S_ISLNK(item.external_attr >> 16):
                    target = zipped.read(item).decode("utf-8")
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                    if target.startswith("/") or resolved == ".." or resolved.startswith("../"):
                        raise SystemExit("release_kit: unsafe symlink in app archive.")
        verification_command(["/usr/bin/ditto", "-x", "-k", str(archive), str(extracted)])
        bundled = extracted / f"{APP_NAME}.app"
        evidence["zip_app"] = verify_signed_artifact(bundled, identity, app=True)
        if (read_distribution(bundled) != distribution
                or evidence["zip_app"]["cdhash"] != app_evidence["cdhash"]):
            raise SystemExit("release_kit: zip does not contain the recorded signed app.")
    return evidence


def assert_shippable(record: dict, version: str) -> dict:
    legal = record.get("legal_gate") or {}
    if legal.get("ship_ready") is not True:
        raise SystemExit("release_kit: legal_gate.ship_ready is false; fill backend/legal/ and "
                         "repackage without --allow-template-legal.")
    if record.get("version") != version:
        raise SystemExit(f"release_kit: asked for {version} but the packaged build is "
                         f"{record.get('version')}. Re-package, do not relabel.")
    if (record.get("backend_smoke") or {}).get("passed") is not True:
        raise SystemExit("release_kit: the packaged backend failed its own smoke test.")
    artifacts = record.get("artifacts") or {}
    for key in ("dmg", "archive"):
        raw = record.get(key)
        if not raw or not Path(raw).is_file():
            raise SystemExit(f"release_kit: {key} artifact is missing.")
        path = Path(raw)
        recorded = artifacts.get(path.name) or {}
        if sha256(path) != recorded.get("sha256"):
            raise SystemExit(f"release_kit: {path.name} has changed since it was packaged or has no digest.")

    identity = record.get("sign_identity")
    if not isinstance(identity, str) or not re.fullmatch(
            r"Developer ID Application: .+ \([A-Z0-9]{10}\)", identity):
        raise SystemExit("release_kit: public release requires the expected Developer ID Application "
                         "sign_identity; ad-hoc builds are not publicly releasable.")
    app = Path(record.get("app") or "")
    dmg, archive = Path(record["dmg"]), Path(record["archive"])
    app_notary = record.get("app_notarization") or {}
    notary = record.get("notarization") or {}
    if (app_notary.get("stapled_app") != str(app) or notary.get("stapled") != str(dmg)
            or not {str(dmg), str(archive)} <= set(notary.get("notarized") or [])):
        raise SystemExit("release_kit: missing app/DMG notarization and stapling build evidence; "
                         "package with --sign-identity and --notarize using operator credentials.")
    distribution = read_distribution(app)
    if (distribution.get("signing") != identity or distribution.get("notarized") is not True
            or distribution.get("version") != version or distribution.get("releasable") is not True
            or (distribution.get("legal_gate") or {}).get("ship_ready") is not True):
        raise SystemExit("release_kit: signed bundle distribution contract does not permit public release.")
    app_evidence = verify_signed_artifact(app, identity, app=True)
    return {"app": app_evidence,
            **verify_downloads(dmg, archive, identity, distribution, app_evidence)}


def cask_text(version: str, base_url: str, digest: str) -> str:
    # Preserve the existing public cask token while using the current display brand.
    return f'''cask "luminfest" do
  version "{version}"
  sha256 "{digest}"

  url "{base_url.rstrip('/')}/Luminest-{version}-arm64.dmg"
  name "Luminest"
  desc "Adaptive study harness with a local, offline-first tutor"
  homepage "{base_url.rstrip('/')}"

  depends_on macos: ">= :sonoma"
  depends_on arch: :arm64

  app "Luminest.app"
end
'''


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble a signed, notarized public Luminest release")
    parser.add_argument("--version", required=True, help="the version already packaged")
    parser.add_argument("--base-url", default=None,
                        help="public artifact URL; enables the normal Homebrew cask")
    parser.add_argument("--result", default=str(RESULT), help="path to package-result.json")
    parser.add_argument("--out", default=None, help="output directory (default outputs/release/<version>)")
    parser.add_argument("--verify", action="store_true",
                        help="also reverify the copied downloads; source verification is always required")
    args = parser.parse_args(argv)
    record = read_result(Path(args.result))
    verification = assert_shippable(record, args.version)
    out = Path(args.out) if args.out else OUTPUTS / "release" / args.version
    if out.exists():
        raise SystemExit(f"release_kit: output already exists: {out}; choose a fresh directory.")
    out.mkdir(parents=True)
    shipped_dmg = out / f"{APP_NAME}-{args.version}-arm64.dmg"
    shipped_zip = out / f"{APP_NAME}-{args.version}-arm64.zip"
    shutil.copy2(Path(record["dmg"]), shipped_dmg)
    shutil.copy2(Path(record["archive"]), shipped_zip)
    for path, original in ((shipped_dmg, record["dmg"]), (shipped_zip, record["archive"])):
        if sha256(path) != record["artifacts"][Path(original).name]["sha256"]:
            raise SystemExit("release_kit: artifact changed while copying; release is incomplete.")
    if args.verify:
        verification["copied_downloads"] = verify_downloads(
            shipped_dmg, shipped_zip, record["sign_identity"],
            read_distribution(Path(record["app"])), verification["app"])
    write(out / "INSTALL.txt", INSTALL_TXT.format(version=args.version))
    digest = sha256(shipped_dmg)
    write(out / "SHA256SUMS.txt", f"{digest}  {shipped_dmg.name}\n"
          f"{sha256(shipped_zip)}  {shipped_zip.name}\n")
    built = datetime.datetime.fromtimestamp(shipped_dmg.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    write(out / "RELEASE.md", RELEASE_NOTES.format(
        version=args.version, date=built, size_app=human(shipped_dmg.stat().st_size),
        summary=record.get("summary") or "See the release notes for what changed."))
    if args.base_url:
        write(out / "luminfest.rb", cask_text(args.version, args.base_url, digest))
    report = {
        "version": args.version, "directory": str(out), "public_release": True,
        "artifacts": {
            "dmg": {"file": shipped_dmg.name, "bytes": shipped_dmg.stat().st_size, "sha256": digest},
            "zip": {"file": shipped_zip.name, "bytes": shipped_zip.stat().st_size,
                    "sha256": sha256(shipped_zip)},
        },
        "cask": bool(args.base_url), "verification": verification,
        "signed": record["sign_identity"], "notarized": True,
    }
    write(out / "release.json", json.dumps(report, indent=2) + "\n")
    print(f"release {args.version} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
