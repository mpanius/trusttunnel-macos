"""TrustTunnel client process manager — manages the trusttunnel_client subprocess.

Now with pre-flight checks, phased connection progress, and rich diagnostics.
"""

import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Thread, Lock
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ServerProfile


CLIENT_BINARY_PATHS = [
    "/opt/trusttunnel_client/trusttunnel_client",
    "/usr/local/bin/trusttunnel_client",
    "trusttunnel_client",
]


class ClientState(Enum):
    DISCONNECTED = "disconnected"
    CHECKING = "checking"          # pre-flight checks
    CONNECTING = "connecting"       # process started, waiting for tunnel
    CONNECTED = "connected"
    ERROR = "error"


class ConnectPhase(Enum):
    """Granular connection phase for diagnostics."""
    IDLE = "idle"
    FINDING_BINARY = "finding binary"
    CHECKING_SUDO = "checking sudo"
    WRITING_CONFIG = "writing config"
    SPAWNING_PROCESS = "spawning process"
    WAITING_TUNNEL = "waiting for tunnel"
    TUNNEL_UP = "tunnel up"
    FAILED = "failed"


@dataclass
class ClientStatus:
    state: ClientState = ClientState.DISCONNECTED
    phase: ConnectPhase = ConnectPhase.IDLE
    server_name: str = ""
    uptime: float = 0.0
    error: str = ""
    rx_bytes: int = 0
    tx_bytes: int = 0
    log_lines: list[str] = field(default_factory=list)
    started_at: Optional[datetime] = None


