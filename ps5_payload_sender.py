"""PS5 Payload Sender - sends an ELF payload to the PS5 loader (same as `ncat -w 1 IP PORT < payload.elf`)."""

import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, ttk

import flags
from i18n import LANGS, ORDER, detect_language

APP_NAME = "PS5 Payload Sender"
GITHUB_URL = "https://github.com/WonderHunter"
MAX_RECENTS = 15
DEFAULT_PORT = 9021

if sys.platform == "win32":
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PS5PayloadSender")
elif sys.platform == "darwin":
    CONFIG_DIR = os.path.expanduser("~/Library/Application Support/PS5PayloadSender")
else:
    CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                              "ps5-payload-sender")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

C = {
    "bg": "#0e1014",
    "card": "#161921",
    "row": "#1c2029",
    "row_hi": "#232835",
    "border": "#272c38",
    "text": "#e8eaf0",
    "muted": "#8b92a3",
    "dim": "#5d6475",
    "entry": "#0b0d11",
    "accent": "#3b7cf6",
    "accent_hi": "#5a93ff",
    "accent_dim": "#22345c",
    "ok": "#22c55e",
    "err": "#ef4444",
    "warn": "#f5a524",
}

FONT = "Segoe UI"  # replaced at startup by pick_font()
LANG = LANGS["en"]


def t(key, **kw):
    text = LANG.get(key) or LANGS["en"][key]
    return text.format(**kw) if kw else text


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def pick_font(root):
    if sys.platform == "win32":
        return "Segoe UI"
    from tkinter import font
    available = set(font.families(root))
    candidates = (["Helvetica Neue", "Helvetica"] if sys.platform == "darwin"
                  else ["Inter", "Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans", "Liberation Sans"])
    return next((f for f in candidates if f in available), "TkDefaultFont")


# --------------------------------------------------------------------------- config

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    cfg.setdefault("host", "192.168.1.")
    cfg.setdefault("port", DEFAULT_PORT)
    cfg.setdefault("recents", [])
    cfg.setdefault("last_dir", "")
    if cfg.get("lang") not in LANGS:
        cfg["lang"] = detect_language()
    return cfg


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_FILE)
    except OSError:
        pass


# --------------------------------------------------------------------------- network

def send_payload(host, port, path, on_progress):
    with open(path, "rb") as f:
        data = f.read()
    total = len(data)
    view = memoryview(data)
    with socket.create_connection((host, port), timeout=5) as s:
        s.settimeout(15)
        sent = 0
        while sent < total:
            n = s.send(view[sent:sent + 65536])
            sent += n
            on_progress(sent, total)
        s.shutdown(socket.SHUT_WR)
        # like `ncat -w 1`: give the loader a second to close the connection cleanly
        s.settimeout(1)
        try:
            while s.recv(4096):
                pass
        except OSError:
            pass
    return total


# --------------------------------------------------------------------------- helpers

def ltr(text):
    """Keep a left-to-right run (sizes, paths…) intact inside right-to-left text."""
    return f"‎{text}‎" if LANG.get("rtl") else text


def human_size(n):
    for unit in t("units"):
        if n < 1024 or unit == t("units")[-1]:
            return ltr(f"{n:.0f} {unit}" if unit == t("units")[0] else f"{n:.1f} {unit}")
        n /= 1024


