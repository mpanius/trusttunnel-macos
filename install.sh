#!/bin/bash
# TrustTunnel macOS GUI installer
set -euo pipefail

echo "=== TrustTunnel macOS GUI Installer ==="
echo ""

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: This installer is for macOS only."
    exit 1
fi

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is required. Install from https://python.org"
    exit 1
fi
echo "✓ Python $(python3 --version)"

# Check trusttunnel_client
if ! command -v trusttunnel_client &>/dev/null && [ ! -f /opt/trusttunnel_client/trusttunnel_client ]; then
    echo ""
    echo "TrustTunnel CLI client not found. Installing..."
    curl -fsSL https://raw.githubusercontent.com/TrustTunnel/TrustTunnelClient/refs/heads/master/scripts/install.sh | sh -s -
else
    echo "✓ trusttunnel_client found"
fi

# Create venv and install deps
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt
pip install -e .

echo ""
echo "=== Installation complete ==="
echo ""
echo "To run:"
echo "  cd $SCRIPT_DIR"
echo "  source .venv/bin/activate"
echo "  python3 -m src.app"
echo ""
echo "To auto-start on login, run:"
echo "  ./install-launch-agent.sh"
