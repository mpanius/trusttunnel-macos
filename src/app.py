"""TrustTunnel macOS GUI — traditional windowed app with server management and embedded console."""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from .config import (
    ServerProfile, EndpointConfig,
    load_servers, save_servers, parse_deeplink,
)
from .client import ClientManager, ClientState, ClientStatus


# ── colour constants ──────────────────────────────────────────────
BG = "#1e1e1e"
FG = "#d4d4d4"
ACCENT = "#0078d4"
ACCENT_HOVER = "#1a8ae8"
ERROR_RED = "#f44747"
SUCCESS_GREEN = "#4ec9b0"
WARNING_YELLOW = "#cca700"
ROW_ALT = "#2a2a2a"
CONSOLE_BG = "#0d0d0d"


class AddEditDialog(tk.Toplevel):
    """Modal dialog for adding or editing a server profile."""

    def __init__(self, parent, profile: Optional[ServerProfile] = None):
        super().__init__(parent)
        self.title("Edit Server" if profile else "Add Server")
        self.geometry("500x480")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.result: Optional[ServerProfile] = None

        self._profile = profile
        self._build()
        self.transient(parent)
        self.grab_set()
        self.wait_window()

    def _build(self):
        pad = {"padx": 12, "pady": 4}

        fields = [
            ("Name:", "name", ""),
            ("Hostname:", "hostname", ""),
            ("Address (ip:port):", "address", ""),
            ("Username:", "username", ""),
            ("Password:", "password", ""),
            ("Certificate (PEM):", "certificate", ""),
        ]

        self._entries = {}

        row = 0
        for label_text, key, default in fields:
            lbl = tk.Label(self, text=label_text, bg=BG, fg=FG, anchor="w")
            lbl.grid(row=row, column=0, sticky="w", **pad)

            if key == "certificate":
                entry = tk.Text(self, height=4, width=50, bg="#2d2d2d", fg=FG,
                                insertbackground=FG, relief="flat", borderwidth=4)
            elif key == "password":
                entry = tk.Entry(self, show="*", width=40, bg="#2d2d2d", fg=FG,
                                 insertbackground=FG, relief="flat")
            else:
                entry = tk.Entry(self, width=40, bg="#2d2d2d", fg=FG,
                                 insertbackground=FG, relief="flat")

            entry.grid(row=row, column=1, sticky="ew", **pad)
            self._entries[key] = entry
            row += 1

        # Fill from existing profile
        if self._profile:
            ep = self._profile.endpoint
            self._entries["name"].insert(0, self._profile.name)
            self._entries["hostname"].insert(0, ep.hostname)
            self._entries["address"].insert(0, ",".join(ep.addresses))
            self._entries["username"].insert(0, ep.username)
            self._entries["password"].insert(0, ep.password)
            if ep.certificate:
                self._entries["certificate"].insert("1.0", ep.certificate)

        # Buttons
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=16)

        cancel_btn = tk.Button(btn_frame, text="Cancel", command=self.destroy,
                               bg="#3a3a3a", fg=FG, relief="flat",
                               activebackground="#4a4a4a", activeforeground=FG,
                               padx=16, pady=4)
        cancel_btn.pack(side="left", padx=8)

        save_btn = tk.Button(btn_frame, text="Save", command=self._save,
                             bg=ACCENT, fg="white", relief="flat",
                             activebackground=ACCENT_HOVER, activeforeground="white",
                             padx=24, pady=4)
        save_btn.pack(side="left", padx=8)

        self.grid_columnconfigure(1, weight=1)

    def _save(self):
        name = self._entries["name"].get().strip()
        hostname = self._entries["hostname"].get().strip()
        address = self._entries["address"].get().strip()
        username = self._entries["username"].get().strip()
        password = self._entries["password"].get()
        cert_widget = self._entries["certificate"]
        if isinstance(cert_widget, tk.Text):
            certificate = cert_widget.get("1.0", "end-1c").strip()
        else:
            certificate = cert_widget.get().strip()

        if not name or not hostname or not address or not username:
            messagebox.showwarning("Missing Fields",
                                   "Name, Hostname, Address, and Username are required.",
                                   parent=self)
            return

        addresses = [a.strip() for a in address.split(",") if a.strip()]

        ep = EndpointConfig(
            hostname=hostname,
            addresses=addresses,
            username=username,
            password=password,
            certificate=certificate,
            skip_verification=not bool(certificate),
        )

        if self._profile:
            self._profile.name = name
            self._profile.endpoint = ep
            self.result = self._profile
        else:
            self.result = ServerProfile(name=name, endpoint=ep)

        self.destroy()


