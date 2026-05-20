"""TrustTunnel config manager — TOML read/write, server profiles, deep-link import."""

import os
import re
import toml
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import parse_qs, urlparse


APP_DIR = os.path.expanduser("~/.trusttunnel-gui")
SERVERS_FILE = os.path.join(APP_DIR, "servers.toml")


@dataclass
class EndpointConfig:
    hostname: str
    addresses: list[str] = field(default_factory=list)
    username: str = ""
    password: str = ""
    has_ipv6: bool = True
    client_random: str = ""
    skip_verification: bool = False
    certificate: str = ""
    upstream_protocol: str = "http2"       # http2 | http3
    anti_dpi: bool = False
    dns_upstreams: list[str] = field(default_factory=list)


@dataclass
class TunConfig:
    bound_if: str = ""
    included_routes: list[str] = field(default_factory=lambda: ["0.0.0.0/0", "2000::/3"])
    excluded_routes: list[str] = field(default_factory=lambda: [
        "0.0.0.0/8", "10.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/3"
    ])
    mtu_size: int = 1280
    tcp_recv_buf_size: int = 0
    tcp_send_buf_size: int = 0
    change_system_dns: bool = True
    device_name: str = ""


@dataclass
class SocksConfig:
    address: str = "127.0.0.1:1080"
    username: str = ""
    password: str = ""


@dataclass
class ServerProfile:
    name: str
    endpoint: EndpointConfig = field(default_factory=EndpointConfig)
    tun: TunConfig = field(default_factory=TunConfig)
    socks: SocksConfig = field(default_factory=SocksConfig)
    vpn_mode: str = "general"              # general | selective
    killswitch_enabled: bool = True
    killswitch_allow_ports: list[int] = field(default_factory=list)
    post_quantum_group_enabled: bool = True
    exclusions: list[str] = field(default_factory=list)
    loglevel: str = "info"
    listener_type: str = "tun"              # tun | socks

    def to_client_toml(self) -> str:
        """Generate a valid trusttunnel_client TOML config string."""
        cfg = {
            "loglevel": self.loglevel,
            "vpn_mode": self.vpn_mode,
            "killswitch_enabled": self.killswitch_enabled,
            "killswitch_allow_ports": self.killswitch_allow_ports,
            "post_quantum_group_enabled": self.post_quantum_group_enabled,
            "exclusions": self.exclusions,
            "dns_upstreams": self.endpoint.dns_upstreams,
        }
        cfg["endpoint"] = {
            "hostname": self.endpoint.hostname,
            "addresses": self.endpoint.addresses,
            "has_ipv6": self.endpoint.has_ipv6,
            "username": self.endpoint.username,
            "password": self.endpoint.password,
            "client_random": self.endpoint.client_random,
            "skip_verification": self.endpoint.skip_verification,
            "upstream_protocol": self.endpoint.upstream_protocol,
            "anti_dpi": self.endpoint.anti_dpi,
            "dns_upstreams": self.endpoint.dns_upstreams,
        }
        if self.endpoint.certificate:
            cfg["endpoint"]["certificate"] = self.endpoint.certificate

        if self.listener_type == "tun":
            cfg["listener"] = {"tun": asdict(self.tun)}
        else:
            cfg["listener"] = {"socks": asdict(self.socks)}

        return toml.dumps(cfg)


def parse_deeplink(uri: str) -> Optional[ServerProfile]:
    """Parse a tt://? deeplink URI into a ServerProfile.

    Format: tt://?<base64-encoded-toml>
    or:     tt://?name=...&hostname=...&addresses=...&username=...&password=...
    """
    if not uri.startswith("tt://?"):
        return None

    qs = uri[6:]  # strip "tt://?"

    # URL-encoded key=value format
    parsed = parse_qs(qs)
    if "hostname" in parsed:
        name = parsed.get("name", ["TrustTunnel Server"])[0]
        hostname = parsed.get("hostname", [""])[0]
        addresses_raw = parsed.get("addresses", [""])[0]
        addresses = [a.strip() for a in addresses_raw.split(",") if a.strip()]

        ep = EndpointConfig(
            hostname=hostname,
            addresses=addresses,
            username=parsed.get("username", [""])[0],
            password=parsed.get("password", [""])[0],
            client_random=parsed.get("client_random", [""])[0],
            certificate=parsed.get("certificate", [""])[0],
            skip_verification=parsed.get("skip_verification", ["false"])[0].lower() == "true",
            upstream_protocol=parsed.get("upstream_protocol", ["http2"])[0],
            anti_dpi=parsed.get("anti_dpi", ["false"])[0].lower() == "true",
        )
        if "dns_upstream" in parsed:
            ep.dns_upstreams = parsed["dns_upstream"]

        return ServerProfile(name=name, endpoint=ep)

    return None


