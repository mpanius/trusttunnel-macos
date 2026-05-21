"""TrustTunnel macOS GUI — menu bar app with full protocol feature support."""

import os
import sys
import json
import subprocess
import webbrowser
from typing import Optional

import rumps

from .config import (
    ServerProfile, EndpointConfig, TunConfig, SocksConfig,
    load_servers, save_servers, parse_deeplink,
)
from .client import ClientManager, ClientState, ClientStatus

# ── icons (SF Symbols names via macOS) ──────────────────────────
ICON_DISCONNECTED = "🔒"
ICON_CHECKING = "🟡"
ICON_CONNECTING = "🟡"
ICON_CONNECTED = "🟢"
ICON_ERROR = "🔴"


class TrustTunnelApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="TrustTunnel",
            title=ICON_DISCONNECTED,
            icon=None,
            quit_button=None,
        )
        self.client = ClientManager()
        self.servers: list[ServerProfile] = load_servers()
        self.active_profile: Optional[ServerProfile] = None
        self.client.on_state_change(self._on_client_state)

        # Timer to update status periodically
        self.timer = rumps.Timer(self._update_title, 2)
        self.timer.start()

        self._build_menu()

    # ── Menu building ──────────────────────────────────────────

    def _build_menu(self):
        """Rebuild the entire menu."""
        self.menu.clear()

        # Connection status
        status = self.client.status
        phase_str = f" [{status.phase.value}]" if status.phase.value != "idle" else ""
        state_label = f"Status: {status.state.value}{phase_str}"
        self.menu.add(rumps.MenuItem(state_label, callback=None))

        # Server switcher
        server_menu = rumps.MenuItem("Servers")
        if not self.servers:
            server_menu.add(rumps.MenuItem("No servers configured", callback=None))
        else:
            for i, s in enumerate(self.servers):
                active_mark = " ✓" if (
                    self.active_profile and self.active_profile.name == s.name
                ) else ""
                server_menu.add(rumps.MenuItem(
                    f"{s.name}{active_mark}",
                    callback=self._make_server_callback(i),
                ))
        server_menu.add(rumps.separator)
        server_menu.add(rumps.MenuItem("Add Server...", callback=self._add_server))
        server_menu.add(rumps.MenuItem("Import from deep-link...", callback=self._import_deeplink))
        server_menu.add(rumps.MenuItem("Edit Server...", callback=self._edit_server))
        server_menu.add(rumps.MenuItem("Delete Server...", callback=self._delete_server))
        self.menu.add(server_menu)

        self.menu.add(rumps.separator)

        # Quick toggle: Connect/Disconnect
        if self.client.is_connected():
            self.menu.add(rumps.MenuItem(
                f"Disconnect from {self.active_profile.name if self.active_profile else 'VPN'}",
                callback=self._disconnect,
            ))
        else:
            self.menu.add(rumps.MenuItem("Quick Connect", callback=self._quick_connect))

        self.menu.add(rumps.separator)

        # Protocol options
        proto_menu = rumps.MenuItem("Protocol")
        proto_menu.add(rumps.MenuItem(
            "HTTP/2 (recommended)", callback=self._set_proto_http2,
        ))
        proto_menu.add(rumps.MenuItem(
            "HTTP/3 / QUIC", callback=self._set_proto_http3,
        ))
        self.menu.add(proto_menu)

        # Listener type
        listener_menu = rumps.MenuItem("Mode")
        listener_menu.add(rumps.MenuItem(
            "TUN (system-wide VPN)", callback=self._set_listener_tun,
        ))
        listener_menu.add(rumps.MenuItem(
            "SOCKS5 proxy", callback=self._set_listener_socks,
        ))
        self.menu.add(listener_menu)

        # Routing mode
        route_menu = rumps.MenuItem("Routing")
        route_menu.add(rumps.MenuItem(
            "General (route all)", callback=self._set_vpn_general,
        ))
        route_menu.add(rumps.MenuItem(
            "Selective (route only exclusions)", callback=self._set_vpn_selective,
        ))
        self.menu.add(route_menu)

        # Toggles
        self.menu.add(rumps.separator)
        ks_state = self.active_profile.killswitch_enabled if self.active_profile else True
        self.menu.add(rumps.MenuItem(
            f"Kill Switch: {'ON' if ks_state else 'OFF'}",
            callback=self._toggle_killswitch,
        ))
        pq_state = self.active_profile.post_quantum_group_enabled if self.active_profile else True
        self.menu.add(rumps.MenuItem(
            f"Post-Quantum: {'ON' if pq_state else 'OFF'}",
            callback=self._toggle_post_quantum,
        ))
        adpi = self.active_profile.endpoint.anti_dpi if self.active_profile else False
        self.menu.add(rumps.MenuItem(
            f"Anti-DPI: {'ON' if adpi else 'OFF'}",
            callback=self._toggle_anti_dpi,
        ))

        self.menu.add(rumps.separator)

        # DNS management
        self.menu.add(rumps.MenuItem("DNS Settings...", callback=self._dns_settings))

        # Split tunneling / exclusions
        self.menu.add(rumps.MenuItem("Exclusions...", callback=self._exclusions_editor))

        self.menu.add(rumps.separator)

        # Info
        self.menu.add(rumps.MenuItem("Connection Info", callback=self._show_info))
        self.menu.add(rumps.MenuItem("Connection Diagnostics", callback=self._show_diagnostics))
        self.menu.add(rumps.MenuItem("View Logs", callback=self._show_logs))
        self.menu.add(rumps.MenuItem("Open Config Folder", callback=self._open_config_folder))
        self.menu.add(rumps.MenuItem("Check for Updates", callback=self._check_updates))

        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("About TrustTunnel GUI", callback=self._about))
        self.menu.add(rumps.MenuItem("Quit", callback=self._quit))

    # ── State updates ──────────────────────────────────────────

    def _on_client_state(self, status: ClientStatus):
        """Called when client state changes."""
        if status.state == ClientState.CONNECTED:
            self.title = ICON_CONNECTED
        elif status.state == ClientState.CONNECTING:
            self.title = ICON_CONNECTING
        elif status.state == ClientState.CHECKING:
            self.title = ICON_CHECKING
        elif status.state == ClientState.ERROR:
            self.title = ICON_ERROR
        else:
            self.title = ICON_DISCONNECTED
        self._build_menu()

    def _update_title(self, _):
        """Periodic status refresh."""
        status = self.client.status
        if status.state == ClientState.CONNECTED:
            self.title = ICON_CONNECTED
        elif status.state == ClientState.CONNECTING:
            self.title = ICON_CONNECTING
        elif status.state == ClientState.CHECKING:
            self.title = ICON_CHECKING
        elif status.state == ClientState.ERROR:
            self.title = ICON_ERROR
        else:
            self.title = ICON_DISCONNECTED

    # ── Server callbacks ───────────────────────────────────────

    def _make_server_callback(self, index: int):
        def cb(_):
            profile = self.servers[index]
            self._connect_to(profile)
        return cb

    def _connect_to(self, profile: ServerProfile):
        self.active_profile = profile
        save_servers(self.servers)
        rumps.notification(
            "TrustTunnel",
            f"Connecting to {profile.name}...",
            f"{profile.endpoint.hostname}",
        )
        success = self.client.connect(profile)
        if success:
            self._build_menu()
        else:
            self._build_menu()
            # Auto-show diagnostics on failure
            self._show_diagnostics(None)

    def _quick_connect(self, _):
        if not self.servers:
            rumps.alert("No servers configured. Add one first.")
            return
        if len(self.servers) == 1:
            self._connect_to(self.servers[0])
        else:
            # Show submenu-like picker via alert
            names = [s.name for s in self.servers]
            choice = rumps.alert(
                title="Select Server",
                message="\n".join(f"{i+1}. {n}" for i, n in enumerate(names)),
                ok="Cancel",
            )

    def _disconnect(self, _):
        self.client.disconnect()
        self.active_profile = None
        self._build_menu()
        rumps.notification("TrustTunnel", "Disconnected", "")

    def _add_server(self, _):
        """Open server editor window."""
        resp = rumps.Window(
            title="Add TrustTunnel Server",
            message=(
                "Enter server details:\n\n"
                "Name, Hostname, Address (ip:port), Username, Password\n"
                "Separate multiple addresses with commas."
            ),
            default_text="My Server\nvpn.example.com\n192.168.1.1:443\nmyuser\nmypassword",
            dimensions=(400, 200),
        ).run()

        if not resp.clicked or not resp.text.strip():
            return

        lines = resp.text.strip().split("\n")
        if len(lines) < 4:
            rumps.alert("Need at least: name, hostname, address, username, password")
            return

        name = lines[0].strip()
        hostname = lines[1].strip()
        addresses = [a.strip() for a in lines[2].split(",") if a.strip()]
        username = lines[3].strip()
        password = lines[4].strip() if len(lines) > 4 else ""

        profile = ServerProfile(
            name=name,
            endpoint=EndpointConfig(
                hostname=hostname,
                addresses=addresses,
                username=username,
                password=password,
            ),
        )
        self.servers.append(profile)
        save_servers(self.servers)
        self._build_menu()

    def _import_deeplink(self, _):
        """Import server from tt://? deep-link from clipboard."""
        try:
            clipboard = subprocess.check_output(
                ["pbpaste"], text=True
            ).strip()
        except Exception:
            clipboard = ""

        resp = rumps.Window(
            title="Import Deep-Link",
            message=(
                "Paste a tt://? deep-link URI or TOML config.\n"
                "The clipboard contents are pre-filled below."
            ),
            default_text=clipboard,
            dimensions=(500, 200),
        ).run()

        if not resp.clicked or not resp.text.strip():
            return

        uri = resp.text.strip()
        profile = parse_deeplink(uri)
        if profile:
            self.servers.append(profile)
            save_servers(self.servers)
            rumps.notification("TrustTunnel", f"Imported: {profile.name}", "")
        else:
            rumps.alert("Could not parse deep-link. Check format.")

        self._build_menu()

    def _edit_server(self, _):
        if not self.servers:
            rumps.alert("No servers to edit.")
            return
        names = [s.name for s in self.servers]
        choice = rumps.alert(
            title="Edit Server",
            message="Which server?",
            ok=None,
            cancel="Cancel",
            other=names,
        )
        # rumps alert returns index of button clicked
        # This is limited — for a real app we'd use a proper selector

    def _delete_server(self, _):
        if not self.servers:
            return
        names = [s.name for s in self.servers]
        choice = rumps.alert(
            title="Delete Server",
            message="Select server to delete:",
            ok=None,
            cancel="Cancel",
            other=names,
        )

    # ── Settings callbacks ─────────────────────────────────────

    def _set_proto_http2(self, _):
        if self.active_profile:
            self.active_profile.endpoint.upstream_protocol = "http2"
            save_servers(self.servers)
            self._build_menu()
            if self.client.is_connected():
                rumps.alert("Reconnect for protocol change to take effect.")

    def _set_proto_http3(self, _):
        if self.active_profile:
            self.active_profile.endpoint.upstream_protocol = "http3"
            save_servers(self.servers)
            self._build_menu()
            if self.client.is_connected():
                rumps.alert("Reconnect for protocol change to take effect.")

    def _set_listener_tun(self, _):
        if not self.active_profile:
            rumps.alert("Connect to a server first.")
            return
        self.active_profile.listener_type = "tun"
        save_servers(self.servers)
        self._build_menu()
        if self.client.is_connected():
            rumps.alert("Reconnect to switch to TUN mode.")

    def _set_listener_socks(self, _):
        if not self.active_profile:
            rumps.alert("Connect to a server first.")
            return
        self.active_profile.listener_type = "socks"
        save_servers(self.servers)
        self._build_menu()
        if self.client.is_connected():
            rumps.alert("Reconnect to switch to SOCKS5 mode.")

    def _set_vpn_general(self, _):
        if self.active_profile:
            self.active_profile.vpn_mode = "general"
            save_servers(self.servers)
            self._build_menu()

    def _set_vpn_selective(self, _):
        if self.active_profile:
            self.active_profile.vpn_mode = "selective"
            save_servers(self.servers)
            self._build_menu()

    def _toggle_killswitch(self, _):
        if not self.active_profile:
            return
        self.active_profile.killswitch_enabled = not self.active_profile.killswitch_enabled
        save_servers(self.servers)
        self._build_menu()

    def _toggle_post_quantum(self, _):
        if not self.active_profile:
            return
        self.active_profile.post_quantum_group_enabled = (
            not self.active_profile.post_quantum_group_enabled
        )
        save_servers(self.servers)
        self._build_menu()

    def _toggle_anti_dpi(self, _):
        if not self.active_profile:
            return
        self.active_profile.endpoint.anti_dpi = not self.active_profile.endpoint.anti_dpi
        save_servers(self.servers)
        self._build_menu()

    def _dns_settings(self, _):
        if not self.active_profile:
            rumps.alert("Connect to a server first.")
            return
        current = "\n".join(self.active_profile.endpoint.dns_upstreams) or "(AdGuard DNS)"
        resp = rumps.Window(
            title="DNS Upstreams",
            message=(
                "Enter DNS servers, one per line:\n"
                "  8.8.8.8           — plain UDP\n"
                "  tls://1.1.1.1      — DNS over TLS\n"
                "  https://dns.adguard.com/dns-query  — DNS over HTTPS\n"
                "  quic://dns.adguard.com:8853        — DNS over QUIC\n"
                "  tcp://8.8.8.8:53   — DNS over TCP\n"
                "Leave empty for AdGuard DNS default."
            ),
            default_text=current,
            dimensions=(500, 250),
        ).run()
        if resp.clicked:
            upstreams = [l.strip() for l in resp.text.strip().split("\n") if l.strip()]
            if upstreams == ["(AdGuard DNS)"]:
                upstreams = []
            self.active_profile.endpoint.dns_upstreams = upstreams
            save_servers(self.servers)

    def _exclusions_editor(self, _):
        if not self.active_profile:
            rumps.alert("Connect to a server first.")
            return
        current = "\n".join(self.active_profile.exclusions) or "(none)"
        resp = rumps.Window(
            title="Split Tunneling Exclusions",
            message=(
                "Enter domains/IPs/CIDRs to exclude/route, one per line:\n"
                "  example.com   — domain\n"
                "  *.google.com  — wildcard\n"
                "  192.168.0.0/16 — CIDR\n"
                "  *:443         — all port 443 traffic"
            ),
            default_text=current,
            dimensions=(500, 250),
        ).run()
        if resp.clicked:
            exclusions = [l.strip() for l in resp.text.strip().split("\n") if l.strip()]
            if exclusions == ["(none)"]:
                exclusions = []
            self.active_profile.exclusions = exclusions
            save_servers(self.servers)

    # ── Info / Utility ─────────────────────────────────────────

    def _show_info(self, _):
        status = self.client.status
        info = [
            f"State: {status.state.value}",
            f"Phase: {status.phase.value}",
            f"Server: {status.server_name or 'N/A'}",
            f"Uptime: {int(status.uptime)}s",
        ]
        if status.started_at:
            info.append(f"Started: {status.started_at.strftime('%H:%M:%S')}")
        if self.active_profile:
            info += [
                f"Protocol: {self.active_profile.endpoint.upstream_protocol}",
                f"Mode: {self.active_profile.listener_type}",
                f"VPN Mode: {self.active_profile.vpn_mode}",
                f"Kill Switch: {'ON' if self.active_profile.killswitch_enabled else 'OFF'}",
                f"Post-Quantum: {'ON' if self.active_profile.post_quantum_group_enabled else 'OFF'}",
                f"Anti-DPI: {'ON' if self.active_profile.endpoint.anti_dpi else 'OFF'}",
            ]
        if status.error:
            info.append(f"\nError: {status.error}")
        rumps.alert(title="Connection Info", message="\n".join(info))

    def _show_diagnostics(self, _):
        """Show full connection attempt log with phase markers."""
        status = self.client.status
        lines = [
            "═══════════ CONNECTION DIAGNOSTICS ═══════════",
            f"State:  {status.state.value}",
            f"Phase:  {status.phase.value}",
            f"Server: {status.server_name or 'N/A'}",
            f"Error:  {status.error or '(none)'}",
            "",
            "─── Step-by-step log ───",
            self.client.get_full_logs() or "(no log entries — no connection attempted yet)",
            "",
            "─── Tip ───",
            "• If 'sudo requires password': add NOPASSWD to /etc/sudoers",
            "• If 'binary not found': run install script from TrustTunnelClient repo",
            "• Check server address and port are correct",
            "• Try 'View Logs' for live client output after connecting",
        ]
        rumps.Window(
            title="Connection Diagnostics",
            message="\n".join(lines),
            dimensions=(650, 450),
            ok="Close",
        ).run()

    def _show_logs(self, _):
        logs = self.client.get_logs(60)
        status = self.client.status
        header = (
            f"State: {status.state.value} | Phase: {status.phase.value}\n"
            f"Recent output from trusttunnel_client:\n"
            f"{'═' * 40}"
        )
        rumps.Window(
            title="Client Runtime Logs",
            message=header,
            default_text=logs or "(no output yet)",
            dimensions=(700, 450),
            ok="Close",
        ).run()

    def _open_config_folder(self, _):
        from .config import APP_DIR
        os.makedirs(APP_DIR, exist_ok=True)
        subprocess.Popen(["open", APP_DIR])

    def _check_updates(self, _):
        rumps.alert(
            title="Check for Updates",
            message="Visit https://github.com/TrustTunnel/TrustTunnel/releases",
        )

    def _about(self, _):
        rumps.alert(
            title="TrustTunnel macOS GUI",
            message=(
                "A native-feeling macOS menu bar client for the TrustTunnel VPN protocol.\n\n"
                "Features:\n"
                "• HTTP/2 & HTTP/3 (QUIC) support\n"
                "• TUN system-wide VPN & SOCKS5 proxy\n"
                "• Split tunneling with exclusion lists\n"
                "• Custom DNS (DoH, DoT, DoQ, plain)\n"
                "• Kill switch, post-quantum, anti-DPI\n"
                "• Deep-link import (tt://?)\n"
                "• Multi-server profile management\n\n"
                "Built with rumps (Python) + trusttunnel_client"
            ),
        )

    def _quit(self, _):
        if self.client.is_connected():
            resp = rumps.alert(
                title="Disconnect?",
                message="VPN is connected. Disconnect before quitting?",
                ok="Disconnect & Quit",
                cancel="Cancel",
                other="Quit Anyway",
            )
        self.client.disconnect()
        rumps.quit_application()


def main():
    TrustTunnelApp().run()


if __name__ == "__main__":
    main()
