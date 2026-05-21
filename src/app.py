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


# ── ttk style setup ───────────────────────────────────────────────
def _setup_styles():
    style = ttk.Style()
    style.theme_use("default")  # 'aqua' has issues with custom colours

    style.configure("Dark.TFrame", background="#1e1e1e")
    style.configure("Dark.TLabel", background="#1e1e1e", foreground="#d4d4d4")
    style.configure("DarkTitle.TLabel", background="#252525", foreground="#d4d4d4")
    style.configure("DarkBold.TLabel", background="#1e1e1e", foreground="#d4d4d4",
                    font=("Helvetica", 11, "bold"))
    style.configure("Accent.TButton", background="#0078d4", foreground="white",
                    font=("Helvetica", 11, "bold"))

    style.configure("Treeview", background="#2d2d2d", foreground="#d4d4d4",
                    fieldbackground="#2d2d2d", rowheight=26, borderwidth=0)
    style.configure("Treeview.Heading", background="#3a3a3a", foreground="#d4d4d4",
                    relief="flat", borderwidth=0,
                    font=("Helvetica", 10, "bold"))
    style.map("Treeview",
              background=[("selected", "#0078d4")],
              foreground=[("selected", "white")])

    style.configure("DarkConsole.TFrame", background="#0d0d0d")


# ── colours for tk widgets that don't use ttk ─────────────────────
BG = "#1e1e1e"
FG = "#d4d4d4"
INPUT_BG = "#3a3a3a"   # lighter for contrast
CONSOLE_BG = "#0d0d0d"
ACCENT = "#0078d4"
ERROR_RED = "#f44747"
SUCCESS_GREEN = "#4ec9b0"
WARNING_YELLOW = "#cca700"


class AddEditDialog(tk.Toplevel):
    """Modal form dialog using standard tk widgets (most reliable)."""

    def __init__(self, parent, profile: Optional[ServerProfile] = None):
        super().__init__(parent)
        self.title("Edit Server" if profile else "Add Server")
        self.configure(bg="#252525")
        self.result: Optional[ServerProfile] = None
        self._profile = profile

        self.transient(parent)
        self.grab_set()

        self._build()
        self.resizable(False, False)
        self.wait_window()

    def _build(self):
        # Main form area — lighter background so inputs stand out
        form = tk.Frame(self, bg="#2a2a2a", padx=20, pady=16)
        form.pack(fill="both", expand=True)

        fields = [
            ("Name", "name", False),
            ("Hostname", "hostname", False),
            ("Address (ip:port)", "address", False),
            ("Username", "username", False),
            ("Password", "password", True),
            ("Certificate PEM (optional)", "certificate", False),
        ]

        self._entries = {}
        for label_text, key, is_password in fields:
            row = tk.Frame(form, bg="#2a2a2a")
            row.pack(fill="x", pady=3)

            tk.Label(row, text=label_text + ":", bg="#2a2a2a", fg="#cccccc",
                     anchor="e", width=20, font=("Helvetica", 10)).pack(
                side="left", padx=(0, 8))

            if key == "certificate":
                w = tk.Text(row, height=4, width=42,
                            bg="#1a1a1a", fg="#e0e0e0",
                            insertbackground="#e0e0e0",
                            relief="solid", borderwidth=1,
                            font=("Menlo", 9))
                w.pack(side="left", fill="x", expand=True)
            elif is_password:
                w = tk.Entry(row, show="*", width=42,
                             bg="#1a1a1a", fg="#e0e0e0",
                             insertbackground="#e0e0e0",
                             relief="solid", borderwidth=1,
                             font=("Helvetica", 11))
                w.pack(side="left")
            else:
                w = tk.Entry(row, width=42,
                             bg="#1a1a1a", fg="#e0e0e0",
                             insertbackground="#e0e0e0",
                             relief="solid", borderwidth=1,
                             font=("Helvetica", 11))
                w.pack(side="left")

            self._entries[key] = w

        # Pre-fill
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
        btn_frame = tk.Frame(form, bg="#2a2a2a")
        btn_frame.pack(fill="x", pady=(16, 0))

        tk.Button(btn_frame, text="Cancel", command=self.destroy,
                  bg="#555", fg="#ccc", relief="flat",
                  activebackground="#666", activeforeground="white",
                  font=("Helvetica", 10), padx=14, pady=4).pack(
            side="left", padx=(0, 10))

        tk.Button(btn_frame, text="Save", command=self._save,
                  bg=ACCENT, fg="white", relief="flat",
                  activebackground="#1a8ae8", activeforeground="white",
                  font=("Helvetica", 10, "bold"), padx=20, pady=4).pack(
            side="left")

    def _save(self):
        name = self._entries["name"].get().strip()
        hostname = self._entries["hostname"].get().strip()
        address = self._entries["address"].get().strip()
        username = self._entries["username"].get().strip()
        password = self._entries["password"].get()
        cert = self._entries["certificate"]
        certificate = cert.get("1.0", "end-1c").strip() if isinstance(cert, tk.Text) else cert.get().strip()

        if not name or not hostname or not address or not username:
            messagebox.showwarning("Missing Fields",
                                   "Name, Hostname, Address, Username are required.",
                                   parent=self)
            return

        ep = EndpointConfig(
            hostname=hostname,
            addresses=[a.strip() for a in address.split(",") if a.strip()],
            username=username, password=password,
            certificate=certificate,
            skip_verification=not bool(certificate),
        )
        self.result = (self._profile or ServerProfile(name=name, endpoint=ep))
        if self._profile:
            self._profile.name = name
            self._profile.endpoint = ep
        self.destroy()


class TrustTunnelWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TrustTunnel VPN")
        self.configure(bg=BG)

        _setup_styles()

        self.client = ClientManager()
        self.servers: list[ServerProfile] = load_servers()
        self._selected_index: Optional[int] = None

        self._build()
        self._refresh_server_list()
        self.geometry("820x600")
        self.minsize(500, 400)

        self._poll_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self):
        # ── Title bar ──
        title = tk.Frame(self, bg="#252525", height=34)
        title.pack(fill="x")
        title.pack_propagate(False)

        tk.Label(title, text="  TrustTunnel VPN", bg="#252525", fg=FG,
                 font=("Helvetica", 12, "bold")).pack(side="left", pady=4)

        self._status_dot = tk.Label(title, text="", bg="#252525", fg="#666",
                                    font=("Helvetica", 13))
        self._status_dot.pack(side="left", padx=(8, 0))

        self._status_text = tk.Label(title, text="Disconnected", bg="#252525",
                                     fg="#888", font=("Helvetica", 10))
        self._status_text.pack(side="left", padx=4)

        # ── Server table ──
        table_frame = tk.LabelFrame(self, text=" Servers ", bg=BG, fg="#888",
                                    font=("Helvetica", 9, "bold"),
                                    padx=4, pady=4)
        table_frame.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        cols = ("name", "hostname", "address", "username", "status")
        self._tree = ttk.Treeview(table_frame, columns=cols,
                                  show="headings", selectmode="browse")
        self._tree.heading("name", text="Name", anchor="w")
        self._tree.heading("hostname", text="Hostname", anchor="w")
        self._tree.heading("address", text="Address", anchor="w")
        self._tree.heading("username", text="Username", anchor="w")
        self._tree.heading("status", text="Status", anchor="w")
        self._tree.column("name", width=110, minwidth=60)
        self._tree.column("hostname", width=110, minwidth=60)
        self._tree.column("address", width=150, minwidth=80)
        self._tree.column("username", width=90, minwidth=50)
        self._tree.column("status", width=80, minwidth=60)
        self._tree.pack(fill="both", expand=True, side="left")

        vsb = ttk.Scrollbar(table_frame, orient="vertical",
                           command=self._tree.yview)
        vsb.pack(side="right", fill="y")
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.bind("<<TreeviewSelect>>", self._on_server_select)
        self._tree.bind("<Double-1>", lambda e: self._connect_selected())

        # ── Buttons ──
        btn_bar = tk.Frame(self, bg=BG)
        btn_bar.pack(fill="x", padx=8, pady=4)

        def btn(text, cmd, accent=False):
            return tk.Button(btn_bar, text=text, command=cmd,
                             bg=ACCENT if accent else "#444",
                             fg="white" if accent else FG,
                             relief="flat",
                             activebackground="#1a8ae8" if accent else "#555",
                             activeforeground="white",
                             font=("Helvetica", 10, "bold" if accent else "normal"),
                             padx=12, pady=4)

        btn("+ Add", self._add_server).pack(side="left", padx=1)
        btn("Edit", self._edit_server).pack(side="left", padx=1)
        btn("Delete", self._delete_server).pack(side="left", padx=1)
        btn("Import Link", self._import_deeplink).pack(side="left", padx=1)

        self._btn_connect = btn("Connect", self._connect_selected, accent=True)
        self._btn_connect.pack(side="right", padx=2)

        self._btn_disconnect = btn("Disconnect", self._disconnect, accent=False)
        self._btn_disconnect.configure(bg=ERROR_RED,
                                       activebackground="#d63a3a")

        # ── Console ──
        cons_frame = tk.LabelFrame(self, text=" Console ", bg=BG, fg="#888",
                                   font=("Helvetica", 9, "bold"),
                                   padx=4, pady=4)
        cons_frame.pack(fill="both", expand=False, padx=8, pady=(4, 8))

        self._console = tk.Text(cons_frame, bg=CONSOLE_BG, fg="#a0a0a0",
                                font=("Menlo", 10), wrap="word",
                                state="disabled", relief="flat",
                                borderwidth=4, insertbackground=FG,
                                height=7)
        self._console.pack(fill="both", expand=True, side="left")

        csb = ttk.Scrollbar(cons_frame, orient="vertical",
                           command=self._console.yview)
        csb.pack(side="right", fill="y")
        self._console.configure(yscrollcommand=csb.set)

        tk.Button(cons_frame, text="Clear", command=self._clear_console,
                  bg="#444", fg=FG, relief="flat",
                  activebackground="#555", activeforeground="white",
                  font=("Helvetica", 9)).pack(side="bottom", anchor="e",
                                               padx=4, pady=2)

    # ── CRUD ──────────────────────────────────────────────────────

    def _refresh_server_list(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for i, s in enumerate(self.servers):
            addr = ",".join(s.endpoint.addresses) if s.endpoint.addresses else ""
            active = self.client.is_connected() and self.client.status.server_name == s.name
            self._tree.insert("", "end", iid=str(i), values=(
                s.name, s.endpoint.hostname, addr,
                s.endpoint.username, "connected" if active else "idle",
            ), tags=("connected" if active else "",))
        self._tree.tag_configure("connected", background="#1a3a2a",
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
            messagebox.showinfo("Note", "Select a server to edit first.")
            return
        dlg = AddEditDialog(self, profile=self.servers[self._selected_index])
        if dlg.result:
            self.servers[self._selected_index] = dlg.result
            self._save_and_refresh()

    def _delete_server(self):
        if self._selected_index is None:
            messagebox.showinfo("Note", "Select a server to delete first.")
            return
        s = self.servers[self._selected_index]
        if messagebox.askyesno("Delete", f"Delete '{s.name}'?", parent=self):
            self.servers.pop(self._selected_index)
            self._selected_index = None
            self._save_and_refresh()

    def _import_deeplink(self):
        dlg = tk.Toplevel(self)
        dlg.title("Import Deep-Link")
        dlg.configure(bg="#252525")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        f = tk.Frame(dlg, bg="#252525", padx=16, pady=12)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="Paste tt://? deep-link:", bg="#252525", fg="#ccc",
                 anchor="w", font=("Helvetica", 10)).pack(fill="x")

        e = tk.Text(f, height=2, width=55, bg="#1a1a1a", fg="#e0e0e0",
                    insertbackground="#e0e0e0", relief="solid", borderwidth=1,
                    font=("Menlo", 9))
        e.pack(fill="x", pady=6)
        try:
            e.insert("1.0", self.clipboard_get())
        except Exception:
            pass

        def do_import():
            uri = e.get("1.0", "end-1c").strip()
            if not uri:
                dlg.destroy(); return
            profile = parse_deeplink(uri)
            if profile:
                self.servers.append(profile)
                self._save_and_refresh()
                self._log(f"Imported: {profile.name}")
                dlg.destroy()
            else:
                messagebox.showwarning("Error", "Could not parse deep-link.", parent=dlg)

        bf = tk.Frame(f, bg="#252525")
        bf.pack(fill="x", pady=(8, 0))
        tk.Button(bf, text="Cancel", command=dlg.destroy,
                  bg="#555", fg="#ccc", relief="flat",
                  activebackground="#666", activeforeground="white",
                  padx=12).pack(side="left", padx=(0, 10))
        tk.Button(bf, text="Import", command=do_import,
                  bg=ACCENT, fg="white", relief="flat",
                  activebackground="#1a8ae8", activeforeground="white",
                  padx=16).pack(side="left")

    # ── Connection ─────────────────────────────────────────────────

    def _connect_selected(self):
        if self._selected_index is None:
            messagebox.showinfo("Note", "Select a server first.")
            return
        profile = self.servers[self._selected_index]
        self._log(f"--- Connecting to {profile.name} ---")

        def do_connect():
            success = self.client.connect(profile)
            self.after(0, lambda: self._log(
                f"ERROR: {self.client.status.error}" if not success
                else f"Connected to {profile.name}"))
            self.after(0, self._refresh_server_list)

        threading.Thread(target=do_connect, daemon=True).start()

    def _disconnect(self):
        self._log("--- Disconnecting ---")
        self.client.disconnect()
        self._refresh_server_list()

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

            dots = {ClientState.DISCONNECTED: ("", "#666", "Disconnected"),
                    ClientState.CHECKING: ("\u25cf", WARNING_YELLOW, "Checking..."),
                    ClientState.CONNECTING: ("\u25cf", WARNING_YELLOW,
                                             f"Connecting [{status.phase.value}]"),
                    ClientState.CONNECTED: ("\u25cf", SUCCESS_GREEN,
                                            f"Connected - {status.server_name}"),
                    ClientState.ERROR: ("\u25cf", ERROR_RED, "Error")}
            dot, color, label = dots.get(state, ("", "#666", state.value))

            self._status_dot.configure(text=dot, fg=color)
            self._status_text.configure(text=label, fg=color)

            # Log new lines
            lines = status.log_lines
            if not hasattr(self, "_log_idx"):
                self._log_idx = 0
            for line in lines[self._log_idx:]:
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

    def _on_close(self):
        if self.client.is_connected():
            if messagebox.askyesno("Quit", "Disconnect and quit?", parent=self):
                self.client.disconnect()
            else:
                return
        self.destroy()


def main():
    app = TrustTunnelWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
