#!/bin/bash
set -euo pipefail
CARD_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CARD_APP="$CARD_ROOT/build/AgentProgressCard.app"
mkdir -p "$CARD_APP/Contents/MacOS" "$CARD_APP/Contents/Resources" "$CARD_ROOT/build/swift-cache"
CARD_OVERLAY="$(python3 "$CARD_ROOT/desktop/swift-overlay.py")"
xcrun swiftc -parse-as-library -O -module-cache-path "$CARD_ROOT/build/swift-cache" \
  -target "$(uname -m)-apple-macosx13.0" \
  -vfsoverlay "$CARD_OVERLAY" \
  "$CARD_ROOT/desktop/ProgressState.swift" "$CARD_ROOT/desktop/CardWindow.swift" \
  "$CARD_ROOT/desktop/ActivityFeed.swift" "$CARD_ROOT/desktop/ActivityModel.swift" \
  "$CARD_ROOT/desktop/ToolActivityView.swift" \
  "$CARD_ROOT/desktop/WorkExplanationView.swift" \
  "$CARD_ROOT/desktop/AgentProgressCard.swift" \
  -o "$CARD_APP/Contents/MacOS/AgentProgressCard"
mkdir -p "$CARD_APP/Contents/Resources/min_agent_desktop"
cp "$CARD_ROOT"/src/min_agent_desktop/*.py "$CARD_APP/Contents/Resources/min_agent_desktop/"
cat > "$CARD_APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>AgentProgressCard</string>
<key>CFBundleIdentifier</key><string>local.minagent.progresscard</string>
<key>CFBundleName</key><string>任务卡片</string>
<key>CFBundleDisplayName</key><string>任务卡片</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundleShortVersionString</key><string>0.1.0</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --sign - "$CARD_APP"
printf '%s\n' "$CARD_APP"
