#!/bin/bash
# Configure passwordless sudo for TrustTunnel VPN client
# Run once after installing TrustTunnel.app to /Applications

set -euo pipefail

APP_CLI="/Applications/TrustTunnel.app/Contents/Resources/bin/trusttunnel_client"
BREW_CLI="/usr/local/bin/trusttunnel_client"
OPT_CLI="/opt/trusttunnel_client/trusttunnel_client"
SUDOERS_FILE="/etc/sudoers.d/trusttunnel"

echo "=== TrustTunnel Sudo Setup ==="
echo ""
echo "TrustTunnel needs root to create a virtual network interface (utun)."
echo "This script adds passwordless sudo for the trusttunnel_client binary."
echo ""

# Find the binary
CLI_PATH=""
if [ -f "$APP_CLI" ]; then
    CLI_PATH="$APP_CLI"
elif [ -f "$BREW_CLI" ]; then
    CLI_PATH="$BREW_CLI"
elif [ -f "$OPT_CLI" ]; then
    CLI_PATH="$OPT_CLI"
fi

if [ -z "$CLI_PATH" ]; then
    echo "ERROR: trusttunnel_client not found."
    echo "Searched: $APP_CLI, $BREW_CLI, $OPT_CLI"
    echo "Build the .app first: ./build-app.sh"
    exit 1
fi

echo "Found: $CLI_PATH"
echo ""

USER="${SUDO_USER:-$USER}"
echo "Configuring sudo for user: $USER"

if [ "$(id -u)" -ne 0 ]; then
    echo ""
    echo "Need sudo to write $SUDOERS_FILE"
    echo "Running: sudo $0"
    exec sudo "$0" "$@"
fi

# Write sudoers entry
cat > "$SUDOERS_FILE" << EOF
# TrustTunnel VPN — passwordless sudo for the client binary
$USER ALL=(ALL) NOPASSWD: $CLI_PATH
EOF

chmod 440 "$SUDOERS_FILE"

# Verify
if visudo -c -f "$SUDOERS_FILE" >/dev/null 2>&1; then
    echo ""
    echo "✓ Done! $USER can now run $CLI_PATH without password."
    echo ""
    echo "To verify: sudo -u $USER sudo -n $CLI_PATH --version"
else
    echo "ERROR: sudoers syntax error. Removing file."
    rm -f "$SUDOERS_FILE"
    exit 1
fi
