# TrustTunnel macOS GUI

A native macOS windowed client for the [TrustTunnel VPN protocol](https://github.com/TrustTunnel/TrustTunnel).
Dark-themed, with server management, split tunneling, and embedded console.

## Features

- **Windowed UI** — traditional macOS window with resizable server list and console
- **Multi-server profiles** — add, edit, delete, import from `tt://?` deep-links
- **Tabs** — Servers (manage connections) + Bypass (split tunneling exclusion masks)
- **Split tunneling** — bypass VPN for specific domains: `*.ru`, `*.example.com`, CIDR, `*:port`
- **Embedded console** — real-time VPN output in-app, no separate terminal
- **Kill switch, Post-Quantum, Anti-DPI** — full protocol feature support
- **HTTP/2 & HTTP/3 (QUIC)** protocol selection
- **DNS configuration** — plain UDP, DoT, DoH, DoQ, DoTCP
- **Deep-link import** — paste `tt://?` URIs from endpoint exports (TOML-base64 + native TLV)

## Requirements

- macOS 11 (Big Sur) or later
- No other dependencies — TrustTunnel CLI client is bundled in the .app
- **Sudo setup** (one-time, see below)

## Why sudo?

TrustTunnel creates a virtual network interface (`utun`) for system-wide VPN routing.
This requires root privileges. There are only three ways to do this on macOS:

| Approach | Effort | Security | Status |
|---|---|---|---|
| **sudoers NOPASSWD** | 1 command | ★★★★ | ✅ This app |
| SUID bit (`chmod u+s`) | 1 command | ★★★ | ⚠️ macOS strips SUID on .app bundles |
| Privileged Helper (SMJobBless) | Apple dev account + code signing | ★★★★★ | 🔮 v2 roadmap |

This app uses **sudoers NOPASSWD** — the standard approach for tools like Wireshark, VirtualBox, and Docker.

## Sudo setup (one-time, 30 seconds)

```bash
./setup-sudo.sh
```

Or manually:

```bash
sudo bash -c 'echo "$(whoami) ALL=(ALL) NOPASSWD: /Applications/TrustTunnel.app/Contents/Resources/bin/trusttunnel_client" > /etc/sudoers.d/trusttunnel'
```

What this does: tells macOS "user X can run this specific binary as root without a password."
It is NOT a blanket "run anything as root" — only that one binary.

After setup, TrustTunnel.app works without any password prompts.

## Install (pre-built .app)

Download the latest `TrustTunnel.app` from [Releases](https://github.com/inhale/trusttunnel-macos/releases),
drag to `/Applications`, double-click. No terminal, no Python, no CLI client needed.

## Build from source

Requires Python 3.11+ with Tkinter 8.6+ (Homebrew Python recommended):

```bash
# 1. Clone
git clone https://github.com/inhale/trusttunnel-macos.git
cd trusttunnel-macos

# 2. One-command build
./build-app.sh
```

Output: `dist/TrustTunnel.app` — double-click to run.

### Dev run (no build)

```bash
# Install deps
/usr/local/bin/python3.11 -m pip install toml

# Run
/usr/local/bin/python3.11 -m src
```

## Usage

1. Launch TrustTunnel.app (or `python3 -m src`)
2. **Servers tab** → + Add — fill in name, hostname, address, username, password
3. Or **Import Link** — paste a `tt://?` deep-link from your endpoint
4. Select a server → **Connect**
5. **Bypass tab** — add domain masks (`*.ru`, `*.example.com`) to exclude from VPN

### Exporting deep-link from your endpoint

```bash
cd /opt/trusttunnel
sudo ./trusttunnel_endpoint vpn.toml hosts.toml -c myuser -a <PUBLIC_IP>:8443
```

Copy the `tt://?` URI, use Import Link in the app.

### Bypass / Split Tunneling

In the **Bypass** tab, add exclusion masks. These sites will NOT go through the VPN:

| Mask | Effect |
|---|---|
| `*.ru` | All `.ru` domains bypass |
| `*.google.com` | Google services bypass |
| `192.168.0.0/16` | Local network bypass |
| `*:443` | All HTTPS traffic bypass |

## File locations

- Settings: `~/.trusttunnel-gui/servers.toml`
- Build output: `dist/TrustTunnel.app`

## Architecture

```
TrustTunnel.app
├── src/app.py         — Tkinter window, tabs, UI
├── src/client.py      — trusttunnel_client subprocess manager
├── src/config.py      — TOML profiles, deep-link parser
├── trusttunnel.spec   — PyInstaller build config
└── build-app.sh       — one-command .app builder
```

## License

Apache 2.0 — same as TrustTunnel.