class TrustTunnelWindow(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title("TrustTunnel VPN")
        self.geometry("820x620")
        self.minsize(600, 400)
        self.configure(bg=BG)

        self.client = ClientManager()
        self.servers: list[ServerProfile] = load_servers()
        self._selected_index: Optional[int] = None

        self._build_ui()
        self._refresh_server_list()

        # Status update timer
        self._poll_status()

        # Window close → disconnect
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self):
        # ── Toolbar ──
        toolbar = tk.Frame(self, bg="#252525", height=36)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        tk.Label(toolbar, text="🔒 TrustTunnel VPN", bg="#252525", fg=FG,
                 font=("Helvetica", 12, "bold")).pack(side="left", padx=12, pady=6)

        self._status_dot = tk.Label(toolbar, text="⚫", bg="#252525", fg="#666",
                                    font=("Helvetica", 10))
        self._status_dot.pack(side="left", padx=(0, 4))

        self._status_label = tk.Label(toolbar, text="Disconnected", bg="#252525",
                                      fg="#888", font=("Helvetica", 10))
        self._status_label.pack(side="left")

        # ── Main content (paned for server list + console) ──
        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        # Top: server list
        top_frame = tk.Frame(paned, bg=BG)
        paned.add(top_frame, weight=1)

        # Server table
        columns = ("name", "hostname", "address", "username", "status")
        self._tree = ttk.Treeview(top_frame, columns=columns, show="headings",
                                  selectmode="browse", height=8)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background="#252525", foreground=FG,
                        fieldbackground="#252525", rowheight=28,
                        borderwidth=0)
        style.configure("Treeview.Heading",
                        background="#333", foreground=FG,
                        relief="flat", borderwidth=0, font=("Helvetica", 10, "bold"))
        style.map("Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])

        self._tree.heading("name", text="Name", anchor="w")
        self._tree.heading("hostname", text="Hostname", anchor="w")
        self._tree.heading("address", text="Address", anchor="w")
        self._tree.heading("username", text="Username", anchor="w")
        self._tree.heading("status", text="Status", anchor="w")

        self._tree.column("name", width=130, minwidth=80)
        self._tree.column("hostname", width=130, minwidth=80)
        self._tree.column("address", width=160, minwidth=100)
        self._tree.column("username", width=100, minwidth=60)
        self._tree.column("status", width=80, minwidth=60)

        self._tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(top_frame, orient="vertical", command=self._tree.yview)
        scrollbar.pack(side="right", fill="y")
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.bind("<<TreeviewSelect>>", self._on_server_select)
        self._tree.bind("<Double-1>", lambda e: self._connect_selected())

        # ── Server action buttons ──
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(fill="x", padx=8, pady=(0, 4))

        self._make_btn(btn_frame, "+ Add", self._add_server).pack(side="left", padx=2)
        self._make_btn(btn_frame, "✎ Edit", self._edit_server).pack(side="left", padx=2)
        self._make_btn(btn_frame, "✕ Delete", self._delete_server).pack(side="left", padx=2)
        self._make_btn(btn_frame, "📋 Import Link", self._import_deeplink).pack(side="left", padx=2)

        self._connect_btn = self._make_btn(
            btn_frame, "▶ Connect", self._connect_selected, accent=True)
        self._connect_btn.pack(side="right", padx=2)

        self._disconnect_btn = self._make_btn(
            btn_frame, "■ Disconnect", self._disconnect, accent=False)
        # Hidden initially

        # ── Console ──
        console_label = tk.Label(self, text="Console", bg=BG, fg="#888",
                                 font=("Helvetica", 9, "bold"), anchor="w")
        console_label.pack(fill="x", padx=12, pady=(4, 0))

        console_frame = tk.Frame(self, bg=CONSOLE_BG, height=180)
        console_frame.pack(fill="both", expand=False, padx=8, pady=(2, 4))
        console_frame.pack_propagate(False)

        self._console = tk.Text(console_frame, bg=CONSOLE_BG, fg="#a0a0a0",
                                font=("Menlo", 10), wrap="word", state="disabled",
                                relief="flat", borderwidth=6, insertbackground=FG)
        self._console.pack(fill="both", expand=True, side="left")

        console_scroll = ttk.Scrollbar(console_frame, orient="vertical",
                                       command=self._console.yview)
        console_scroll.pack(side="right", fill="y")
        self._console.configure(yscrollcommand=console_scroll.set)

        # Console toolbar
        console_toolbar = tk.Frame(self, bg=BG)
        console_toolbar.pack(fill="x", padx=8)
        self._make_btn(console_toolbar, "Clear", self._clear_console,
                       small=True).pack(side="right")

    def _make_btn(self, parent, text, command, accent=False, small=False):
        bg_color = ACCENT if accent else "#3a3a3a"
        fg_color = "white" if accent else FG
        hover_bg = ACCENT_HOVER if accent else "#4a4a4a"
        font_size = 9 if small else 10
        pad = (8, 2) if small else (12, 4)

        btn = tk.Button(parent, text=text, command=command,
                        bg=bg_color, fg=fg_color, relief="flat",
                        activebackground=hover_bg, activeforeground=fg_color,
                        font=("Helvetica", font_size),
                        padx=pad[0], pady=pad[1])
        return btn

    # ── Server management ────────────────────────────────────────

    def _refresh_server_list(self):
        """Reload server list into treeview."""
        for item in self._tree.get_children():
            self._tree.delete(item)

        for i, s in enumerate(self.servers):
            addr = ",".join(s.endpoint.addresses) if s.endpoint.addresses else ""
            is_active = (
                self.client.is_connected()
                and self.client.status.server_name == s.name
            )
            status = "🟢 connected" if is_active else "⚫ idle"
            tag = "connected" if is_active else ""

            self._tree.insert("", "end", iid=str(i), values=(
                s.name,
                s.endpoint.hostname,
                addr,
                s.endpoint.username,
                status,
            ), tags=(tag,))

        self._tree.tag_configure("connected", background="#1a3a2a", foreground=SUCCESS_GREEN)

    def _save_and_refresh(self):
        save_servers(self.servers)
        self._refresh_server_list()

    def _on_server_select(self, event=None):
        sel = self._tree.selection()
        self._selected_index = int(sel[0]) if sel else None

    def _add_server(self):
        dlg = AddEditDialog(self)
        if dlg.result:
            self.servers.append(dlg.result)
            self._save_and_refresh()
            # Select the new server
            idx = len(self.servers) - 1
            self._tree.selection_set(str(idx))
            self._tree.focus(str(idx))

    def _edit_server(self):
        if self._selected_index is None:
            messagebox.showinfo("Select Server", "Select a server to edit first.")
            return
        profile = self.servers[self._selected_index]
        dlg = AddEditDialog(self, profile=profile)
        if dlg.result:
            self.servers[self._selected_index] = dlg.result
            self._save_and_refresh()

    def _delete_server(self):
        if self._selected_index is None:
            messagebox.showinfo("Select Server", "Select a server to delete first.")
            return
        profile = self.servers[self._selected_index]
        if messagebox.askyesno("Delete Server",
                               f"Delete server '{profile.name}'?",
                               parent=self):
            self.servers.pop(self._selected_index)
            self._selected_index = None
            self._save_and_refresh()

    def _import_deeplink(self):
        """Prompt for tt://? deep-link and import."""
        dlg = tk.Toplevel(self)
        dlg.title("Import Deep-Link")
        dlg.geometry("580x140")
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="Paste a tt://? deep-link:", bg=BG, fg=FG).pack(padx=12, pady=(12, 4), anchor="w")

        entry = tk.Text(dlg, height=2, width=60, bg="#2d2d2d", fg=FG,
                        insertbackground=FG, relief="flat", borderwidth=4,
                        font=("Menlo", 9))
        entry.pack(fill="x", padx=12, pady=4)

        # Try clipboard
        try:
            clipboard = self.clipboard_get()
            entry.insert("1.0", clipboard)
        except Exception:
            pass

        def do_import():
            uri = entry.get("1.0", "end-1c").strip()
            if not uri:
                dlg.destroy()
                return
            profile = parse_deeplink(uri)
            if profile:
                self.servers.append(profile)
                self._save_and_refresh()
                dlg.destroy()
                self._log(f"Imported: {profile.name}")
            else:
                messagebox.showwarning("Parse Error",
                                       "Could not parse deep-link. Check format.",
                                       parent=dlg)

        btn_frame = tk.Frame(dlg, bg=BG)
        btn_frame.pack(pady=8)
        tk.Button(btn_frame, text="Cancel", command=dlg.destroy,
                  bg="#3a3a3a", fg=FG, relief="flat", padx=12).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Import", command=do_import,
                  bg=ACCENT, fg="white", relief="flat", padx=16).pack(side="left", padx=4)

    # ── Connection controls ──────────────────────────────────────

    def _connect_selected(self):
        if self._selected_index is None:
            messagebox.showinfo("Select Server", "Select a server to connect to first.")
            return
        profile = self.servers[self._selected_index]
        self._log(f"Connecting to {profile.name}...")
        self._update_status("connecting", f"Connecting to {profile.name}...")

        # Run connect in background to not block UI
        def do_connect():
            success = self.client.connect(profile)
            if not success:
                self.after(0, lambda: self._log(f"ERROR: {self.client.status.error}"))
            self.after(0, self._refresh_server_list)

        t = threading.Thread(target=do_connect, daemon=True)
        t.start()

    def _disconnect(self):
        self._log("Disconnecting...")
        self.client.disconnect()
        self._update_status("disconnected", "Disconnected")
        self._refresh_server_list()

    # ── Console ───────────────────────────────────────────────────

    def _log(self, text: str):
        self._console.configure(state="normal")
        self._console.insert("end", text + "\n")
        self._console.see("end")
        self._console.configure(state="disabled")

    def _clear_console(self):
        self._console.configure(state="normal")
        self._console.delete("1.0", "end")
        self._console.configure(state="disabled")

    # ── Status polling ───────────────────────────────────────────

    def _poll_status(self):
        """Periodically update status and console from client."""
        try:
            status = self.client.status

            # Update status indicator
            state_map = {
                ClientState.DISCONNECTED: ("⚫", "Disconnected", "#666"),
                ClientState.CHECKING: ("🟡", "Checking...", WARNING_YELLOW),
                ClientState.CONNECTING: ("🟡", f"Connecting... [{status.phase.value}]",
                                         WARNING_YELLOW),
                ClientState.CONNECTED: ("🟢", f"Connected — {status.server_name}",
                                        SUCCESS_GREEN),
                ClientState.ERROR: ("🔴", "Error", ERROR_RED),
            }
            dot, label, color = state_map.get(status.state,
                                              ("⚫", status.state.value, "#666"))

            self._status_dot.configure(text=dot, fg=color)
            self._status_label.configure(text=label, fg=color)

            # Show/hide connect/disconnect buttons
            if status.state == ClientState.CONNECTED:
                self._connect_btn.pack_forget()
                self._disconnect_btn.pack(side="right", padx=2)
            else:
                self._disconnect_btn.pack_forget()
                self._connect_btn.pack(side="right", padx=2)

            # Append new log lines to console
            lines = status.log_lines
            if hasattr(self, "_last_log_count"):
                new_lines = lines[self._last_log_count:]
                for line in new_lines:
                    self._log(line)
            self._last_log_count = len(lines)

            # Refresh server list periodically
            if status.state in (ClientState.CONNECTED, ClientState.CONNECTING,
                                ClientState.CHECKING):
                self._refresh_server_list()

        except Exception:
            pass

        self.after(300, self._poll_status)

    def _update_status(self, state: str, text: str):
        pass  # handled by _poll_status

    # ── Lifecycle ─────────────────────────────────────────────────

    def _on_close(self):
        if self.client.is_connected():
            if messagebox.askyesno("Disconnect",
                                   "VPN is connected. Disconnect and quit?",
                                   parent=self):
                self.client.disconnect()
            else:
                return
        self.destroy()


def main():
    app = TrustTunnelWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
