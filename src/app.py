"""TrustTunnel macOS GUI — windowed app with server table, CRUD, embedded console."""

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


# ── colours ───────────────────────────────────────────────────────
BG = "#1e1e1e"
FG = "#d4d4d4"
ACCENT = "#0078d4"
ACCENT_HOVER = "#1a8ae8"
ERROR_RED = "#f44747"
SUCCESS_GREEN = "#4ec9b0"
WARNING_YELLOW = "#cca700"
CONSOLE_BG = "#0d0d0d"
INPUT_BG = "#2d2d2d"
BTN_BG = "#3a3a3a"
BTN_HOVER = "#4a4a4a"


class AddEditDialog(tk.Toplevel):
    """Modal dialog for adding/editing a server profile."""

    def __init__(self, parent, profile: Optional[ServerProfile] = None):
        super().__init__(parent)
        self.title("Edit Server" if profile else "Add Server")
        self.configure(bg=BG)
        self.result: Optional[ServerProfile] = None
        self._profile = profile

        # Make modal
        self.transient(parent)
        self.grab_set()

        # Build inside a frame
        self._build()

        # Size to content
        self.update_idletasks()
        w = self.winfo_reqwidth() + 40
        h = self.winfo_reqheight() + 20
        self.geometry(f"{max(w, 440)}x{max(h, 380)}")
        self.resizable(False, False)

        # Center on parent
        if parent:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

        self.wait_window()

    def _build(self):
        frame = tk.Frame(self, bg=BG, padx=16, pady=12)
        frame.pack(fill="both", expand=True)

        fields = [
            ("Name:", "name", False),
            ("Hostname:", "hostname", False),
            ("Address (ip:port):", "address", False),
            ("Username:", "username", False),
            ("Password:", "password", True),
            ("Certificate (PEM, optional):", "certificate", False),
        ]

        self._entries = {}
        for label_text, key, is_password in fields:
            row_frame = tk.Frame(frame, bg=BG)
            row_frame.pack(fill="x", pady=3)

            tk.Label(row_frame, text=label_text, bg=BG, fg=FG,
                     anchor="w", width=22).pack(side="left")

            if key == "certificate":
                entry = tk.Text(row_frame, height=4, width=42,
                                bg=INPUT_BG, fg=FG, insertbackground=FG,
                                relief="flat", borderwidth=4,
                                font=("Menlo", 9))
                entry.pack(side="left", fill="x", expand=True)
            elif is_password:
                entry = tk.Entry(row_frame, show="*", width=42,
                                 bg=INPUT_BG, fg=FG, insertbackground=FG,
                                 relief="flat")
                entry.pack(side="left")
            else:
                entry = tk.Entry(row_frame, width=42,
                                 bg=INPUT_BG, fg=FG, insertbackground=FG,
                                 relief="flat")
                entry.pack(side="left")

            self._entries[key] = entry

        # Pre-fill from profile
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
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill="x", pady=(16, 0))

        tk.Button(btn_frame, text="Cancel", command=self.destroy,
                  bg=BTN_BG, fg=FG, relief="flat",
                  activebackground=BTN_HOVER, activeforeground=FG,
                  padx=16, pady=4).pack(side="left", padx=(0, 8))

        tk.Button(btn_frame, text="Save", command=self._save,
                  bg=ACCENT, fg="white", relief="flat",
                  activebackground=ACCENT_HOVER, activeforeground="white",
                  padx=24, pady=4).pack(side="left")

    def _save(self):
        name = self._entries["name"].get().strip()
        hostname = self._entries["hostname"].get().strip()
        address = self._entries["address"].get().strip()
        username = self._entries["username"].get().strip()
        password = self._entries["password"].get()
        cert_widget = self._entries["certificate"]
        certificate = cert_widget.get("1.0", "end-1c").strip() if isinstance(cert_widget, tk.Text) else cert_widget.get().strip()

        if not name or not hostname or not address or not username:
            messagebox.showwarning("Missing Fields",
                                   "Name, Hostname, Address, and Username are required.",
                                   parent=self)
            return

        addresses = [a.strip() for a in address.split(",") if a.strip()]
        ep = EndpointConfig(
            hostname=hostname, addresses=addresses,
            username=username, password=password,
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
    """Main window."""

    def __init__(self):
        super().__init__()
        self.title("TrustTunnel VPN")
        self.configure(bg=BG)

        self.client = ClientManager()
        self.servers: list[ServerProfile] = load_servers()
        self._selected_index: Optional[int] = None

        self._build()
        self._refresh_server_list()

        # Geometry
        self.geometry("800x600")
        self.minsize(500, 400)

        self._poll_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ────────────────────────────────────────────────────────

    def _build(self):
        # Title bar
        title_frame = tk.Frame(self, bg="#252525", height=32)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)

        tk.Label(title_frame, text="TrustTunnel VPN", bg="#252525", fg=FG,
                 font=("Helvetica", 11, "bold")).pack(side="left", padx=12, pady=4)

        self._status_dot = tk.Label(title_frame, text="  ", bg="#252525",
                                    fg="#666", font=("Helvetica", 11))
        self._status_dot.pack(side="left")

        self._status_label = tk.Label(title_frame, text="Disconnected",
                                      bg="#252525", fg="#888",
                                      font=("Helvetica", 10))
        self._status_label.pack(side="left", padx=(0, 12))

        # ── Server table ──
        table_frame = tk.LabelFrame(self, text="Servers", bg=BG, fg="#888",
                                    font=("Helvetica", 9, "bold"),
                                    padx=4, pady=4)
        table_frame.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        columns = ("name", "hostname", "address", "username", "status")
        self._tree = ttk.Treeview(table_frame, columns=columns, show="headings",
                                  selectmode="browse")

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background=INPUT_BG, foreground=FG,
                        fieldbackground=INPUT_BG, rowheight=26, borderwidth=0)
        style.configure("Treeview.Heading", background="#333", foreground=FG,
                        relief="flat", borderwidth=0,
                        font=("Helvetica", 10, "bold"))
        style.map("Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])

        self._tree.heading("name", text="Name", anchor="w")
        self._tree.heading("hostname", text="Hostname", anchor="w")
        self._tree.heading("address", text="Address", anchor="w")
        self._tree.heading("username", text="Username", anchor="w")
        self._tree.heading("status", text="Status", anchor="w")

        self._tree.column("name", width=110, minwidth=60)
        self._tree.column("hostname", width=110, minwidth=60)
        self._tree.column("address", width=150, minwidth=80)
        self._tree.column("username", width=90, minwidth=50)
        self._tree.column("status", width=90, minwidth=60)

        self._tree.pack(fill="both", expand=True, side="left")

        vsb = ttk.Scrollbar(table_frame, orient="vertical",
                           command=self._tree.yview)
        vsb.pack(side="right", fill="y")
        self._tree.configure(yscrollcommand=vsb.set)

        self._tree.bind("<<TreeviewSelect>>", self._on_server_select)
        self._tree.bind("<Double-1>", lambda e: self._connect_selected())

        # ── Action buttons ──
        action_frame = tk.Frame(self, bg=BG)
        action_frame.pack(fill="x", padx=8, pady=4)

        self._btn_add = tk.Button(action_frame, text="+ Add",
                                  command=self._add_server,
                                  bg=BTN_BG, fg=FG, relief="flat",
                                  activebackground=BTN_HOVER,
                                  activeforeground=FG,
                                  font=("Helvetica", 10), padx=10, pady=3)
        self._btn_add.pack(side="left", padx=1)

        self._btn_edit = tk.Button(action_frame, text="Edit",
                                   command=self._edit_server,
                                   bg=BTN_BG, fg=FG, relief="flat",
                                   activebackground=BTN_HOVER,
                                   activeforeground=FG,
                                   font=("Helvetica", 10), padx=10, pady=3)
        self._btn_edit.pack(side="left", padx=1)

        self._btn_del = tk.Button(action_frame, text="Delete",
                                  command=self._delete_server,
                                  bg=BTN_BG, fg=FG, relief="flat",
                                  activebackground=BTN_HOVER,
                                  activeforeground=FG,
                                  font=("Helvetica", 10), padx=10, pady=3)
        self._btn_del.pack(side="left", padx=1)

        self._btn_import = tk.Button(action_frame, text="Import Link",
                                     command=self._import_deeplink,
                                     bg=BTN_BG, fg=FG, relief="flat",
                                     activebackground=BTN_HOVER,
                                     activeforeground=FG,
                                     font=("Helvetica", 10), padx=10, pady=3)
        self._btn_import.pack(side="left", padx=1)

        self._btn_connect = tk.Button(action_frame, text="Connect",
                                      command=self._connect_selected,
                                      bg=ACCENT, fg="white", relief="flat",
                                      activebackground=ACCENT_HOVER,
                                      activeforeground="white",
                                      font=("Helvetica", 10, "bold"),
                                      padx=16, pady=3)
        self._btn_connect.pack(side="right", padx=2)

        self._btn_disconnect = tk.Button(action_frame, text="Disconnect",
                                         command=self._disconnect,
                                         bg=ERROR_RED, fg="white",
                                         relief="flat",
                                         activebackground="#d63a3a",
                                         activeforeground="white",
                                         font=("Helvetica", 10, "bold"),
                                         padx=16, pady=3)

        # ── Console ──
        console_frame = tk.LabelFrame(self, text="Console", bg=BG, fg="#888",
                                      font=("Helvetica", 9, "bold"),
                                      padx=4, pady=4)
        console_frame.pack(fill="both", expand=False, padx=8, pady=(4, 8))
        # Fixed height but can grow
        console_frame.configure(height=160)

        self._console = tk.Text(console_frame, bg=CONSOLE_BG, fg="#a0a0a0",
                                font=("Menlo", 10), wrap="word",
                                state="disabled", relief="flat",
                                borderwidth=4, insertbackground=FG,
                                height=6)
        self._console.pack(fill="both", expand=True, side="left")

        csb = ttk.Scrollbar(console_frame, orient="vertical",
                           command=self._console.yview)
        csb.pack(side="right", fill="y")
        self._console.configure(yscrollcommand=csb.set)

        # Clear button above console
        tk.Button(console_frame, text="Clear", command=self._clear_console,
                  bg=BTN_BG, fg=FG, relief="flat",
                  activebackground=BTN_HOVER, activeforeground=FG,
                  font=("Helvetica", 9)).pack(side="bottom", anchor="e",
                                               padx=4, pady=2)

    # ── Server CRUD ───────────────────────────────────────────────

    def _refresh_server_list(self):
        for item in self._tree.get_children():
            self._tree.delete(item)

        for i, s in enumerate(self.servers):
            addr = ",".join(s.endpoint.addresses) if s.endpoint.addresses else ""
            active = (self.client.is_connected()
                      and self.client.status.server_name == s.name)
            status = "connected" if active else "idle"
            tag = "connected" if active else ""

            self._tree.insert("", "end", iid=str(i), values=(
                s.name, s.endpoint.hostname, addr,
                s.endpoint.username, status,
            ), tags=(tag,))

        self._tree.tag_configure("connected",
                                 background="#1a3a2a",
                                 foreground=SUCCESS_GREEN)

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
        if messagebox.askyesno("Delete", f"Delete '{profile.name}'?", parent=self):
            self.servers.pop(self._selected_index)
            self._selected_index = None
            self._save_and_refresh()

    def _import_deeplink(self):
        dlg = tk.Toplevel(self)
        dlg.title("Import Deep-Link")
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        frame = tk.Frame(dlg, bg=BG, padx=16, pady=12)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Paste tt://? deep-link:", bg=BG, fg=FG,
                 anchor="w").pack(fill="x")

        entry = tk.Text(frame, height=2, width=55, bg=INPUT_BG, fg=FG,
                        insertbackground=FG, relief="flat", borderwidth=4,
                        font=("Menlo", 9))
        entry.pack(fill="x", pady=6)

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
                self._log(f"Imported: {profile.name}")
                dlg.destroy()
            else:
                messagebox.showwarning("Parse Error",
                                       "Could not parse deep-link.", parent=dlg)

        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(fill="x", pady=(8, 0))
        tk.Button(btn_frame, text="Cancel", command=dlg.destroy,
                  bg=BTN_BG, fg=FG, relief="flat",
                  activebackground=BTN_HOVER, activeforeground=FG,
                  padx=12).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="Import", command=do_import,
                  bg=ACCENT, fg="white", relief="flat",
                  activebackground=ACCENT_HOVER, activeforeground="white",
                  padx=16).pack(side="left")

        dlg.update_idletasks()
        w, h = dlg.winfo_reqwidth() + 20, dlg.winfo_reqheight() + 10
        dlg.geometry(f"{max(w, 480)}x{max(h, 150)}")
        px = self.winfo_rootx(); py = self.winfo_rooty()
        pw = self.winfo_width(); ph = self.winfo_height()
        dlg.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    # ── Connection ─────────────────────────────────────────────────

    def _connect_selected(self):
        if self._selected_index is None:
            messagebox.showinfo("Select Server", "Select a server first.")
            return
        profile = self.servers[self._selected_index]
        self._log(f"Connecting to {profile.name}...")
        self._update_buttons("connecting")

        def do_connect():
            success = self.client.connect(profile)
            self.after(0, lambda: self._log(
                f"ERROR: {self.client.status.error}" if not success
                else f"Connected to {profile.name}"
            ))
            self.after(0, self._refresh_server_list)
            self.after(0, self._update_buttons)

        threading.Thread(target=do_connect, daemon=True).start()

    def _disconnect(self):
        self._log("Disconnecting...")
        self.client.disconnect()
        self._refresh_server_list()
        self._update_buttons()

    def _update_buttons(self, state=None):
        """Show/hide connect/disconnect based on actual client state."""
        if state is None:
            connected = self.client.is_connected()
        else:
            connected = (state == "connecting")

        if connected:
            self._btn_connect.pack_forget()
            self._btn_disconnect.pack(side="right", padx=2)
        else:
            self._btn_disconnect.pack_forget()
            self._btn_connect.pack(side="right", padx=2)

    # ── Console ────────────────────────────────────────────────────

    def _log(self, text: str):
        self._console.configure(state="normal")
        self._console.insert("end", text + "\n")
        self._console.see("end")
        self._console.configure(state="disabled")

    def _clear_console(self):
        self._console.configure(state="normal")
        self._console.delete("1.0", "end")
        self._console.configure(state="disabled")

    # ── Polling ────────────────────────────────────────────────────

    def _poll_status(self):
        try:
            status = self.client.status
            state = status.state

            dot_map = {ClientState.DISCONNECTED: ("  ", "#666"),
                       ClientState.CHECKING: ("*", WARNING_YELLOW),
                       ClientState.CONNECTING: ("*", WARNING_YELLOW),
                       ClientState.CONNECTED: ("*", SUCCESS_GREEN),
                       ClientState.ERROR: ("!", ERROR_RED)}
            dot, color = dot_map.get(state, ("  ", "#666"))

            label_map = {ClientState.DISCONNECTED: "Disconnected",
                         ClientState.CHECKING: "Checking...",
                         ClientState.CONNECTING: f"Connecting [{status.phase.value}]",
                         ClientState.CONNECTED: f"Connected - {status.server_name}",
                         ClientState.ERROR: "Error"}
            label = label_map.get(state, state.value)

            self._status_dot.configure(text=dot, fg=color)
            self._status_label.configure(text=label, fg=color)

            # Append new log lines
            lines = status.log_lines
            if not hasattr(self, "_log_idx"):
                self._log_idx = 0
            new_lines = lines[self._log_idx:]
            for line in new_lines:
                self._log(line)
            self._log_idx = len(lines)

            # Buttons
            if state == ClientState.CONNECTED:
                self._btn_connect.pack_forget()
                self._btn_disconnect.pack(side="right", padx=2)
            elif state == ClientState.CONNECTING:
                self._btn_connect.pack_forget()
                self._btn_disconnect.pack(side="right", padx=2)
            else:
                self._btn_disconnect.pack_forget()
                self._btn_connect.pack(side="right", padx=2)

        except Exception:
            pass

        self.after(300, self._poll_status)

    # ── Lifecycle ──────────────────────────────────────────────────

    def _on_close(self):
        if self.client.is_connected():
            if messagebox.askyesno("Quit", "VPN is connected. Disconnect and quit?",
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
