#!/bin/sh
set -eu
CARD_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
mkdir -p "$CARD_ROOT/build/swift-cache"
CARD_OVERLAY="$(python3 "$CARD_ROOT/desktop/swift-overlay.py")"
CARD_BINARY="${1:-$CARD_ROOT/build/WeChatLogin}"
xcrun swiftc -O -module-cache-path "$CARD_ROOT/build/swift-cache" \
  -target "$(uname -m)-apple-macosx13.0" -vfsoverlay "$CARD_OVERLAY" \
  "$CARD_ROOT/desktop/WeChatLogin.swift" -o "$CARD_BINARY"
codesign --force --sign - "$CARD_BINARY"
