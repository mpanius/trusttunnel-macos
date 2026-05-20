# TrustTunnel macOS GUI

A native-feeling macOS menu bar client for the [TrustTunnel VPN protocol](https://github.com/TrustTunnel/TrustTunnel).

Sits in your menu bar. Connect/disconnect in one click. Full protocol features exposed.

## Features

- **HTTP/2 & HTTP/3 (QUIC)** protocol support
- **TUN system-wide VPN** — routes all traffic through the tunnel
- **SOCKS5 proxy mode** — per-app routing
- **Split tunneling** with domain/IP/CIDR exclusion lists (general & selective modes)
- **Custom DNS** — plain UDP, DNS over TLS (DoT), DNS over HTTPS (DoH), DNS over QUIC (DoQ), DNS over TCP
- **Kill switch** — blocks traffic when VPN disconnects
- **Post-quantum key exchange** — X25519Kyber768
- **Anti-DPI** — deep packet inspection evasion
- **Deep-link import** — paste `tt://?` URIs from endpoint exports
- **Multi-server profile management** — save, edit, switch between servers

## Requirements

- macOS 12 (Monterey) or later
- Python 3.9+
- [TrustTunnel CLI Client](https://github.com/TrustTunnel/TrustTunnelClient) installed

## Quick Install

```bash
# 1. Install TrustTunnel CLI client
curl -fsSL https://raw.githubusercontent.com/TrustTunnel/TrustTunnelClient/refs/heads/master/scripts/install.sh | sh -s -

# 2. Install this GUI
git clone https://github.com/YOUR_USER/trusttunnel-macos.git
cd trusttunnel-macos
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### Run

```bash
# From the project directory with venv active:
python3 -m src.app

# Or if installed via pip:
trusttunnel-gui
```

### Auto-start on login

Add to System Settings → General → Login Items:
- Application: `/path/to/trusttunnel-macos/.venv/bin/python3`
- Arguments: `-m src.app`

Or use the included launch agent:

```bash
mkdir -p ~/Library/LaunchAgents
cp com.trusttunnel.gui.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.trusttunnel.gui.plist
```

Edit the plist to match your install path first.

## Usage

1. Click the 🔒 icon in your menu bar
2. **Servers → Add Server** — enter your endpoint details
3. Or **Servers → Import from deep-link** — paste a `tt://?` URI
4. Click your server name to connect
5. Toggle settings (protocol, kill switch, DNS, exclusions) while connected

### Adding a server manually

```
Name: My VPN
Hostname: vpn.example.com
Address: 192.168.1.100:443
Username: myuser
Password: mypassword
```

### Importing from endpoint

On your TrustTunnel endpoint, export a client config:

```bash
cd /opt/trusttunnel
./trusttunnel_endpoint vpn.toml hosts.toml -c my-client -a vpn.example.com
```

This prints a `tt://?` URI. Copy it, then in the GUI: Servers → Import from deep-link.

## Architecture

```
┌─────────────────────────────────────┐
│  trusttunnel-macos (rumps menu bar) │
│  ┌───────────┐  ┌────────────────┐  │
│  │ config.py │  │  client.py     │  │
│  │ (TOML)    │  │  (subprocess)  │  │
│  └───────────┘  └───────┬────────┘  │
│                         │           │
│                 sudo trusttunnel_   │
│                 client -c config    │
└─────────────────────────┼───────────┘
                          │
                   ┌──────▼──────┐
                   │  TUN device │
                   │  or SOCKS5  │
                   └─────────────┘
```

Settings stored in `~/.trusttunnel-gui/servers.toml`.

## License

Apache 2.0 — same as TrustTunnel.
