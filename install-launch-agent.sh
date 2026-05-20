#!/bin/bash
# Install the LaunchAgent for auto-start on login
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$SCRIPT_DIR/com.trusttunnel.gui.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.trusttunnel.gui.plist"

# Update paths in plist
mkdir -p "$HOME/Library/LaunchAgents"
sed "s|/path/to/trusttunnel-macos|$SCRIPT_DIR|g" "$PLIST_SRC" > "$PLIST_DST"

echo "Installed: $PLIST_DST"
echo ""

# Unload if already loaded
launchctl unload "$PLIST_DST" 2>/dev/null || true

# Load
launchctl load "$PLIST_DST"
echo "LaunchAgent loaded. TrustTunnel will start on next login."
echo ""
echo "To start now:"
echo "  launchctl start com.trusttunnel.gui"