def relative_time(ts):
    if not ts:
        return t("never")
    d = int(time.time() - ts)
    if d < 60:
        return t("just_now")
    if d < 3600:
        return t("min_ago", n=d // 60)
    if d < 86400:
        return t("h_ago", n=d // 3600)
    days = d // 86400
    return t("yesterday") if days == 1 else t("d_ago", n=days)


class Notifier:
    """Desktop notifications: native Shell_NotifyIcon toast on Windows, osascript on macOS, notify-send on Linux."""

    NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
    NIF_ICON, NIF_TIP, NIF_INFO = 0x02, 0x04, 0x10
    NIIF_ERROR, NIIF_USER, NIIF_LARGE_ICON = 0x03, 0x04, 0x20

    def __init__(self, root, icon_ico, icon_png):
        self.root = root
        self.icon_png = icon_png
        self.active = False
        self.hide_job = None
        self.ok = False
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes as w

            class NOTIFYICONDATAW(ctypes.Structure):
                _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
                            ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", w.WCHAR * 128),
                            ("dwState", w.DWORD), ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256),
                            ("uVersion", w.UINT), ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD),
                            ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", w.HICON)]

            self.ctypes, self.NID = ctypes, NOTIFYICONDATAW
            self.shell = ctypes.windll.shell32
            self.shell.Shell_NotifyIconW.argtypes = [w.DWORD, ctypes.c_void_p]
            user32 = ctypes.windll.user32
            user32.LoadImageW.restype = w.HANDLE
            user32.LoadImageW.argtypes = [w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int, ctypes.c_int, w.UINT]
            user32.GetParent.restype = w.HWND
            user32.GetParent.argtypes = [w.HWND]
            self.user32 = user32
            # IMAGE_ICON = 1, LR_LOADFROMFILE = 0x10
            self.small_icon = user32.LoadImageW(None, icon_ico, 1, 16, 16, 0x10)
            self.big_icon = user32.LoadImageW(None, icon_ico, 1, 48, 48, 0x10)
            self.ok = True
        except Exception:
            self.ok = False

    def notify(self, title, message, error=False):
        if sys.platform == "win32":
            self._notify_windows(title, message, error)
            return
        if sys.platform == "darwin":
            def q(s):
                return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
            cmd = ["osascript", "-e", f"display notification {q(message)} with title {q(APP_NAME)} subtitle {q(title)}"]
        elif shutil.which("notify-send"):
            cmd = ["notify-send", "-a", APP_NAME, "-i", self.icon_png, title, message]
        else:
            return
        threading.Thread(target=subprocess.run, args=(cmd,), kwargs={"capture_output": True}, daemon=True).start()

    def _nid(self, flags_):
        nid = self.NID()
        nid.cbSize = self.ctypes.sizeof(self.NID)
        nid.hWnd = self.user32.GetParent(self.root.winfo_id())
        nid.uID = 1
        nid.uFlags = flags_
        nid.hIcon = self.small_icon
        nid.szTip = APP_NAME
        return nid

    def _notify_windows(self, title, message, error):
        if not self.ok:
            return
        nid = self._nid(self.NIF_ICON | self.NIF_TIP | self.NIF_INFO)
        nid.szInfoTitle = title[:63]
        nid.szInfo = message[:255]
        if error:
            nid.dwInfoFlags = self.NIIF_ERROR
        else:
            nid.dwInfoFlags = self.NIIF_USER | self.NIIF_LARGE_ICON
            nid.hBalloonIcon = self.big_icon
        if not (self.active and self.shell.Shell_NotifyIconW(self.NIM_MODIFY, self.ctypes.byref(nid))):
            self.active = bool(self.shell.Shell_NotifyIconW(self.NIM_ADD, self.ctypes.byref(nid)))
        # the tray icon only exists to carry the toast: remove it after a few seconds
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
        self.hide_job = self.root.after(8000, self.remove)

    def remove(self):
        self.hide_job = None
        if self.ok and self.active:
            self.shell.Shell_NotifyIconW(self.NIM_DELETE, self.ctypes.byref(self._nid(0)))
            self.active = False


