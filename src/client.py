"""TrustTunnel client process manager — manages the trusttunnel_client subprocess."""

import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from threading import Thread, Lock
from typing import Optional, Callable

from .config import ServerProfile


CLIENT_BINARY_PATHS = [
    "/opt/trusttunnel_client/trusttunnel_client",
    "/usr/local/bin/trusttunnel_client",
    "trusttunnel_client",
]


class ClientState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ClientStatus:
    state: ClientState = ClientState.DISCONNECTED
    server_name: str = ""
    uptime: float = 0.0
    error: str = ""
    rx_bytes: int = 0
    tx_bytes: int = 0


class ClientManager:
    """Manages the trusttunnel_client process lifecycle."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._status = ClientStatus()
        self._lock = Lock()
        self._start_time: float = 0.0
        self._state_callbacks: list[Callable[[ClientStatus], None]] = []
        self._reader_thread: Optional[Thread] = None
        self._log_lines: list[str] = []
        self._config_path: Optional[str] = None

    @property
    def status(self) -> ClientStatus:
        with self._lock:
            return ClientStatus(
                state=self._status.state,
                server_name=self._status.server_name,
                uptime=time.time() - self._start_time if self._start_time else 0.0,
                error=self._status.error,
                rx_bytes=self._status.rx_bytes,
                tx_bytes=self._status.tx_bytes,
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

    def _find_binary(self) -> Optional[str]:
        for path in CLIENT_BINARY_PATHS:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        # Check PATH
        for path in os.environ.get("PATH", "").split(":"):
            candidate = os.path.join(path, "trusttunnel_client")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    def connect(self, profile: ServerProfile) -> bool:
        """Start the VPN connection with the given profile."""
        if self.is_connected():
            self.disconnect()

        binary = self._find_binary()
        if not binary:
            self._set_error("trusttunnel_client not found. Install it first:\n"
                           "curl -fsSL https://raw.githubusercontent.com/TrustTunnel/"
                           "TrustTunnelClient/refs/heads/master/scripts/install.sh | sh -s -")
            return False

        # Write TOML config
        toml_content = profile.to_client_toml()
        config_path = os.path.join(tempfile.gettempdir(), f"tt_gui_{os.getpid()}.toml")
        with open(config_path, "w") as f:
            f.write(toml_content)
        self._config_path = config_path

        with self._lock:
            self._status.state = ClientState.CONNECTING
            self._status.server_name = profile.name
            self._status.error = ""

        self._notify()

        try:
            self._process = subprocess.Popen(
                ["sudo", binary, "-c", config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._start_time = time.time()
            self._log_lines = []

            # Background reader thread
            self._reader_thread = Thread(target=self._read_output, daemon=True)
            self._reader_thread.start()

            # Wait briefly for connection
            time.sleep(3)
            if self._process.poll() is not None:
                logs = "\n".join(self._log_lines[-10:])
                self._set_error(f"Client exited immediately.\n{logs}")
                return False

            with self._lock:
                self._status.state = ClientState.CONNECTED
            self._notify()
            return True

        except Exception as e:
            self._set_error(str(e))
            return False

    def _read_output(self):
        """Read subprocess output in background, parsing for status info."""
        if not self._process or not self._process.stdout:
            return
        try:
            for line in self._process.stdout:
                self._log_lines.append(line.rstrip())
                if len(self._log_lines) > 500:
                    self._log_lines = self._log_lines[-200:]
                # Check for connection established
                if "connected" in line.lower() or "tunnel up" in line.lower():
                    with self._lock:
                        if self._status.state == ClientState.CONNECTING:
                            self._status.state = ClientState.CONNECTED
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
            self._status.server_name = ""
        self._notify()

    def is_connected(self) -> bool:
        return (self._process is not None
                and self._process.poll() is None
                and self._status.state == ClientState.CONNECTED)

    def _set_error(self, msg: str):
        with self._lock:
            self._status.state = ClientState.ERROR
            self._status.error = msg
        self._notify()

    def get_logs(self, n: int = 50) -> str:
        return "\n".join(self._log_lines[-n:])

    def restart(self, profile: ServerProfile) -> bool:
        self.disconnect()
        time.sleep(1)
        return self.connect(profile)
