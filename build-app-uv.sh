#!/bin/bash
# Build TrustTunnel.app for macOS — via uv (no system/Homebrew Python hassle).
#
# Why this exists: Homebrew's python@3.11 ships a frequently-broken _tkinter
# (tcl-tk linkage), which makes build-app.sh loop on "install python@3.11".
# uv installs a python-build-standalone interpreter that bundles a working
# Tk 8.6, so the build just works — no brew, no system Python.
#
# Run on your Mac (PyInstaller builds for the host OS/arch).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Python version is overridable: TT_PYTHON=3.11 ./build-app-uv.sh
TT_PYTHON="${TT_PYTHON:-3.12}"

echo "=== TrustTunnel macOS App Builder (uv) ==="
echo ""

# 1. uv present?
if ! command -v uv >/dev/null 2>&1; then
    echo "✗ uv not found. Install it (one of):"
    echo "    brew install uv"
    echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "  then re-run ./build-app-uv.sh"
    exit 1
fi
echo "uv: $(uv --version)"

# 2. Ensure a uv-managed Python with a WORKING tkinter.
#    python-build-standalone bundles Tk 8.6 — this is the whole point.
echo ""
echo "=== Python $TT_PYTHON via uv ==="
uv python install "$TT_PYTHON"

TKVER="$(uv run --no-project --python "$TT_PYTHON" \
    python -c "import tkinter; print(tkinter.TkVersion)" 2>/dev/null || echo "")"
if [ -z "$TKVER" ]; then
    echo "✗ uv Python $TT_PYTHON has no working tkinter."
    echo "  Try another version, e.g.:  TT_PYTHON=3.11 ./build-app-uv.sh"
    exit 1
fi
echo "  Python $TT_PYTHON ready (Tk $TKVER) — tkinter works."

# 3. TrustTunnel CLI client binary (bundled into the .app by the spec).
echo ""
if [ ! -f "bin/trusttunnel_client" ]; then
    echo "=== Downloading TrustTunnel CLI client ==="
    mkdir -p bin
    TT_VERSION="v1.0.49"
    TT_URL="https://github.com/TrustTunnel/TrustTunnelClient/releases/download/${TT_VERSION}/trusttunnel_client-${TT_VERSION}-macos-universal.tar.gz"
    curl -fsSL "$TT_URL" | tar xz --strip-components=1 -C bin/ "trusttunnel_client-${TT_VERSION}-macos-universal/trusttunnel_client"
    chmod +x bin/trusttunnel_client
    rm -f bin/LICENSE bin/*.sig  # only need the binary
    echo "  bin/trusttunnel_client ($(du -sh bin/trusttunnel_client | cut -f1))"
else
    echo "=== TrustTunnel CLI client already bundled ==="
    echo "  bin/trusttunnel_client ($(du -sh bin/trusttunnel_client | cut -f1))"
fi

# 4. Build the .app in an ephemeral uv environment (pyinstaller only).
#    Runtime deps are vendored/stdlib (see requirements.txt), so the build
#    env needs nothing but PyInstaller. tkinter comes from the interpreter.
echo ""
echo "=== Building .app (PyInstaller) ==="
uv run --no-project --python "$TT_PYTHON" --with pyinstaller \
    pyinstaller trusttunnel.spec --clean --noconfirm 2>&1

# 5. Result + optional install (same UX as build-app.sh).
echo ""
echo "=== Done ==="
APP="dist/TrustTunnel.app"
if [ ! -d "$APP" ]; then
    echo "ERROR: Build failed. Check output above."
    exit 1
fi

SIZE="$(du -sh "$APP" | cut -f1)"
echo "App:  $SCRIPT_DIR/$APP  ($SIZE)"
echo ""
echo "Copy to /Applications?"
read -p "  [Y/n]: " answer
if [ "${answer:-y}" = "y" ] || [ "${answer:-y}" = "Y" ] || [ -z "$answer" ]; then
    rm -rf /Applications/TrustTunnel.app
    cp -R "$APP" /Applications/
    echo "  → Copied to /Applications/TrustTunnel.app"

    # Auto-configure sudo if not already done.
    SUDOERS="/etc/sudoers.d/trusttunnel"
    if [ -f "$SUDOERS" ] && grep -q "trusttunnel_client" "$SUDOERS" 2>/dev/null; then
        echo "  → Sudo already configured."
    else
        echo ""
        echo "  TrustTunnel needs root to create a virtual network interface."
        echo "  Configure passwordless sudo for the VPN client?"
        read -p "  [Y/n]: " sudo_ans
        if [ "${sudo_ans:-y}" = "y" ] || [ "${sudo_ans:-y}" = "Y" ] || [ -z "$sudo_ans" ]; then
            "$SCRIPT_DIR/setup-sudo.sh"
        else
            echo "  (Skipped. Run ./setup-sudo.sh later.)"
        fi
    fi
else
    echo "  To install later: cp -r \"$APP\" /Applications/"
fi
echo ""
echo "To share: zip -r TrustTunnel-macOS.zip \"$APP\""
