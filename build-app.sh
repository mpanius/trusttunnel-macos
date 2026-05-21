#!/bin/bash
# Build TrustTunnel.app for macOS distribution
# Run this on your Mac (not on VPS — PyInstaller needs target OS)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== TrustTunnel macOS App Builder ==="
echo ""

# 1. Check Python and Tkinter
PYTHON=""
for candidate in /usr/local/bin/python3.11 /opt/homebrew/bin/python3.11 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    if [ -x "$candidate" ]; then
        ver=$("$candidate" -c "import tkinter; print(tkinter.TkVersion)" 2>/dev/null || echo "0")
        if [ "${ver%%.*}" -ge 8 ] && [ "${ver#*.}" -ge 6 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: No Python with Tkinter 8.6+ found."
    echo "Install: brew install python@3.11"
    exit 1
fi
echo "Python: $PYTHON (Tk $("$PYTHON" -c "import tkinter; print(tkinter.TkVersion)"))"

# 2. Install build deps
echo ""
echo "=== Installing build dependencies ==="
"$PYTHON" -m pip install --quiet pyinstaller toml

# 3. Generate icon (if no icon.icns exists)
if [ ! -f "icon.icns" ]; then
    echo ""
    echo "=== Generating icon ==="

    # Create a simple 1024x1024 PNG icon using Python + tkinter
    "$PYTHON" -c "
import tkinter as tk
import struct, zlib

SZ = 256
root = tk.Tk()
root.withdraw()
c = tk.Canvas(root, width=SZ, height=SZ, bg='white', highlightthickness=0)

# Shield shape
pts = [128,20, 236,80, 236,160, 190,190, 128,240, 66,190, 20,160, 20,80]
c.create_polygon(*pts, fill='#2563eb', outline='#1e40af', width=3, smooth=True)

# 'T' letter
c.create_text(128, 140, text='T', fill='white', font=('Helvetica', 80, 'bold'))

c.postscript(file='/tmp/tt_icon.ps', width=SZ, height=SZ)
root.destroy()
" 2>/dev/null && echo "PS generated" || echo "PS generation skipped (no display)"

    # Fallback: simple blue square PNG
    "$PYTHON" -c "
import struct, zlib
SZ = 512
raw = b''
for y in range(SZ):
    raw += b'\\x00'  # filter none
    for x in range(SZ):
        r, g, b, a = 37, 99, 235, 255  # blue
        raw += struct.pack('BBBB', r, g, b, a)

sig = b'\\x89PNG\\r\\n\\x1a\\n'
ihdr = struct.pack('>IIBBBBB', SZ, SZ, 8, 6, 0, 0, 0)
def chunk(t, d):
    return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
z = zlib.compress(raw)
png = sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', z) + chunk(b'IEND', b'')
with open('icon.png', 'wb') as f: f.write(png)
"
    echo "icon.png created"

    # Convert to .icns
    echo "To get a proper .icns: open icon.png in Preview, File > Export > Format: PNG,"
    echo "then in Terminal:"
    echo "  mkdir icon.iconset"
    echo "  sips -z 16 16   icon.png --out icon.iconset/icon_16x16.png"
    echo "  sips -z 32 32   icon.png --out icon.iconset/icon_16x16@2x.png"
    echo "  sips -z 32 32   icon.png --out icon.iconset/icon_32x32.png"
    echo "  sips -z 64 64   icon.png --out icon.iconset/icon_32x32@2x.png"
    echo "  sips -z 128 128 icon.png --out icon.iconset/icon_128x128.png"
    echo "  sips -z 256 256 icon.png --out icon.iconset/icon_128x128@2x.png"
    echo "  sips -z 256 256 icon.png --out icon.iconset/icon_256x256.png"
    echo "  sips -z 512 512 icon.png --out icon.iconset/icon_256x256@2x.png"
    echo "  sips -z 512 512 icon.png --out icon.iconset/icon_512x512.png"
    echo "  iconutil -c icns icon.iconset -o icon.icns"
    echo "  rm -rf icon.iconset"
fi

# 4. Build
echo ""
echo "=== Building .app ==="
"$PYTHON" -m PyInstaller trusttunnel.spec --clean --noconfirm 2>&1

# 5. Result
echo ""
echo "=== Done ==="
APP="dist/TrustTunnel.app"
if [ -d "$APP" ]; then
    SIZE=$(du -sh "$APP" | cut -f1)
    echo "App:  $SCRIPT_DIR/$APP  ($SIZE)"
    echo ""
    echo "To install:"
    echo "  cp -r \"$APP\" /Applications/"
    echo ""
    echo "To share with others:"
    echo "  zip -r TrustTunnel-macOS.zip \"$APP\""
else
    echo "ERROR: Build failed. Check output above."
    exit 1
fi