def load_servers() -> list[ServerProfile]:
    """Load saved server profiles from disk."""
    os.makedirs(APP_DIR, exist_ok=True)
    if not os.path.exists(SERVERS_FILE):
        return []
    try:
        data = toml.load(SERVERS_FILE)
        profiles = []
        for s in data.get("servers", []):
            ep_data = s.get("endpoint", {})
            ep = EndpointConfig(
                hostname=ep_data.get("hostname", ""),
                addresses=ep_data.get("addresses", []),
                username=ep_data.get("username", ""),
                password=ep_data.get("password", ""),
                has_ipv6=ep_data.get("has_ipv6", True),
                client_random=ep_data.get("client_random", ""),
                skip_verification=ep_data.get("skip_verification", False),
                certificate=ep_data.get("certificate", ""),
                upstream_protocol=ep_data.get("upstream_protocol", "http2"),
                anti_dpi=ep_data.get("anti_dpi", False),
                dns_upstreams=ep_data.get("dns_upstreams", []),
            )
            tun_data = s.get("tun", {})
            tun = TunConfig(
                bound_if=tun_data.get("bound_if", ""),
                included_routes=tun_data.get("included_routes", ["0.0.0.0/0", "2000::/3"]),
                excluded_routes=tun_data.get("excluded_routes", []),
                mtu_size=tun_data.get("mtu_size", 1280),
                tcp_recv_buf_size=tun_data.get("tcp_recv_buf_size", 0),
                tcp_send_buf_size=tun_data.get("tcp_send_buf_size", 0),
                change_system_dns=tun_data.get("change_system_dns", True),
                device_name=tun_data.get("device_name", ""),
            )
            socks_data = s.get("socks", {})
            socks = SocksConfig(
                address=socks_data.get("address", "127.0.0.1:1080"),
                username=socks_data.get("username", ""),
                password=socks_data.get("password", ""),
            )
            profiles.append(ServerProfile(
                name=s.get("name", "Unnamed"),
                endpoint=ep, tun=tun, socks=socks,
                vpn_mode=s.get("vpn_mode", "general"),
                killswitch_enabled=s.get("killswitch_enabled", True),
                killswitch_allow_ports=s.get("killswitch_allow_ports", []),
                post_quantum_group_enabled=s.get("post_quantum_group_enabled", True),
                exclusions=s.get("exclusions", []),
                loglevel=s.get("loglevel", "info"),
                listener_type=s.get("listener_type", "tun"),
            ))
        return profiles
    except Exception:
        return []


def save_servers(profiles: list[ServerProfile]):
    """Save server profiles to disk."""
    os.makedirs(APP_DIR, exist_ok=True)
    data = {"servers": []}
    for p in profiles:
        data["servers"].append({
            "name": p.name,
            "vpn_mode": p.vpn_mode,
            "killswitch_enabled": p.killswitch_enabled,
            "killswitch_allow_ports": p.killswitch_allow_ports,
            "post_quantum_group_enabled": p.post_quantum_group_enabled,
            "exclusions": p.exclusions,
            "loglevel": p.loglevel,
            "listener_type": p.listener_type,
            "endpoint": {
                "hostname": p.endpoint.hostname,
                "addresses": p.endpoint.addresses,
                "username": p.endpoint.username,
                "password": p.endpoint.password,
                "has_ipv6": p.endpoint.has_ipv6,
                "client_random": p.endpoint.client_random,
                "skip_verification": p.endpoint.skip_verification,
                "certificate": p.endpoint.certificate,
                "upstream_protocol": p.endpoint.upstream_protocol,
                "anti_dpi": p.endpoint.anti_dpi,
                "dns_upstreams": p.endpoint.dns_upstreams,
            },
            "tun": asdict(p.tun),
            "socks": asdict(p.socks),
        })
    with open(SERVERS_FILE, "w") as f:
        toml.dump(data, f)
