#!/bin/zsh
# Package the SwiftPM-built LearningHarness binary as Luminfest.app.
# The Info.plist declares the microphone + speech-recognition usage strings so
# the Stage's on-device ASR can request permission like any regular app.
set -euo pipefail
cd "$(dirname "$0")/.."
BIN=".build/debug/LearningHarness"
[ -x "$BIN" ] || { echo "binary missing — run swift build first" >&2; exit 1 }
APP=".build/Luminfest.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp "$BIN" "$APP/Contents/MacOS/Luminfest"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key><string>io.luminfest.harness</string>
    <key>CFBundleName</key><string>Luminfest</string>
    <key>CFBundleExecutable</key><string>Luminfest</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>0.4.0</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>Luminfest uses the microphone only for on-device dictation of your messages to the tutor. Audio never leaves this machine.</string>
    <key>NSSpeechRecognitionUsageDescription</key>
    <string>Luminfest transcribes your dictation on this device so you can speak to the tutor instead of typing.</string>
</dict>
</plist>
PLIST
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
echo "packaged: ${PWD}/$APP"
