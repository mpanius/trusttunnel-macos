# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for TrustTunnel macOS app.

Build:
    pip install pyinstaller toml
    pyinstaller trusttunnel.spec

Output: dist/TrustTunnel.app  (double-clickable, no terminal)
"""

import sys
from pathlib import Path

# Detect tkinter location for macOS Homebrew
_tk_lib = None
for candidate in [
    "/usr/local/opt/python-tk@3.11/lib",
    "/usr/local/opt/tcl-tk/lib",
    "/opt/homebrew/opt/tcl-tk/lib",
    "/opt/homebrew/opt/python-tk@3.11/lib",
]:
    if Path(candidate).exists():
        _tk_lib = candidate
        break

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("src", "src"),              # all source code
    ],
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "toml",
        "base64",
        "threading",
        "json",
        "re",
        "subprocess",
        "tempfile",
        "signal",
        "datetime",
        "urllib.parse",
        "pathlib",
        "enum",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TrustTunnel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # No terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.icns" if Path("icon.icns").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TrustTunnel",
)

app = BUNDLE(
    coll,
    name="TrustTunnel.app",
    icon="icon.icns" if Path("icon.icns").exists() else None,
    bundle_identifier="com.trusttunnel.gui",
    info_plist={
        "NSHighResolutionCapable": True,
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "CFBundleName": "TrustTunnel",
        "CFBundleDisplayName": "TrustTunnel VPN",
        "LSMinimumSystemVersion": "10.15",
        "NSRequiresAquaSystemAppearance": False,
    },
)