class FlatButton(tk.Label):
    STYLES = {
        "primary": ("accent", "accent_hi", "#ffffff"),
        "secondary": ("row_hi", "border", "text"),
        "ghost": ("row", "row_hi", "muted"),
    }

    def __init__(self, master, text, command, kind="primary", font=None, padx=14, pady=7):
        bg, hover, fg = self.STYLES[kind]
        self._bg, self._hover, self._fg = C[bg], C[hover], C.get(fg, fg)
        super().__init__(master, text=text, bg=self._bg, fg=self._fg, cursor="hand2",
                         padx=padx, pady=pady, font=font or (FONT, 10, "bold"))
        self.command = command
        self.enabled = True
        self.bind("<Enter>", lambda e: self.enabled and self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg if self.enabled else C["border"]))
        self.bind("<ButtonRelease-1>", self._click)

    def _click(self, e):
        if self.enabled and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.config(bg=self._bg if enabled else C["border"],
                    fg=self._fg if enabled else C["dim"],
                    cursor="hand2" if enabled else "arrow")


# --------------------------------------------------------------------------- app

class App:
    def __init__(self, root):
        global LANG
        self.root = root
        self.cfg = load_config()
        LANG = LANGS[self.cfg["lang"]]
        self.selected = None
        self.busy = False
        self.events = queue.Queue()
        self.send_buttons = []
        self.lang_popup = None
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)

        root.title(APP_NAME)
        root.configure(bg=C["bg"])
        root.geometry("600x700")
        root.minsize(500, 560)
        try:
            if sys.platform == "win32":
                root.iconbitmap(resource_path("icon.ico"))
            else:
                self._icon_img = tk.PhotoImage(file=resource_path("icon.png"))
                root.iconphoto(True, self._icon_img)
        except tk.TclError:
            pass

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Send.Horizontal.TProgressbar", troughcolor=C["entry"], background=C["accent"],
                        bordercolor=C["entry"], lightcolor=C["accent"], darkcolor=C["accent"], thickness=4)

        if self.cfg["recents"] and os.path.isfile(self.cfg["recents"][0]["path"]):
            self.selected = self.cfg["recents"][0]["path"]
        self._build()
        self.notifier = Notifier(root, resource_path("icon.ico"), resource_path("icon.png"))
        self.refresh_recents()

        root.bind("<Return>", lambda e: self.send_selected())
        root.bind_all("<MouseWheel>", self._on_wheel)
        root.bind_all("<Button-4>", self._on_wheel)
        root.bind_all("<Button-5>", self._on_wheel)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(50, self.poll_events)

    # ---------------------------------------------------------------- layout
    def card(self, parent, title, expand=False, right=None):
        outer = tk.Frame(parent, bg=C["card"], highlightthickness=1, highlightbackground=C["border"])
        outer.pack(fill="both", expand=expand, pady=(0, 12))
        head = tk.Frame(outer, bg=C["card"])
        head.pack(fill="x", padx=16, pady=(12, 8))
        tk.Label(head, text=title.upper(), bg=C["card"], fg=C["muted"],
                 font=(FONT, 8, "bold")).pack(side="left")
        if right:
            right(head)
        body = tk.Frame(outer, bg=C["card"])
        body.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        return body

    def entry(self, parent, value, width=None):
        e = tk.Entry(parent, bg=C["entry"], fg=C["text"], insertbackground=C["text"], relief="flat",
                     font=(FONT, 11), highlightthickness=1, highlightbackground=C["border"],
                     highlightcolor=C["accent"], width=width)
        e.insert(0, str(value))
        return e

    def _build(self):
        wrap = tk.Frame(self.root, bg=C["bg"])
        wrap.pack(fill="both", expand=True, padx=18, pady=(16, 0))

        # header
        head = tk.Frame(wrap, bg=C["bg"])
        head.pack(fill="x", pady=(0, 14))
        self._lang_pill(head).pack(side="right", anchor="n", pady=(4, 0))
        titles = tk.Frame(head, bg=C["bg"])
        titles.pack(side="left", fill="x", expand=True)
        tk.Label(titles, text=APP_NAME, bg=C["bg"], fg=C["text"],
                 font=(FONT, 17, "bold")).pack(anchor="w")
        tk.Label(titles, text=t("subtitle"), bg=C["bg"], fg=C["muted"], font=(FONT, 10)).pack(anchor="w")

        # target
        body = self.card(wrap, t("console"))
        body.columnconfigure(0, weight=1)
        tk.Label(body, text=t("ip"), bg=C["card"], fg=C["muted"], font=(FONT, 9)).grid(row=0, column=0, sticky="w")
        tk.Label(body, text=t("port"), bg=C["card"], fg=C["muted"], font=(FONT, 9)).grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.host_entry = self.entry(body, self.cfg["host"])
        self.host_entry.grid(row=1, column=0, sticky="ew", ipady=6, pady=(4, 0))
        self.port_entry = self.entry(body, self.cfg["port"], width=8)
        self.port_entry.grid(row=1, column=1, sticky="ew", ipady=6, pady=(4, 0), padx=(12, 0))

        # payload
        body = self.card(wrap, t("payload"))
        row = tk.Frame(body, bg=C["card"])
        row.pack(fill="x")
        info = tk.Frame(row, bg=C["card"])
        info.pack(side="left", fill="x", expand=True)
        self.sel_name = tk.Label(info, text=t("none_selected"), bg=C["card"], fg=C["text"],
                                 font=(FONT, 11, "bold"), anchor="w")
        self.sel_name.pack(fill="x")
        self.sel_path = tk.Label(info, text=t("choose_file"), bg=C["card"], fg=C["dim"],
                                 font=(FONT, 9), anchor="w")
        self.sel_path.pack(fill="x")
        if self.selected:
            self.sel_name.config(text=os.path.basename(self.selected))
            self.sel_path.config(text=self.selected)
        FlatButton(row, t("browse"), self.browse, kind="secondary").pack(side="right", padx=(10, 0))

        self.send_btn = FlatButton(body, t("send_payload"), self.send_selected,
                                   font=(FONT, 11, "bold"), pady=10)
        self.send_btn.pack(fill="x", pady=(14, 0))
        self.send_buttons = [self.send_btn]

        # recents
        def recents_header(h):
            self.count_lbl = tk.Label(h, text="", bg=C["card"], fg=C["dim"], font=(FONT, 8, "bold"))
            self.count_lbl.pack(side="left", padx=(6, 0))
        body = self.card(wrap, t("quick_send"), expand=True, right=recents_header)
        self.canvas = tk.Canvas(body, bg=C["card"], highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.list_frame = tk.Frame(self.canvas, bg=C["card"])
        self.list_win = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.list_win, width=e.width))

        # status bar
        bar = tk.Frame(self.root, bg=C["card"], highlightthickness=1, highlightbackground=C["border"])
        bar.pack(fill="x", side="bottom", padx=18, pady=(0, 6), before=wrap)
        self.progress = ttk.Progressbar(bar, style="Send.Horizontal.TProgressbar", maximum=1.0)
        self.progress.pack(fill="x", side="bottom")
        inner = tk.Frame(bar, bg=C["card"])
        inner.pack(fill="x", padx=14, pady=9)
        self.dot = tk.Label(inner, text="●", bg=C["card"], fg=C["dim"], font=(FONT, 10))
        self.dot.pack(side="left")
        self.status = tk.Label(inner, text=t("ready"), bg=C["card"], fg=C["muted"], font=(FONT, 10), anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # footer
        foot = tk.Frame(self.root, bg=C["bg"])
        foot.pack(side="bottom", pady=(0, 8), before=bar)
        tk.Label(foot, text="made with", bg=C["bg"], fg=C["dim"], font=(FONT, 8)).pack(side="left")
        tk.Label(foot, text="♥", bg=C["bg"], fg="#f0507a", font=(FONT, 9)).pack(side="left", padx=2)
        tk.Label(foot, text="by", bg=C["bg"], fg=C["dim"], font=(FONT, 8)).pack(side="left")
        link = tk.Label(foot, text="WonderHunter", bg=C["bg"], fg=C["muted"], font=(FONT, 8, "bold"), cursor="hand2")
        link.pack(side="left", padx=(3, 0))
        link.bind("<Enter>", lambda e: link.config(fg=C["accent_hi"], font=(FONT, 8, "bold", "underline")))
        link.bind("<Leave>", lambda e: link.config(fg=C["muted"], font=(FONT, 8, "bold")))
        link.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))

    def _on_wheel(self, e):
        if self.lang_popup or self.canvas.winfo_height() >= self.list_frame.winfo_reqheight():
            return
        if e.num == 4:
            step = -1
        elif e.num == 5:
            step = 1
        elif sys.platform == "darwin":
            step = -e.delta
        else:
            step = int(-e.delta / 120)
        self.canvas.yview_scroll(step, "units")

    # ---------------------------------------------------------------- language
    def _lang_pill(self, parent):
        pill = tk.Frame(parent, bg=C["row"], highlightthickness=1, highlightbackground=C["border"], cursor="hand2")
        fl = flags.flag(pill, self.cfg["lang"], self.scale, bg=C["row"])
        fl.pack(side="left", padx=(10, 6), pady=7)
        code = tk.Label(pill, text=self.cfg["lang"].upper(), bg=C["row"], fg=C["text"], font=(FONT, 9, "bold"))
        code.pack(side="left")
        arrow = tk.Label(pill, text="▾", bg=C["row"], fg=C["muted"], font=(FONT, 9))
        arrow.pack(side="left", padx=(4, 10))
        parts = (pill, fl, code, arrow)

        def hover(on):
            for w in parts:
                w.config(bg=C["row_hi"] if on else C["row"])
        for w in parts:
            w.bind("<Enter>", lambda e: hover(True))
            w.bind("<Leave>", lambda e: hover(False))
            w.bind("<Button-1>", lambda e: self.toggle_lang_menu(pill))
        return pill

    def toggle_lang_menu(self, anchor):
        if self.lang_popup:
            self.close_lang_menu()
            return
        top = tk.Toplevel(self.root, bg=C["border"])
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        self.lang_popup = top
        inner = tk.Frame(top, bg=C["card"])
        inner.pack(padx=1, pady=1)

        for code in ORDER:
            current = code == self.cfg["lang"]
            bg = C["row_hi"] if current else C["card"]
            row = tk.Frame(inner, bg=bg, cursor="hand2")
            row.pack(fill="x")
            fl = flags.flag(row, code, self.scale, bg=bg)
            fl.pack(side="left", padx=(12, 10), pady=6)
            name = tk.Label(row, text=LANGS[code]["name"], bg=bg, fg=C["text"] if current else C["muted"],
                            font=(FONT, 10, "bold" if current else "normal"), anchor="w", width=12)
            name.pack(side="left")
            tag = tk.Label(row, text=code.upper(), bg=bg, fg=C["dim"], font=(FONT, 8, "bold"))
            tag.pack(side="right", padx=(8, 12))
            parts = (row, fl, name, tag)

            def hover(on, parts=parts, base=bg):
                for w in parts:
                    w.config(bg=C["row_hi"] if on else base)
            for w in parts:
                w.bind("<Enter>", lambda e, h=hover: h(True))
                w.bind("<Leave>", lambda e, h=hover: h(False))
                w.bind("<ButtonRelease-1>", lambda e, c=code: self.set_lang(c))

        top.update_idletasks()
        x = anchor.winfo_rootx() + anchor.winfo_width() - top.winfo_reqwidth()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 4
        top.geometry(f"+{x}+{y}")
        top.bind("<Escape>", lambda e: self.close_lang_menu())
        top.bind("<Button-1>", self._lang_click_outside)
        top.focus_force()
        top.grab_set()

    def _lang_click_outside(self, e):
        top = self.lang_popup
        if top and not (top.winfo_rootx() <= e.x_root < top.winfo_rootx() + top.winfo_width()
                        and top.winfo_rooty() <= e.y_root < top.winfo_rooty() + top.winfo_height()):
            self.close_lang_menu()

    def close_lang_menu(self):
        if self.lang_popup:
            self.lang_popup.grab_release()
            self.lang_popup.destroy()
            self.lang_popup = None

    def set_lang(self, code):
        global LANG
        self.close_lang_menu()
        if code == self.cfg["lang"]:
            return
        self.store_target()
        self.cfg["lang"] = code
        LANG = LANGS[code]
        save_config(self.cfg)
        for w in self.root.winfo_children():
            w.destroy()
        self._build()
        self.refresh_recents()

    # ---------------------------------------------------------------- recents
    def refresh_recents(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.send_buttons = [self.send_btn]
        recents = self.cfg["recents"]
        self.count_lbl.config(text=str(len(recents)) if recents else "")

        if not recents:
            tk.Label(self.list_frame, text=t("empty"), bg=C["card"], fg=C["dim"],
                     font=(FONT, 10), justify="center").pack(pady=30)
        for item in recents:
            self._recent_row(item)
        self.set_busy(self.busy)

    def _recent_row(self, item):
        path = item["path"]
        exists = os.path.isfile(path)
        is_sel = self.selected == path
        bg = C["row_hi"] if is_sel else C["row"]

        row = tk.Frame(self.list_frame, bg=bg, highlightthickness=1,
                       highlightbackground=C["accent"] if is_sel else C["row"])
        row.pack(fill="x", pady=(0, 6))

        badge = tk.Label(row, text="ELF", bg=C["accent_dim"] if exists else C["border"],
                         fg=C["accent_hi"] if exists else C["dim"], font=(FONT, 8, "bold"), width=5, pady=9)
        badge.pack(side="left", padx=(10, 10), pady=8)

        info = tk.Frame(row, bg=bg)
        info.pack(side="left", fill="x", expand=True, pady=6)
        name = tk.Label(info, text=os.path.basename(path), bg=bg, fg=C["text"] if exists else C["dim"],
                        font=(FONT, 10, "bold"), anchor="w")
        name.pack(fill="x")
        if exists:
            meta = "  ·  ".join((relative_time(item.get("last")), t("sent_n", n=item.get("count", 0)),
                                 human_size(os.path.getsize(path))))
            if LANG.get("rtl"):
                meta = "‏" + meta
            meta_fg = C["muted"]
        else:
            meta, meta_fg = t("not_found"), C["err"]
        meta_lbl = tk.Label(info, text=meta, bg=bg, fg=meta_fg, font=(FONT, 8), anchor="w")
        meta_lbl.pack(fill="x")

        rm = FlatButton(row, "✕", lambda p=path: self.remove_recent(p), kind="ghost",
                        font=(FONT, 10), padx=8, pady=4)
        rm.config(bg=bg)
        rm._bg = bg
        rm.pack(side="right", padx=(0, 8))

        btn = FlatButton(row, t("send"), lambda p=path: self.send(p), font=(FONT, 9, "bold"), padx=12, pady=5)
        btn.pack(side="right", padx=(0, 4))
        if exists:
            self.send_buttons.append(btn)
        else:
            btn.set_enabled(False)

        for w in (row, badge, info, name, meta_lbl):
            w.bind("<Button-1>", lambda e, p=path: os.path.isfile(p) and self.select(p))
            w.bind("<Double-Button-1>", lambda e, p=path: os.path.isfile(p) and self.send(p))
            w.config(cursor="hand2" if exists else "arrow")

    def remove_recent(self, path):
        self.cfg["recents"] = [r for r in self.cfg["recents"] if r["path"] != path]
        save_config(self.cfg)
        self.refresh_recents()

    def remember(self, path):
        recents = self.cfg["recents"]
        old = next((r for r in recents if os.path.normcase(r["path"]) == os.path.normcase(path)), None)
        count = old["count"] if old else 0
        recents = [r for r in recents if r is not old]
        recents.insert(0, {"path": path, "count": count + 1, "last": time.time()})
        self.cfg["recents"] = recents[:MAX_RECENTS]
        save_config(self.cfg)

    # ---------------------------------------------------------------- actions
    def browse(self):
        path = filedialog.askopenfilename(
            title=t("dialog_title"),
            initialdir=self.cfg.get("last_dir") or None,
            filetypes=[(t("ft_elf"), "*.elf"), (t("ft_bin"), "*.bin"), (t("ft_all"), "*")],
        )
        if path:
            path = os.path.normpath(path)
            self.cfg["last_dir"] = os.path.dirname(path)
            self.select(path)

    def select(self, path):
        self.selected = path
        self.sel_name.config(text=os.path.basename(path))
        self.sel_path.config(text=path)
        self.refresh_recents()

    def send_selected(self):
        if not self.selected:
            self.set_status(t("choose_first"), "warn")
            return
        self.send(self.selected)

    def store_target(self):
        self.cfg["host"] = self.host_entry.get().strip() or self.cfg["host"]
        try:
            self.cfg["port"] = int(self.port_entry.get().strip())
        except ValueError:
            pass

    def read_target(self):
        host = self.host_entry.get().strip()
        try:
            port = int(self.port_entry.get().strip())
            if not 0 < port < 65536:
                raise ValueError
        except ValueError:
            self.set_status(t("invalid_port"), "err")
            return None
        if not host:
            self.set_status(t("missing_ip"), "err")
            return None
        self.cfg["host"], self.cfg["port"] = host, port
        return host, port

    def send(self, path):
        if self.busy:
            return
        if not os.path.isfile(path):
            self.set_status(t("file_missing", path=path), "err")
            return
        target = self.read_target()
        if not target:
            return
        host, port = target
        if self.selected != path:
            self.select(path)
        self.set_busy(True)
        self.progress["value"] = 0
        name = os.path.basename(path)
        where = f"{host}:{port}"
        self.set_status(t("sending", name=name, target=where), "accent")

        def worker():
            try:
                size = send_payload(host, port, path, lambda s, tot: self.events.put(("progress", s / tot)))
                self.events.put(("done", path, name, size, where))
            except socket.timeout:
                self.events.put(("error", name, "timeout", {}))
            except ConnectionRefusedError:
                self.events.put(("error", name, "refused", {"target": where}))
            except OSError as e:
                self.events.put(("error", name, "net_error", {"err": e.strerror or str(e)}))

        threading.Thread(target=worker, daemon=True).start()

    def poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "progress":
                    self.progress["value"] = ev[1]
                elif ev[0] == "done":
                    _, path, name, size, where = ev
                    msg = t("sent_ok", name=name, size=human_size(size), target=where)
                    self.progress["value"] = 1.0
                    self.remember(path)
                    self.set_busy(False)
                    self.refresh_recents()
                    self.set_status(msg, "ok")
                    self.notifier.notify(t("notif_ok"), msg)
                elif ev[0] == "error":
                    _, name, key, kw = ev
                    msg = t(key, **kw)
                    self.progress["value"] = 0
                    self.set_busy(False)
                    self.set_status(msg, "err")
                    self.notifier.notify(t("notif_fail", name=name), msg, error=True)
        except queue.Empty:
            pass
        self.root.after(50, self.poll_events)

    def set_busy(self, busy):
        self.busy = busy
        for b in self.send_buttons:
            b.set_enabled(not busy)

    def set_status(self, text, kind="muted"):
        self.dot.config(fg=C.get(kind, C["muted"]))
        self.status.config(text=text, fg=C["text"] if kind in ("ok", "err", "accent") else C["muted"])

    def on_close(self):
        self.store_target()
        save_config(self.cfg)
        self.notifier.remove()
        self.root.destroy()


def main():
    global FONT
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    FONT = pick_font(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