class ClientManager:
    """Manages the trusttunnel_client process lifecycle."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._status = ClientStatus()
        self._lock = Lock()
        self._start_time: float = 0.0
        self._state_callbacks: list[Callable[[ClientStatus], None]] = []
        self._reader_thread: Optional[Thread] = None
        self._config_path: Optional[str] = None
        self._last_connect_log: list[str] = []

    @property
    def status(self) -> ClientStatus:
        with self._lock:
            return ClientStatus(
                state=self._status.state,
                phase=self._status.phase,
                server_name=self._status.server_name,
                uptime=time.time() - self._start_time if self._start_time else 0.0,
                error=self._status.error,
                rx_bytes=self._status.rx_bytes,
                tx_bytes=self._status.tx_bytes,
                log_lines=list(self._status.log_lines),
                started_at=self._status.started_at,
            )

    def on_state_change(self, callback: Callable[[ClientStatus], None]):
        self._state_callbacks.append(callback)

    def _notify(self):
        status = self.status
        for cb in self._state_callbacks:
            try:
                cb(status)
            except Exception:
                pass

    def _set_phase(self, phase: ConnectPhase):
        with self._lock:
            self._status.phase = phase
            self._status.log_lines.append(
                f"[{_ts()}] {phase.value}"
            )
        self._notify()

    def _find_binary(self) -> Optional[str]:
        self._set_phase(ConnectPhase.FINDING_BINARY)
        for path in CLIENT_BINARY_PATHS:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        for path in os.environ.get("PATH", "").split(":"):
            candidate = os.path.join(path, "trusttunnel_client")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    def _check_sudo(self) -> tuple[bool, str]:
        """Verify sudo is available (non-interactive check)."""
        self._set_phase(ConnectPhase.CHECKING_SUDO)
        try:
            result = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return True, "sudo available (passwordless)"
            else:
                return False, (
                    "sudo requires a password or is not configured.\n\n"
                    "Fix: add this line to /etc/sudoers via 'sudo visudo':\n"
                    "  YOUR_USER  ALL=(ALL) NOPASSWD: /usr/local/bin/trusttunnel_client, "
                    "/opt/trusttunnel_client/trusttunnel_client\n\n"
                    f"stderr: {result.stderr.strip()}"
                )
        except FileNotFoundError:
            return False, "'sudo' command not found on this system"
        except subprocess.TimeoutExpired:
            return False, "sudo check timed out (hung waiting for password prompt?)"

    def connect(self, profile: "ServerProfile") -> bool:
        """Start the VPN connection with full diagnostics."""

        if self.is_connected():
            self.disconnect()
            time.sleep(0.5)

        with self._lock:
            self._status.state = ClientState.CHECKING
            self._status.server_name = profile.name
            self._status.error = ""
            self._status.log_lines = []
            self._status.phase = ConnectPhase.IDLE
            self._status.started_at = datetime.now()
        self._notify()

        # ── Pre-flight 1: find binary ──
        binary = self._find_binary()
        if not binary:
            self._set_error(
                "trusttunnel_client not found.\n\n"
                "Searched:\n  " + "\n  ".join(CLIENT_BINARY_PATHS) + "\n"
                "and all directories in $PATH.\n\n"
                "Install: curl -fsSL https://raw.githubusercontent.com/"
                "TrustTunnel/TrustTunnelClient/refs/heads/master/scripts/install.sh | sh -s -"
            )
            return False

        # ── Pre-flight 2: sudo check ──
        sudo_ok, sudo_msg = self._check_sudo()
        if not sudo_ok:
            self._set_error(f"sudo check failed:\n{sudo_msg}")
            return False

        # ── Pre-flight 3: write config ──
        self._set_phase(ConnectPhase.WRITING_CONFIG)
        toml_content = profile.to_client_toml()
        config_path = os.path.join(
            tempfile.gettempdir(), f"tt_gui_{os.getpid()}.toml"
        )
        try:
            with open(config_path, "w") as f:
                f.write(toml_content)
        except OSError as e:
            self._set_error(f"Failed to write config to {config_path}:\n{e}")
            return False
        self._config_path = config_path

        # ── Spawn process ──
        self._set_phase(ConnectPhase.SPAWNING_PROCESS)
        with self._lock:
            self._status.state = ClientState.CONNECTING
        self._notify()

        try:
            self._process = subprocess.Popen(
                ["sudo", "-n", binary, "-c", config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._start_time = time.time()

            # Background reader
            self._reader_thread = Thread(
                target=self._read_output, daemon=True
            )
            self._reader_thread.start()

            # ── Wait for tunnel with phased checking ──
            self._set_phase(ConnectPhase.WAITING_TUNNEL)

            # Wait up to 10 seconds (some servers take time)
            deadline = time.time() + 10
            connected = False
            while time.time() < deadline:
                time.sleep(0.5)
                if self._process.poll() is not None:
                    # Process died
                    logs = "\n".join(self._status.log_lines[-20:])
                    self._set_error(
                        f"trusttunnel_client exited with code "
                        f"{self._process.returncode}.\n\n"
                        f"--- last 20 log lines ---\n{logs}\n"
                        f"--- end of log ---\n\n"
                        f"Config written to: {config_path}\n"
                        f"Command: sudo -n {binary} -c {config_path}"
                    )
                    return False
                # Check if output indicates connection
                with self._lock:
                    if self._status.state == ClientState.CONNECTED:
                        connected = True
                        break

            if connected:
                self._set_phase(ConnectPhase.TUNNEL_UP)
                return True
            else:
                # Process still running but no tunnel-up signal
                # Consider it connected anyway if alive
                with self._lock:
                    self._status.state = ClientState.CONNECTED
                self._set_phase(ConnectPhase.TUNNEL_UP)
                self._notify()
                return True

        except Exception as e:
            self._set_error(f"Exception during connect:\n{type(e).__name__}: {e}")
            return False

    def _read_output(self):
        """Read subprocess output, parsing for status info."""
        if not self._process or not self._process.stdout:
            return
        try:
            for line in self._process.stdout:
                line = line.rstrip()
                with self._lock:
                    self._status.log_lines.append(f"[{_ts()}] {line}")
                    if len(self._status.log_lines) > 1000:
                        self._status.log_lines = self._status.log_lines[-400:]
                # Detect connection established
                lower = line.lower()
                if any(kw in lower for kw in [
                    "connected", "tunnel up", "tunnel is up",
                    "listening", "started", "running",
                ]):
                    with self._lock:
                        if self._status.state == ClientState.CONNECTING:
                            self._status.state = ClientState.CONNECTED
                            self._status.phase = ConnectPhase.TUNNEL_UP
                    self._notify()
        except Exception:
            pass

    def disconnect(self):
        """Stop the VPN connection."""
        if self._process:
            try:
                self._process.send_signal(signal.SIGTERM)
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
            except Exception:
                pass
            self._process = None

        if self._config_path and os.path.exists(self._config_path):
            try:
                os.unlink(self._config_path)
            except Exception:
                pass
        self._config_path = None

        self._start_time = 0.0
        with self._lock:
            self._status.state = ClientState.DISCONNECTED
            self._status.phase = ConnectPhase.IDLE
            self._status.server_name = ""
            self._status.started_at = None
        self._notify()

    def is_connected(self) -> bool:
        return (
            self._process is not None
            and self._process.poll() is None
            and self._status.state == ClientState.CONNECTED
        )

    def _set_error(self, msg: str):
        with self._lock:
            self._status.state = ClientState.ERROR
            self._status.phase = ConnectPhase.FAILED
            self._status.error = msg
            self._status.log_lines.append(
                f"[{_ts()}] ERROR: {msg[:200]}"
            )
        self._notify()

    def get_logs(self, n: int = 50) -> str:
        return "\n".join(self._status.log_lines[-n:])

    def get_full_logs(self) -> str:
        return "\n".join(self._status.log_lines)

    def restart(self, profile) -> bool:
        self.disconnect()
        time.sleep(1)
        return self.connect(profile)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:12]
