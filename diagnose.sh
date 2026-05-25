#!/usr/bin/env bash
set -euo pipefail

section() { echo -e "\n=== $1 ==="; }

section "OS"
sw_vers

section "Python"
PYTHON_BIN=$(which python3 || which python || echo "none")
echo "Python binary: $PYTHON_BIN"
[[ -x "$PYTHON_BIN" ]] && "$PYTHON_BIN" -V 2>&1 && \
  "$PYTHON_BIN" -c "import tkinter; print(f'Tkinter version: {tkinter.TkVersion}')" || echo "Python not executable"

section "Tkinter (_tkinter)"
[[ -x "$PYTHON_BIN" ]] && \
  if "$PYTHON_BIN" -c "import _tkinter" 2>/dev/null; then
    echo "_tkinter imported successfully"
  else
    echo "_tkinter module NOT available"
    echo "Fix: brew reinstall python@3.11 --with-tcl-tk"
  fi || echo "No Python to test"

section "PyInstaller"
command -v pip3 >/dev/null && pip3 show pyinstaller || echo "pyinstaller not installed"

section "trusttunnel_client binary"
BIN_PATH="/Applications/TrustTunnelGUI.app/Contents/Resources/bin/trusttunnel_client"
if [[ -f "$BIN_PATH" ]]; then
  echo "Binary exists: $BIN_PATH"
  ls -l "$BIN_PATH"
  file "$BIN_PATH"
  [[ -x "$BIN_PATH" ]] && sudo "$BIN_PATH" --version || echo "Binary not executable"
else
  echo "Binary NOT found at $BIN_PATH"
fi

section "Sudoers NOPASSWD"
SUDOERS_FILE="/etc/sudoers.d/trusttunnel"
[[ -f "$SUDOERS_FILE" ]] && \
  grep -q "trusttunnel_client" "$SUDOERS_FILE" && \
  echo "NOPASSWD entry found" || echo "NOPASSWD entry MISSING"

section "App bundle"
APP_BUNDLE="/Applications/TrustTunnelGUI.app"
[[ -d "$APP_BUNDLE" ]] && \
  find "$APP_BUNDLE" -name "trusttunnel_client" -o -name "*.py" -o -name "*.icns" | head -10 || \
  echo "App bundle NOT found at $APP_BUNDLE"

section "Runtime test"
[[ -x "$BIN_PATH" ]] && \
  sudo "$BIN_PATH" --help >/dev/null 2>&1 && \
  echo "✓ trusttunnel_client runs successfully" || \
  echo "✗ trusttunnel_client failed to start"