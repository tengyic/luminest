#!/bin/sh
# Repackage the SwiftPM build output as a double-clickable .app bundle.
#
# Why this exists: `swift build` emits a bare executable, and `open` cannot
# activate a bare executable (error -10826) — so the app has no way to become
# frontmost and the user sees nothing. A minimal bundle fixes that, and
# LaunchServices activation does not require Accessibility permission the way
# Apple Events / System Events does.
#
# Run after `swift build --disable-sandbox`:
#     sh harness/native/package_app.sh
#
# The resource bundle MUST land in Contents/Resources: Bundle.module resolves
# relative to the executable's bundle, so Lumi's sprites, hero art and growth
# seeds only load in that layout.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
NATIVE="$ROOT/harness/native"
APP="$ROOT/outputs/Luminfest Learning Harness.app"

BIN="$NATIVE/.build/debug/LearningHarness"
RES="$NATIVE/.build/debug/LumenLearningHarness_LearningHarness.bundle"

[ -x "$BIN" ] || { echo "missing $BIN — run: swift build --disable-sandbox" >&2; exit 1; }
[ -d "$RES" ] || { echo "missing $RES — run: swift build --disable-sandbox" >&2; exit 1; }

echo "packaging -> $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp "$BIN" "$APP/Contents/MacOS/LearningHarness"
cp -R "$RES" "$APP/Contents/Resources/"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>en</string>
	<key>CFBundleDisplayName</key>
	<string>Luminfest Learning Harness</string>
	<key>CFBundleExecutable</key>
	<string>LearningHarness</string>
	<key>CFBundleIdentifier</key>
	<string>workbuddy.LearningHarness</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>Luminfest Learning Harness</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>1.0</string>
	<key>CFBundleVersion</key>
	<string>1</string>
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

codesign --force --deep --sign - "$APP" >/dev/null 2>&1
echo "signed: $(codesign --verify "$APP" 2>/dev/null && echo ok || echo FAILED)"
echo "launch: open -a \"$APP\""
