#!/bin/sh
# Internal distribution builder for the Luminest closed beta.
#
# Produces an UNSIGNED / AD-HOC-SIGNED .app from the *release* SwiftPM build and
# zips it for hand-off to internal testers. This is NOT a shippable artifact:
#   - ad-hoc signing (`codesign --sign -`) is self-signed and is NOT notarized;
#   - testers on other Macs must bypass Gatekeeper once (see docs/internal-alpha/INSTALL.md);
#   - the bundle carries an UNSIGNED / INTERNAL-ALPHA-ONLY marker, never a shipping stamp.
#
# The release binary must already exist (build it first if not):
#     cd harness/native && swift build -c release --disable-sandbox
#
# Usage:
#     sh harness/scripts/package_internal.sh
# Output:
#     harness/outputs/internal-distribution/
#         Luminest.app/
#         Luminest-closed-beta.zip
#         STAGING-MARKER.md
#         sha256.txt

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
NATIVE="$ROOT/native"
OUT="$ROOT/outputs/internal-distribution"
APP="$OUT/Luminest.app"
ZIP="$OUT/Luminest-closed-beta.zip"

# --- locate the release build (fall back to debug only if release is absent) ---
BIN=""
for cand in \
    "$NATIVE/.build/release/LearningHarness" \
    "$NATIVE/.build/arm64-apple-macosx/release/LearningHarness" \
    "$NATIVE/.build/debug/LearningHarness"; do
    [ -x "$cand" ] && { BIN="$cand"; break; }
done
[ -n "$BIN" ] || { echo "missing build output — run: swift build -c release --disable-sandbox" >&2; exit 1; }

# The resource bundle (sprites, hero art, growth seeds) MUST sit in Contents/Resources
# or Bundle.module resolution fails and the app renders nothing.
RES=""
for rcand in \
    "$NATIVE/.build/release/LumenLearningHarness_LearningHarness.bundle" \
    "$NATIVE/.build/arm64-apple-macosx/release/LumenLearningHarness_LearningHarness.bundle" \
    "$NATIVE/.build/debug/LumenLearningHarness_LearningHarness.bundle"; do
    [ -d "$rcand" ] && { RES="$rcand"; break; }
done
[ -n "$RES" ] || { echo "missing resource bundle — run: swift build -c release --disable-sandbox" >&2; exit 1; }

echo "packaging from: $BIN"
rm -rf "$APP"
mkdir -p "$OUT" "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp "$BIN" "$APP/Contents/MacOS/LearningHarness"
cp -R "$RES" "$APP/Contents/Resources/"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>en</string>
	<key>CFBundleDisplayName</key>
	<string>Luminest</string>
	<key>CFBundleExecutable</key>
	<string>LearningHarness</string>
	<key>CFBundleIdentifier</key>
	<string>workbuddy.LearningHarness</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>Luminest</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>1.0-alpha</string>
	<key>CFBundleVersion</key>
	<string>internal-alpha</string>
	<key>LSMinimumSystemVersion</key>
	<string>14.0</string>
	<key>NSPrincipalClass</key>
	<string>NSApplication</string>
	<key>NSSupportsAutomaticTermination</key>
	<true/>
	<key>NSSupportsSuddenTermination</key>
	<true/>
	<key>NSHighResolutionCapable</key>
	<true/>
	<key>NSMicrophoneUsageDescription</key>
	<string>Luminfest uses the microphone for voice dictation and live voice chat with the tutor.</string>
	<key>NSSpeechRecognitionUsageDescription</key>
	<string>Luminfest uses speech recognition to turn your spoken messages into text for the tutor.</string>
</dict>
</plist>
PLIST

# Ad-hoc signature: self-signed, NOT notarized. Gatekeeper on the *same* machine
# accepts it; on a tester's different Mac it must be bypassed once (see INSTALL.md).
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || {
    echo "codesign failed — continuing unsigned; testers must still bypass Gatekeeper" >&2
}
echo "sign: $(codesign --verify "$APP" 2>/dev/null && echo "ad-hoc ok" || echo "UNSIGNED")"

# --- stamp the artifact as internal-alpha-only, then zip ---
cat > "$OUT/STAGING-MARKER.md" <<'MARK'
# INTERNAL ALPHA BUILD — NOT FOR PUBLIC DISTRIBUTION

- **UNSIGNED** — ad-hoc self-signed (`codesign --sign -`), no Developer ID, **no notarization**.
- **NOT SHIPPABLE** — do not publish, do not redistribute outside the closed-alpha cohort.
- **macOS 14+ / Apple Silicon only** — see `docs/internal-alpha/ADMISSION.md`.
- Covered by the non-commercial internal testing agreement: `docs/internal-alpha/INTERNAL_ALPHA_AGREEMENT.md`.
- PhET simulations are CC BY-NC; this build is for **non-commercial** internal testing only.
MARK

# Refresh the archive only; previous zip is removed so the sha256 is always current.
rm -f "$ZIP"
# The .app is quarantined on copy by some macOS versions; zip preserves that flag,
# which is exactly why testers run the Gatekeeper-bypass steps in INSTALL.md.
ditto -c -k --keepParent "$APP" "$ZIP"
echo "zip: $ZIP ($(du -h "$ZIP" | cut -f1))"

SHA=$(shasum -a 256 "$ZIP" | awk '{print $1}')
echo "$SHA  $(basename "$ZIP")" > "$OUT/sha256.txt"
echo "sha256: $SHA"
echo "done -> $OUT"
