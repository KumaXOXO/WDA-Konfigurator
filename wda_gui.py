#!/usr/bin/env python3
"""WDA Konfigurator – Oberfläche im Stil der Wireless-Display-Adapter-App.

Inoffizielles Werkzeug für den Microsoft Wireless Display Adapter (Gen 1, Gen 1.5, Gen 3;
am echten Gerät getestet nur mit Gen 1.5).
Die Kommunikation mit dem Adapter steckt in wda_tool.py.
"""
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import i18n
import wda_tool as wda
from i18n import T

APP_NAME = "WDA Konfigurator"
APP_VERSION = "2.0"
DEFAULT_TYPE = "Gen-1.5"           # Firmware-Seite ohne verbundenen Adapter
TESTED_TYPES = {"Gen-1.5"}         # nur damit am echten Gerät getestet
CONNECT_URI = "ms-settings-connectabledevices:devicediscovery"   # wie in der Original-App

PALETTES = {
    "light": dict(bg="#F3F3F3", pane="#EBEBEB", card="#FBFBFB", card_border="#E5E5E5", divider="#EAEAEA",
                  text="#1B1B1B", text2="#5D5D5D", disabled="#A0A0A0", accent="#005FB8", accent_hover="#1A6FC2",
                  on_accent="#FFFFFF", ctrl="#FDFDFD", ctrl_hover="#F6F6F6", ctrl_border="#D0D0D0",
                  input="#FFFFFF", nav_sel="#E0E0E0", nav_hover="#E6E6E6", ok="#0F7B0F", warn="#9D5D00",
                  err="#C42B1C", info_bg="#F4F9FD", warn_bg="#FFF4CE", err_bg="#FDE7E9", ok_bg="#DFF6DD"),
    "dark": dict(bg="#202020", pane="#1C1C1C", card="#2B2B2B", card_border="#1D1D1D", divider="#3A3A3A",
                 text="#FFFFFF", text2="#C5C5C5", disabled="#787878", accent="#60CDFF", accent_hover="#5AB8E6",
                 on_accent="#000000", ctrl="#2D2D2D", ctrl_hover="#323232", ctrl_border="#3F3F3F",
                 input="#1F1F1F", nav_sel="#2D2D2D", nav_hover="#292929", ok="#6CCB5F", warn="#FCE100",
                 err="#FF99A4", info_bg="#2B3A45", warn_bg="#433519", err_bg="#442726", ok_bg="#393D1B"),
}

# Segoe Fluent Icons / Segoe MDL2 Assets
IC = dict(nav="", adapter="", rename="", lang="", bright="", fit="",
          power="", sync="", info="", ok="", warn="", err="",
          refresh="", search="", copy="", lock="")


def resource(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def system_theme():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
    except OSError:
        return "light"


# --- Bausteine im Fluent-Stil -----------------------------------------------
class FButton(tk.Label):
    def __init__(self, parent, app, text, command, accent=False, icon=None):
        self.app, self.c, self.command, self.accent, self.enabled = app, app.c, command, accent, True
        label = f"{icon}  {text}" if icon else text
        super().__init__(parent, text=label, font=app.f_body, padx=14, pady=5, bd=0,
                         highlightthickness=1, cursor="hand2")
        if icon:
            self.configure(font=app.f_body)
        self.bind("<Enter>", lambda e: self._paint(True))
        self.bind("<Leave>", lambda e: self._paint(False))
        self.bind("<ButtonRelease-1>", self._click)
        self._paint(False)

    def _click(self, _):
        if self.enabled and self.command:
            self.command()

    def _paint(self, hover):
        c = self.c
        if not self.enabled:
            bg, fg, br = (c.divider, c.disabled, c.divider) if self.accent else (c.ctrl, c.disabled, c.ctrl_border)
        elif self.accent:
            bg = c.accent_hover if hover else c.accent
            fg, br = c.on_accent, bg
        else:
            bg, fg, br = (c.ctrl_hover if hover else c.ctrl), c.text, c.ctrl_border
        self.configure(bg=bg, fg=fg, highlightbackground=br, highlightcolor=br,
                       cursor="hand2" if self.enabled else "arrow")

    def set_enabled(self, on):
        self.enabled = on
        self._paint(False)


class FLink(tk.Label):
    def __init__(self, parent, app, text, command, bg):
        super().__init__(parent, text=text, font=app.f_body, fg=app.c.accent, bg=bg, cursor="hand2", bd=0)
        self.bind("<ButtonRelease-1>", lambda e: command())
        self.bind("<Enter>", lambda e: self.configure(font=app.f_body_ul))
        self.bind("<Leave>", lambda e: self.configure(font=app.f_body))


class FToggle(tk.Canvas):
    """Umschalter wie ToggleSwitch: Klick ruft command(neuer_wert) – der Wert wird erst nach Erfolg gesetzt."""

    def __init__(self, parent, app, value, command, bg):
        super().__init__(parent, width=44, height=22, bg=bg, highlightthickness=0, cursor="hand2")
        self.app, self.value, self.command, self.enabled = app, value, command, True
        self.bind("<ButtonRelease-1>", lambda e: self.enabled and self.command(not self.value))
        self._paint()

    def _paint(self):
        c = self.app.c
        self.delete("all")
        on = self.value
        fill = (c.accent if on else c.ctrl) if self.enabled else c.divider
        outline = fill if on else (c.text2 if self.enabled else c.disabled)
        self.create_oval(1, 1, 21, 21, fill=fill, outline=outline)
        self.create_oval(23, 1, 43, 21, fill=fill, outline=outline)
        self.create_rectangle(11, 1, 33, 21, fill=fill, outline="")
        self.create_line(11, 1, 33, 1, fill=outline)
        self.create_line(11, 21, 33, 21, fill=outline)
        knob = c.on_accent if on else (c.text2 if self.enabled else c.disabled)
        x = 33 if on else 11
        self.create_oval(x - 6, 5, x + 6, 17, fill=knob, outline="")

    def set_enabled(self, on):
        self.enabled = on
        self._paint()


class Spinner(tk.Canvas):
    def __init__(self, parent, app, size=20, bg=None):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0)
        self.app, self.size, self.angle = app, size, 0
        self._spin()

    def _spin(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        s = self.size
        self.create_arc(2, 2, s - 2, s - 2, start=self.angle, extent=100, style="arc",
                        outline=self.app.c.accent, width=2.5)
        self.angle = (self.angle - 12) % 360
        self.after(30, self._spin)


class NavItem(tk.Frame):
    def __init__(self, parent, app, icon, text, command):
        c = app.c
        super().__init__(parent, bg=c.pane, cursor="hand2")
        self.app, self.selected = app, False
        self.bar = tk.Frame(self, width=3, height=16, bg=c.pane)
        self.bar.pack(side="left", padx=(4, 0))
        self.icon = tk.Label(self, text=icon, font=app.f_icon, bg=c.pane, fg=c.text, width=3)
        self.icon.pack(side="left", padx=(6, 0), pady=9)
        self.label = tk.Label(self, text=text, font=app.f_body, bg=c.pane, fg=c.text, anchor="w")
        self.label.pack(side="left", fill="x", expand=True, padx=(4, 12))
        for w in (self, self.bar, self.icon, self.label):
            w.bind("<ButtonRelease-1>", lambda e: command())
            w.bind("<Enter>", lambda e: self._paint(True))
            w.bind("<Leave>", lambda e: self._paint(False))

    def _paint(self, hover=False):
        c = self.app.c
        bg = c.nav_sel if self.selected else (c.nav_hover if hover else c.pane)
        for w in (self, self.icon, self.label):
            w.configure(bg=bg)
        self.bar.configure(bg=c.accent if self.selected else bg)

    def set_selected(self, on):
        self.selected = on
        self._paint()

    def set_compact(self, compact):
        if compact:
            self.label.pack_forget()
        else:
            self.label.pack(side="left", fill="x", expand=True, padx=(4, 12))


class FScrollbar(tk.Canvas):
    """Bildlaufleiste wie in Windows 11: schmaler Strich, beim Darüberfahren breiter, ohne Überlauf unsichtbar."""

    def __init__(self, parent, app, command):
        self.app, self.command = app, command
        self.w = app.px(14)
        super().__init__(parent, width=self.w, bg=app.c.bg, highlightthickness=0, bd=0)
        self.first, self.last, self.hover, self.drag = 0.0, 1.0, False, None
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    def _geom(self):
        pad = self.app.px(4)
        track = max(self.winfo_height() - 2 * pad, 1)
        y1 = pad + self.first * track
        y2 = max(pad + self.last * track, y1 + self.app.px(28))
        return pad, track, y1, y2

    def _draw(self):
        self.delete("all")
        if self.last - self.first >= 0.999:        # alles sichtbar → ausblenden
            return
        c, px = self.app.c, self.app.px
        _, _, y1, y2 = self._geom()
        wide = self.hover or self.drag is not None
        thick = px(6) if wide else px(3)
        x = self.w - px(6)
        if wide:   # dezente Schiene wie bei Windows 11
            self.create_line(x, px(6), x, self.winfo_height() - px(6), width=thick, fill=c.divider,
                             capstyle="round")
        self.create_line(x, y1 + thick / 2, x, y2 - thick / 2, width=thick,
                         fill=c.text2 if wide else c.disabled, capstyle="round")

    def _hover(self, on):
        self.hover = on
        self._draw()

    def _press(self, e):
        _, _, y1, y2 = self._geom()
        if y1 <= e.y <= y2:
            self.drag = e.y - y1
        else:
            self.command("scroll", 1 if e.y > y2 else -1, "pages")

    def _motion(self, e):
        if self.drag is not None:
            pad, track, _, _ = self._geom()
            self.command("moveto", (e.y - self.drag - pad) / track)

    def _release(self, _):
        self.drag = None
        self._draw()


class ScrollArea(tk.Frame):
    """Senkrecht scrollbarer Bereich mit begrenzter Inhaltsbreite; Inhalt kommt in .inner.

    Beim Ziehen am Fensterrand wird live nachgezogen (höchstens alle ~16 ms, dazwischen nur
    die letzte Breite merken). on_width(breite) passt Umbrüche und Zeilen an; das Neuzeichnen
    passiert gebündelt in einem Schritt (WM_SETREDRAW), damit nichts flackert.
    """

    def __init__(self, parent, app, max_width, on_width):
        super().__init__(parent, bg=app.c.bg)
        self.max_width, self.on_width = max_width, on_width
        self.canvas = tk.Canvas(self, bg=app.c.bg, highlightthickness=0, bd=0, yscrollincrement=app.px(24))
        self.sb = FScrollbar(self, app, self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=app.c.bg)
        self.win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=(0, 0, e.width, e.height)))
        self.canvas.bind("<Configure>", self._resized)
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self._job, self._pending, self.width = None, None, None

    def _resized(self, e):
        self._pending = e.width
        if self._job is None:         # sofort anwenden, weitere Ereignisse kurz sammeln
            self._run()

    def _run(self):
        self._job = None
        if self._pending is None:
            return
        w, self._pending = self._pending, None
        self.apply(w)
        self._job = self.after(16, self._run)

    def apply(self, width):
        w = max(min(width, self.max_width), 1)
        if w == self.width:
            return
        self.width = w
        frozen = self._redraw(False)
        try:
            self.on_width(w)
            self.canvas.itemconfigure(self.win, width=w)
            self.update_idletasks()
        finally:
            if frozen:
                self._redraw(True)

    def _redraw(self, on):
        """Zeichnen des Inhalts unter Windows kurz anhalten bzw. wieder einschalten und neu zeichnen."""
        try:
            import ctypes
            u = ctypes.windll.user32
            hwnd = self.winfo_id()
            u.SendMessageW(hwnd, 0x000B, 1 if on else 0, 0)            # WM_SETREDRAW
            if on:   # RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW
                u.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100)
            return True
        except Exception:
            return False

    def _wheel(self, e):
        if self.canvas.winfo_exists() and self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120) * 2, "units")


class Palette:
    def __init__(self, d):
        self.__dict__.update(d)


# --- Hauptfenster -------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.c = Palette(PALETTES[system_theme()])
        self.title(APP_NAME)
        self.s = self.winfo_fpixels("1i") / 96          # Windows-Skalierung (1.0 = 100 %)
        w = min(self.px(1060), int(self.winfo_screenwidth() * 0.9))
        h = min(self.px(800), int(self.winfo_screenheight() * 0.85))
        x = (self.winfo_screenwidth() - w) // 2
        y = max((self.winfo_screenheight() - h) // 3, 0)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(min(self.px(620), w), min(self.px(460), h))
        self.responsive = []            # Funktionen f(inhaltsbreite) für Umbrüche/Zeilenlayout der Seite
        self.narrow = False             # Listenansicht aktiv (schmales Fenster)
        self.glitches = []              # Zeitpunkte, zu denen die Verbindung unterbrochen war
        self.connected_at = 0.0
        self._shown_unstable = False
        self.compact_user = None        # vom Nutzer per ☰ gewählt (None = automatisch nach Fensterbreite)
        self.configure(bg=self.c.bg)
        try:
            self.iconbitmap(default=str(resource("wda.ico")))
        except tk.TclError:
            pass
        self._fonts()
        self._styles()

        self.events = queue.Queue()
        self.busy = False          # Schreibvorgang läuft
        self.checking = False      # Hintergrundsuche/-prüfung läuft
        self.adapter = None
        self.info = {}
        self.password = None
        self.ping_failures = 0
        self.need_reboot = False
        self.last_ip = None
        self.fw = {"running": False, "pct": 0, "text": "", "result": None}
        self.log_lines = []
        self.page = "adapter"
        self.compact = False
        self.fw_dl = None               # (Prozent, Text) während des Firmware-Downloads
        self._load_fw_library(DEFAULT_TYPE)

        self._build_shell()
        self.show_page("adapter")
        self.after(100, self._drain_events)
        self.after(300, self._tick)
        self.after(50, self._dark_titlebar)

    def px(self, n):
        """Pixelmaß passend zur Windows-Skalierung (Basis: 120 % Anzeige)."""
        return round(n * self.s / 1.2)

    # Schriften, Stile -----------------------------------------------------------
    def _fonts(self):
        import tkinter.font as tkfont
        fam = set(tkfont.families())
        disp = "Segoe UI Variable Display" if "Segoe UI Variable Display" in fam else "Segoe UI"
        text = "Segoe UI Variable Text" if "Segoe UI Variable Text" in fam else "Segoe UI"
        icons = "Segoe Fluent Icons" if "Segoe Fluent Icons" in fam else "Segoe MDL2 Assets"
        # Segoe UI hat keine CJK-/Thai-Zeichen – dafür die Windows-UI-Schrift der Sprache nehmen
        script_fonts = {"ja-JP": "Yu Gothic UI", "ko-KR": "Malgun Gothic", "zh-CN": "Microsoft YaHei UI",
                        "zh-TW": "Microsoft JhengHei UI", "th-TH": "Leelawadee UI"}
        special = script_fonts.get(i18n.current())
        if special in fam:
            disp = text = special
        self.f_title = (disp, 21, "bold")
        self.f_subtitle = (disp, 14, "bold")
        self.f_strong = (text, 10, "bold")
        self.f_body = (text, 10)
        self.f_body_ul = (text, 10, "underline")
        self.f_caption = (text, 9)
        self.f_icon = (icons, 12)
        self.f_icon_big = (icons, 32)
        self.f_mono = ("Consolas", 9)

    def _styles(self):
        c = self.c
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure("TCombobox", fieldbackground=c.input, background=c.ctrl, foreground=c.text,
                     arrowcolor=c.text, bordercolor=c.ctrl_border, lightcolor=c.input, darkcolor=c.input,
                     padding=5)
        st.map("TCombobox", fieldbackground=[("readonly", c.input), ("disabled", c.ctrl)],
               foreground=[("readonly", c.text), ("disabled", c.disabled)],
               selectbackground=[("readonly", c.input)], selectforeground=[("readonly", c.text)],
               bordercolor=[("focus", c.accent)])
        self.option_add("*TCombobox*Listbox.background", c.card)
        self.option_add("*TCombobox*Listbox.foreground", c.text)
        self.option_add("*TCombobox*Listbox.selectBackground", c.accent)
        self.option_add("*TCombobox*Listbox.selectForeground", c.on_accent)
        self.option_add("*TCombobox*Listbox.font", self.f_body)
        st.configure("Fluent.Horizontal.TProgressbar", troughcolor=c.divider, background=c.accent,
                     bordercolor=c.divider, lightcolor=c.accent, darkcolor=c.accent, thickness=4)

    def _dark_titlebar(self):
        if self.c.bg != PALETTES["dark"]["bg"]:
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            val = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass

    # Rahmen: Navigation + Inhalt ---------------------------------------------------
    def _build_shell(self):
        c = self.c
        self.nav = tk.Frame(self, bg=c.pane)
        self.nav.pack(side="left", fill="y")
        self.nav.pack_propagate(False)
        top = tk.Frame(self.nav, bg=c.pane)
        top.pack(fill="x", pady=(8, 8))
        burger = tk.Label(top, text=IC["nav"], font=self.f_icon, bg=c.pane, fg=c.text, width=3, cursor="hand2")
        burger.pack(side="left", padx=(self.px(8), 0), pady=6)
        burger.bind("<ButtonRelease-1>", lambda e: self.toggle_nav())
        self.nav_title = tk.Label(top, text="Wireless Display Adapter", font=self.f_body, bg=c.pane, fg=c.text)
        self.nav_title.pack(side="left", padx=(self.px(6), self.px(16)))

        self.nav_items = {
            "adapter": NavItem(self.nav, self, IC["adapter"], T("My adapter"), lambda: self.show_page("adapter")),
            "firmware": NavItem(self.nav, self, IC["sync"], T("Firmware"), lambda: self.show_page("firmware")),
        }
        for item in self.nav_items.values():
            item.pack(fill="x", padx=4, pady=1)
        about = NavItem(self.nav, self, IC["info"], T("About"), lambda: self.show_page("about"))
        about.pack(side="bottom", fill="x", padx=4, pady=(1, 10))
        self.nav_items["about"] = about

        # Breite aus dem tatsächlichen Platzbedarf der Texte (Schrift/Skalierung) statt fest
        self.update_idletasks()
        need = max([top.winfo_reqwidth()] + [i.winfo_reqwidth() + 8 for i in self.nav_items.values()])
        self.nav_w = max(need, self.px(200))
        self.nav_w_compact = burger.winfo_reqwidth() + self.px(8) * 2
        self.nav.configure(width=self.nav_w)

        self.content = tk.Frame(self, bg=c.bg)
        self.content.pack(side="left", fill="both", expand=True)
        self.bind("<Configure>", self._on_window_resize)

    def _on_window_resize(self, e):
        if e.widget is self:
            self._auto_compact()

    def _auto_compact(self):
        """Wie NavigationView: bei schmalem Fenster nur Symbole zeigen."""
        want = self.winfo_width() < self.px(900) if self.compact_user is None else self.compact_user
        if want != self.compact:
            self._set_compact(want)

    def toggle_nav(self):
        self.compact_user = not self.compact
        self._set_compact(self.compact_user)

    def _set_compact(self, compact):
        self.compact = compact
        self.nav.configure(width=self.nav_w_compact if compact else self.nav_w)
        for item in self.nav_items.values():
            item.set_compact(compact)
        if compact:
            self.nav_title.pack_forget()
        else:
            self.nav_title.pack(side="left", padx=(self.px(6), self.px(16)))

    def show_page(self, name):
        self.page = name
        for k, item in self.nav_items.items():
            item.set_selected(k == name)
        self.render()

    def render(self):
        """Seite komplett neu aufbauen (Zustand liegt in self.* und self.fw)."""
        for w in self.content.winfo_children():
            w.destroy()
        self.fw_widgets = None
        self.responsive = []
        self.body_pad = (self.px(36), self.px(28))
        area = ScrollArea(self.content, self, self.px(1250), self._layout)
        area.pack(fill="both", expand=True)
        body = tk.Frame(area.inner, bg=self.c.bg)
        body.pack(fill="both", expand=True, padx=self.body_pad, pady=(self.px(28), self.px(28)))
        {"adapter": self._page_adapter, "firmware": self._page_firmware, "about": self._page_about}[self.page](body)
        # Layout sofort für die aktuelle Breite rechnen (kein Springen beim Aufbau)
        self.update_idletasks()
        area.apply(max(self.content.winfo_width() - area.sb.w, self.px(400)))

    def _layout(self, width):
        bw = width - sum(self.body_pad)
        self.narrow = bw < self.px(680)      # darunter: Listenansicht (Steuerelemente unter dem Text)
        for f in self.responsive:
            f(bw)

    def set_wrap(self, label, value, minimum=None):
        """Umbruchbreite in 16-px-Stufen setzen – nur wenn sie sich wirklich ändert (spart Neuberechnungen)."""
        step = self.px(16)
        value = max(minimum or self.px(160), value)
        value -= value % step
        if getattr(label, "_wrap", None) != value:
            label._wrap = value
            label.configure(wraplength=value)

    def wrap(self, label, margin):
        """Umbruchbreite eines Labels an die Inhaltsbreite koppeln (Breite minus margin)."""
        self.responsive.append(lambda bw: self.set_wrap(label, bw - margin))
        return label

    # Kleine Bauhelfer ----------------------------------------------------------------
    def title_label(self, parent, text):
        tk.Label(parent, text=text, font=self.f_title, bg=self.c.bg, fg=self.c.text).pack(anchor="w", pady=(0, 18))

    def section(self, parent, text):
        tk.Label(parent, text=text, font=self.f_strong, bg=self.c.bg, fg=self.c.text).pack(anchor="w", pady=(18, 6))

    def card(self, parent, pady=(0, 0)):
        f = tk.Frame(parent, bg=self.c.card, highlightthickness=1, highlightbackground=self.c.card_border)
        f.pack(fill="x", pady=pady)
        return f

    def row(self, card, icon, title, desc, first=False):
        """Einstellungszeile wie in den Windows-Einstellungen; liefert Frame für Steuerelemente."""
        c = self.c
        if not first:
            tk.Frame(card, bg=c.divider, height=1).pack(fill="x")
        r = tk.Frame(card, bg=c.card)
        pad = self.px(16)
        r.pack(fill="x", padx=pad, pady=self.px(12))
        ico = tk.Label(r, text=icon, font=self.f_strong if icon.isdigit() else self.f_icon, bg=c.card, fg=c.text,
                       width=2)
        ico.pack(side="left", anchor="n", pady=2)
        col = tk.Frame(r, bg=c.card)
        col.pack(side="left", fill="x", expand=True, padx=(self.px(12), 0))
        txt = tk.Frame(col, bg=c.card)
        ctl = tk.Frame(col, bg=c.card)
        labels = [tk.Label(txt, text=title, font=self.f_body, bg=c.card, fg=c.text, anchor="w", justify="left")]
        if desc:
            labels.append(tk.Label(txt, text=desc, font=self.f_caption, bg=c.card, fg=c.text2, anchor="w",
                                   justify="left"))
        for lab in labels:
            lab.pack(anchor="w")
        state = {"mode": None}

        def layout(bw):
            # Breite der Textspalte = Kartenbreite – Ränder – Symbol – Abstand
            inner = bw - 2 - 2 * pad - ico.winfo_reqwidth() - self.px(12)
            ctl_w = ctl.winfo_reqwidth() if ctl.winfo_children() else 0
            narrow = ctl_w and (self.narrow or inner - ctl_w < self.px(240))
            mode = "narrow" if narrow else "wide"
            if mode != state["mode"]:
                state["mode"] = mode
                txt.pack_forget()
                ctl.pack_forget()
                if narrow:      # Steuerelemente unter den Text
                    txt.pack(side="top", fill="x")
                    ctl.pack(side="top", anchor="w", pady=(self.px(8), 0))
                else:
                    ctl.pack(side="right")
                    txt.pack(side="left", fill="x", expand=True, padx=(0, self.px(12)))
            wrap = inner if narrow else inner - ctl_w - self.px(16)
            for lab in labels:
                self.set_wrap(lab, wrap, self.px(140))

        layout(self.px(800))
        self.responsive.append(layout)
        return ctl

    def infobar(self, parent, kind, title, text, action=None, inset=0):
        """Hinweisbalken (InfoBar). inset = zusätzlicher Randabstand, wenn er in einer Karte steckt."""
        c = self.c
        bg = {"info": c.info_bg, "warn": c.warn_bg, "err": c.err_bg, "ok": c.ok_bg}[kind]
        fg = {"info": c.accent, "warn": c.warn, "err": c.err, "ok": c.ok}[kind]
        icon = {"info": IC["info"], "warn": IC["warn"], "err": IC["err"], "ok": IC["ok"]}[kind]
        f = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=c.card_border)
        f.pack(fill="x", pady=(0, 12))
        ico = tk.Label(f, text=icon, font=self.f_icon, bg=bg, fg=fg)
        ico.pack(side="left", padx=(14, 10), pady=12, anchor="n")
        btn = None
        if action:
            btn = FButton(f, self, action[0], action[1])
            btn.pack(side="right", padx=12)
        t = tk.Frame(f, bg=bg)
        t.pack(side="left", fill="x", expand=True, pady=10)
        lab_title = tk.Label(t, text=title, font=self.f_strong, bg=bg, fg=c.text, anchor="w", justify="left")
        lab_title.pack(anchor="w")
        labs = [lab_title]
        if text:
            labs.append(tk.Label(t, text=text, font=self.f_body, bg=bg, fg=c.text, justify="left", anchor="w"))
            labs[-1].pack(anchor="w")

        def layout(bw):
            used = inset + 2 + 24 + ico.winfo_reqwidth() + (btn.winfo_reqwidth() + 24 if btn else 12)
            for lab in labs:
                self.set_wrap(lab, bw - used, self.px(140))

        self.responsive.append(layout)
        return f

    def entry(self, parent, width=26, show=None):
        c = self.c
        e = tk.Entry(parent, width=width, font=self.f_body, bg=c.input, fg=c.text, insertbackground=c.text,
                     relief="flat", highlightthickness=1, highlightbackground=c.ctrl_border,
                     highlightcolor=c.accent, show=show or "")
        return e

    # Seite: Mein Adapter ---------------------------------------------------------------
    def _page_adapter(self, body):
        c = self.c
        self.title_label(body, T("My adapter"))
        if not self.adapter:
            self._connect_view(body)
            return
        self._stability_bar(body)
        info = self.info
        if self.need_reboot:
            self.infobar(body, "warn", T("Restart required"),
                         T("You must restart your adapter for the change to take effect."),
                         (T("Restart adapter"), self.on_reboot))

        hero = self.card(body)
        h = tk.Frame(hero, bg=c.card)
        h.pack(fill="x", padx=20, pady=18)
        tk.Label(h, text=IC["adapter"], font=self.f_icon_big, bg=c.card, fg=c.accent).pack(side="left", padx=(0, 18),
                                                                                          anchor="n")
        btn = FButton(h, self, T("Refresh"), self.reload_info)
        btn.pack(side="right")
        t = tk.Frame(h, bg=c.card)
        t.pack(side="left", fill="x", expand=True)
        hero_mode = {"narrow": None}

        def hero_layout(bw):
            # Listenansicht: Button unter den Namen statt rechts daneben
            if self.narrow != hero_mode["narrow"]:
                hero_mode["narrow"] = self.narrow
                btn.pack_forget()
                if self.narrow:
                    btn.pack(in_=t, side="bottom", anchor="w", pady=(self.px(10), 0))
                    btn.lift(t)          # sonst liegt der Button hinter dem Textbereich
                else:
                    btn.pack(side="right", before=t)

        self.responsive.append(hero_layout)
        self.wrap(tk.Label(t, text=info["name"], font=self.f_subtitle, bg=c.card, fg=c.text, justify="left"),
                  self.px(290)).pack(anchor="w")
        dot = tk.Frame(t, bg=c.card)
        dot.pack(anchor="w", pady=(2, 0))
        tk.Label(dot, text="●", font=self.f_caption, bg=c.card, fg=c.ok).pack(side="left", anchor="n")
        self.wrap(tk.Label(dot, text=" " + T("Connected  ·  {type}  ·  Firmware {version}").format(
                               type=info["type"], version=info["version"]),
                           font=self.f_caption, bg=c.card, fg=c.text2, justify="left"),
                  self.px(310)).pack(side="left")

        if info.get("protected"):
            self.infobar(body, "info", T("Password protection is on"),
                         T("You'll be asked for the adapter password before changing settings."))

        self.section(body, T("Adapter settings"))
        card = self.card(body)
        ctl = self.row(card, IC["rename"], T("Adapter name"),
                       T("1–32 characters: a–z, A–Z, 0–9, + - _ ( ) { } [ ]  (no spaces or accented "
                         "letters)"), first=True)
        self.name_entry = self.entry(ctl, 24)
        self.name_entry.insert(0, info["name"])
        self.name_entry.pack(side="left", ipady=4, padx=(0, 8))
        self.btn_rename = FButton(ctl, self, T("Apply"), self.on_rename)
        self.btn_rename.pack(side="left")

        ctl = self.row(card, IC["lang"], T("Language"), T("Language of the text the adapter shows on the display"))
        self.lang_codes = info["languages"]
        names = [f"{wda.LANGUAGES.get(code.lower(), code)}  ({code})" for code in self.lang_codes]
        self.lang_box = ttk.Combobox(ctl, values=names, state="readonly", width=22, font=self.f_body)
        for i, code in enumerate(self.lang_codes):
            if code.lower() == info["lang"].lower():
                self.lang_box.current(i)
        self.lang_box.pack(side="left", padx=(0, 8))
        self.btn_lang = FButton(ctl, self, T("Apply"), self.on_language)
        self.btn_lang.pack(side="left")

        if info.get("wallpaper") is not None:
            self._wallpaper_section(body)

        self.section(body, T("Display preferences"))
        card = self.card(body)
        ctl = self.row(card, IC["bright"], T("Brightness"),
                       T("The adapter has no brightness control – the Microsoft app doesn't offer one "
                         "either. Adjust brightness on the display or projector itself."), first=True)
        tk.Label(ctl, text=T("Not available"), font=self.f_body, bg=c.card, fg=c.disabled).pack()
        ov = info.get("overscan") or {}
        ctl = self.row(card, IC["fit"], T("Fit to display (overscan)"),
                       T("Read-only: the allowed value range is unknown, so nothing is changed here."))
        auto = T("automatic") if str(ov.get("IsAutoAdjust")).lower() == "true" else T("manual")
        tk.Label(ctl, text=T("{mode}, value {value}").format(mode=auto, value=ov.get("OverscanSettingValue", "–")),
                 font=self.f_body, bg=c.card, fg=c.text2).pack()

        self.section(body, T("Security"))
        card = self.card(body)
        first = True
        if info.get("pbc") in ("Auto", "Disabled", "Manual"):
            ctl = self.row(card, IC["lock"], T("Enter a PIN when connecting a new device"),
                           T("When connecting, the adapter shows a PIN on the display that must be entered on "
                             "the PC. The adapter generates the PIN; it can't be chosen."),
                           first=True)
            self.tg_pin = FToggle(ctl, self, info["pbc"] == "Disabled", self.on_pin, c.card)
            self.tg_pin.pack()
            first = False
        ctl = self.row(card, IC["lock"], T("Require a password to change adapter settings"),
                       T("Protects this adapter's settings. 6–64 characters: a–z, A–Z, 0–9, + - _ ( ) { } "
                         "[ ]. Forgot it? Hold the reset button on the adapter for 10 seconds."), first=first)
        if info.get("protected"):
            self.btn_pw = FButton(ctl, self, T("Change password"), self.on_change_password)
            self.btn_pw.pack(side="left", padx=(0, 12))
        self.tg_pw = FToggle(ctl, self, bool(info.get("protected")), self.on_password_toggle, c.card)
        self.tg_pw.pack(side="left")

        self.section(body, T("Adapter"))
        card = self.card(body)
        ctl = self.row(card, IC["power"], T("Restart adapter"),
                       T("If a change only takes effect after a restart, the app will tell you."),
                       first=True)
        self.btn_reboot = FButton(ctl, self, T("Restart"), self.on_reboot)
        self.btn_reboot.pack()
        ctl = self.row(card, IC["refresh"], T("Reset to default settings"),
                       T("Clears all custom settings (name, language, password, wallpaper); the adapter "
                         "then restarts."))
        self.btn_reset = FButton(ctl, self, T("Reset"), self.on_reset)
        self.btn_reset.pack()
        self._update_buttons()

    def _wallpaper_section(self, body):
        c = self.c
        self.section(body, T("Wallpaper"))
        card = self.card(body)
        inner = tk.Frame(card, bg=c.card)
        inner.pack(fill="x", padx=16, pady=14)
        self.wrap(tk.Label(inner, text=T("Image the adapter shows on the display while no device is connected."), font=self.f_caption, bg=c.card, fg=c.text2, justify="left"),
                  self.px(50)).pack(anchor="w", pady=(0, 10))
        row = tk.Frame(inner, bg=c.card)
        row.pack(anchor="w")
        self.wp_images = []
        current = self.info.get("wallpaper")
        tiles = []
        for wid in (1, 2, 3, 4):
            sel = wid == current
            f = tk.Frame(row, bg=c.accent if sel else c.card_border, padx=3 if sel else 1, pady=3 if sel else 1,
                         cursor="hand2")
            img = self._wallpaper_thumb(wid)
            if img:
                self.wp_images.append(img)
                lbl = tk.Label(f, image=img, bd=0, bg=c.card)
            else:
                lbl = tk.Label(f, text=T("Image {n}").format(n=wid), width=16, height=4, font=self.f_body,
                               bg=c.ctrl, fg=c.text)
            lbl.pack()
            for w in (f, lbl):
                w.bind("<ButtonRelease-1>", lambda e, i=wid: self.on_wallpaper(i))
            tiles.append(f)
        gap = self.px(10)
        state = {"cols": None}

        def layout(bw):
            # so viele Vorschaubilder pro Zeile, wie hineinpassen
            tile_w = max(t.winfo_reqwidth() for t in tiles) + gap
            cols = max(1, min(4, (bw - self.px(40)) // tile_w))
            if cols != state["cols"]:
                state["cols"] = cols
                for i, t in enumerate(tiles):
                    t.grid(row=i // cols, column=i % cols, padx=(0, gap), pady=(0, gap), sticky="w")

        layout(self.px(800))
        self.responsive.append(layout)
        b = tk.Frame(inner, bg=c.card)
        b.pack(anchor="w", pady=(12, 0))
        self.btn_wp = FButton(b, self, T("Upload your own image …"), self.on_custom_wallpaper)
        self.btn_wp.pack(side="left")
        if current not in (1, 2, 3, 4):
            tk.Label(b, text=T("   Current: custom image"), font=self.f_body, bg=c.card, fg=c.text2).pack(side="left")

    def _wallpaper_thumb(self, wid):
        """Vorschau der vorinstallierten Bilder: eingebettet (build/thumbs) oder aus app-source."""
        big = self.s >= 1.75            # ab 175 % Skalierung die doppelt so großen Vorschaubilder
        candidates = [(resource("thumbs") / f"{wid}.png", 1 if big else 2),
                      (Path(__file__).resolve().parent / "build" / "thumbs" / f"{wid}.png", 1 if big else 2),
                      (Path(__file__).resolve().parent / "app-source" / "Images" / "Wallpapers" / f"{wid}.png",
                       7 if big else 13)]
        for p, sub in candidates:
            if p.exists():
                try:
                    img = tk.PhotoImage(file=str(p))
                    return img.subsample(sub) if sub > 1 else img
                except tk.TclError:
                    return None
        return None

    def _connect_view(self, body):
        c = self.c
        card = self.card(body)
        inner = tk.Frame(card, bg=c.card)
        inner.pack(fill="x", padx=28, pady=26)
        tk.Label(inner, text=IC["adapter"], font=self.f_icon_big, bg=c.card, fg=c.text2).pack(anchor="w")
        self.wrap(tk.Label(inner, text=T("Connect your device to edit settings"),
                           font=self.f_subtitle, bg=c.card, fg=c.text, justify="left"),
                  self.px(70)).pack(anchor="w", pady=(12, 6))
        self.wrap(tk.Label(inner, justify="left", font=self.f_body, bg=c.card, fg=c.text,
                           text=T("Press the Windows logo key + K or open the action center and select your "
                                  "adapter. Once connected, the adapter is detected here automatically.")), self.px(70)).pack(anchor="w")
        s = tk.Frame(inner, bg=c.card)
        s.pack(anchor="w", pady=(18, 18))
        Spinner(s, self, self.px(20), bg=c.card).pack(side="left", anchor="n")
        self.wrap(tk.Label(s, text=T("  Searching for connected wireless display adapter …"), font=self.f_body,
                           bg=c.card, fg=c.text2, justify="left"), self.px(110)).pack(side="left")
        b = tk.Frame(inner, bg=c.card)
        b.pack(anchor="w")
        FButton(b, self, T("Connect (Windows + K)"), self.open_connect, accent=True).pack(side="left", padx=(0, 8))
        self.btn_scan = FButton(b, self, T("Advanced search"), self.on_full_scan, icon=IC["search"])
        self.btn_scan.pack(side="left", padx=(0, 16))

        self.section(body, T("How to connect"))
        card = self.card(body)
        for i, (t, d) in enumerate([
                (T("Plug in the adapter"), T("HDMI plug into the display or projector, USB plug into a USB port for power.")),
                (T("Connect to the adapter"), T("Press the Windows logo key + K and select the adapter in the list. The PC's "
                                                "screen appears on the display.")),
                (T("Change settings"), T("This app detects the adapter automatically and shows its settings."))]):
            self.row(card, str(i + 1), t, d, first=(i == 0))

    # Seite: Firmware ---------------------------------------------------------------------
    def _page_firmware(self, body):
        c = self.c
        self.title_label(body, T("Firmware"))
        fw = self.fw
        if self.adapter and not fw["running"]:
            self._stability_bar(body)
        if fw["result"]:
            kind, title, text = fw["result"]
            self.infobar(body, kind, title, text)

        card = self.card(body)
        inner = tk.Frame(card, bg=c.card)
        inner.pack(fill="x", padx=20, pady=18)
        top = tk.Frame(inner, bg=c.card)
        top.pack(fill="x")
        tk.Label(top, text=IC["sync"], font=self.f_icon_big, bg=c.card, fg=c.accent).pack(side="left", padx=(0, 18))
        t = tk.Frame(top, bg=c.card)
        t.pack(side="left", fill="x", expand=True)
        current = self.info.get("version") if self.adapter else None
        latest = self.fw_meta["version"] if self.fw_meta else None
        self.wrap(tk.Label(t, text=T("Firmware version: {version}").format(version=current or "–"),
                           font=self.f_subtitle, bg=c.card, fg=c.text, justify="left"), self.px(160)).pack(anchor="w")
        latest_text = T("Latest firmware version: {version}").format(version=latest or "–")
        if self.fw_meta:
            where = (T("(from {date}, downloaded from Microsoft)") if self._fw_downloaded(self.fw_meta)
                     else T("(from {date}, included in the app)"))
            latest_text += "  " + where.format(date=self.fw_meta["release_date"])
        self.wrap(tk.Label(t, text=latest_text, font=self.f_body, bg=c.card, fg=c.text2, justify="left"),
                  self.px(160)).pack(anchor="w")

        dtype = self.info.get("type")
        status = tk.Frame(inner, bg=c.card)
        status.pack(fill="x", pady=(16, 0))
        if fw["running"]:
            tk.Label(status, text=T("Firmware update running …"), font=self.f_strong, bg=c.card,
                     fg=c.text).pack(anchor="w")
            bar = ttk.Progressbar(status, style="Fluent.Horizontal.TProgressbar", maximum=100, value=fw["pct"])
            bar.pack(fill="x", pady=(8, 6))
            detail = tk.Label(status, text=fw["text"], font=self.f_caption, bg=c.card, fg=c.text2)
            detail.pack(anchor="w")
            self.wrap(tk.Label(status, text=T("Keep this app open and the adapter connected. The update might take a few "
                                              "minutes."), font=self.f_body, bg=c.card,
                               fg=c.text, justify="left"), self.px(60)).pack(anchor="w", pady=(8, 0))
            self.fw_widgets = (bar, detail)
        elif not self.adapter:
            self._status_line(status, "info", T("Connect the adapter (Windows logo key + K) to update it."))
            FButton(status, self, T("Connect (Windows + K)"), self.open_connect, accent=True).pack(anchor="w",
                                                                                                 pady=(12, 0))
        elif dtype not in wda.DEVICE_TYPES:
            self._status_line(status, "warn", T("Unknown adapter type {type} – firmware updates are not "
                                                "supported.").format(type=dtype))
        elif self.fw_dl:
            pct, text = self.fw_dl
            tk.Label(status, text=T("Downloading firmware from Microsoft …"), font=self.f_strong, bg=c.card,
                     fg=c.text).pack(anchor="w")
            bar = ttk.Progressbar(status, style="Fluent.Horizontal.TProgressbar", maximum=100, value=pct)
            bar.pack(fill="x", pady=(8, 6))
            detail = tk.Label(status, text=text, font=self.f_caption, bg=c.card, fg=c.text2)
            detail.pack(anchor="w")
            self.fw_widgets = (bar, detail)
        elif not self.fw_meta:
            self._status_line(status, "info", T("No firmware for this adapter type is stored yet. The app "
                                                "downloads the official firmware from Microsoft once and keeps "
                                                "it for later updates."))
            if self.fw_error:
                self._status_line(status, "err", self.fw_error)
            self.btn_fw = FButton(status, self, T("Download firmware"), self.on_download_fw, accent=True)
            self.btn_fw.pack(anchor="w", pady=(12, 0))
        elif wda.version_tuple(latest) > wda.version_tuple(current):
            self._status_line(status, "info", T("A firmware update is available for your adapter."))
            self.btn_fw = FButton(status, self, T("Update now"), self.on_firmware, accent=True)
            self.btn_fw.pack(anchor="w", pady=(12, 0))
        else:
            self._status_line(status, "ok", T("Your adapter is up to date."))
        if self.adapter and dtype in wda.DEVICE_TYPES and dtype not in TESTED_TYPES and not fw["running"]:
            self._status_line(status, "warn", T("Updates for {generation} adapters have not been tested on a "
                                                "real device. The app follows the same steps as the official "
                                                "app.").format(generation=wda.DEVICE_TYPES[dtype]["generation"]))
        if self.adapter and not fw["running"] and not self.fw_dl and self.fw_list:
            self._firmware_choice(body)
        self._update_buttons()

        self.section(body, T("Notes"))
        card = self.card(body)
        if self.fw_meta and self._fw_downloaded(self.fw_meta):
            self.row(card, IC["info"], T("Firmware downloaded from Microsoft"),
                     T("Official Microsoft firmware for the {generation} adapter, stored in {path}. The checksum "
                       "is verified before transferring.").format(
                         generation=wda.DEVICE_TYPES[self.fw_type]["generation"],
                         path=Path(self.fw_meta["_path"]).parent), first=True)
        else:
            self.row(card, IC["info"], T("Firmware is included in the app"),
                     T("Official Microsoft firmware for Wireless Display Adapter Gen 1 and Gen 1.5. No internet "
                       "connection is needed for the update. Firmware for Gen 3 (128 MB) is downloaded from "
                       "Microsoft when needed. The checksum is verified before transferring."), first=True)
        self.row(card, IC["warn"], T("During the update"),
                 T("Don't unplug the adapter from power or the display and don't close this app. "
                   "Afterwards the adapter restarts – then connect again with the Windows logo key "
                   "+ K."))

    def _load_fw_library(self, dtype):
        """Offizielle Firmware-Stände für den Adaptertyp laden (neueste zuerst)."""
        self.fw_type = dtype
        self.fw_list = wda.list_local_firmware(dtype) if dtype in wda.DEVICE_TYPES else []
        self.fw_meta = self.fw_list[0] if self.fw_list else None
        self.fw_error = None
        self.fw_sel = 0                 # Auswahl im Dropdown; len(fw_list) = eigene Datei
        self.custom_fw = None           # {"path", "data", "info", "signature"} der eigenen Datei

    @staticmethod
    def _fw_downloaded(meta):
        """Liegt die Firmware im Download-Cache (statt in der EXE bzw. im Projektordner)?"""
        return getattr(sys, "frozen", False) and Path(meta["_path"]).is_relative_to(wda.FIRMWARE_CACHE)

    def on_download_fw(self):
        if self.busy:
            return
        dtype = self.fw_type
        self.fw_dl = (0, T("Connecting …"))
        self.fw_error = None
        self.render()

        def progress(done, total):
            self.post(self._fw_dl_progress, done * 100 // total,
                      T("{done} of {total} MB").format(done=done // 1_000_000, total=total // 1_000_000))

        def work():
            try:
                return wda.fetch_official_firmware(dtype, progress=progress)
            except OSError as e:        # Internetfehler – kein Funkloch zum Adapter
                raise wda.AdapterError(T("Download failed: {error}").format(error=e)) from e

        def done(meta):
            self.fw_dl = None
            self.log(T("Firmware {version} for {generation} downloaded (SHA-256 {sha})").format(
                version=meta["version"], generation=wda.DEVICE_TYPES[dtype]["generation"], sha=meta["sha256"]))
            self._load_fw_library(dtype)
            self.render()

        self.run_bg(T("Downloading firmware from Microsoft …"), work, done)
        self.after(500, self._fw_dl_watch)

    def _fw_dl_progress(self, pct, text):
        if self.fw_dl is None:
            return
        self.fw_dl = (pct, text)
        if self.fw_widgets and self.fw_widgets[0].winfo_exists():
            self.fw_widgets[0].configure(value=pct)
            self.fw_widgets[1].configure(text=text)

    def _fw_dl_watch(self):
        """Download fehlgeschlagen (kein Internet o. Ä.): Fehler auf der Seite zeigen."""
        if self.fw_dl and not self.busy:
            self.fw_dl = None
            self.fw_error = T("The download failed. Check the internet connection and try again.")
            self.render()
        elif self.fw_dl:
            self.after(500, self._fw_dl_watch)

    def _firmware_choice(self, body):
        """Version aus der Bibliothek wählen oder eigene Datei (hohes Risiko)."""
        c = self.c
        self.section(body, T("Install a specific firmware"))
        card = self.card(body)
        ctl = self.row(card, IC["sync"], T("Firmware version"),
                       T("Official versions from the \"firmware\" folder or your own file."), first=True)
        names = [T("{version}  –  official Microsoft ({date})").format(version=m["version"],
                                                                       date=m.get("release_date", "?"))
                 for m in self.fw_list]
        names.append(T("Custom firmware file …  (high risk)"))
        self.fw_box = ttk.Combobox(ctl, values=names, state="readonly", width=34, font=self.f_body)
        self.fw_box.current(min(self.fw_sel, len(names) - 1))
        self.fw_box.bind("<<ComboboxSelected>>", lambda e: (setattr(self, "fw_sel", self.fw_box.current()),
                                                           self.render()))
        self.fw_box.pack(side="left")

        custom = self.fw_sel >= len(self.fw_list)
        if custom:
            inner = tk.Frame(card, bg=c.card)
            tk.Frame(card, bg=c.divider, height=1).pack(fill="x")
            inner.pack(fill="x", padx=16, pady=14)
            self.infobar(inner, "err", T("High risk"),
                         T("Third-party or modified firmware can permanently break (\"brick\") the adapter. "
                           "The adapter may not verify the file. There is no way back – not even with the "
                           "reset button. Only use this if you know exactly what the file is."),
                         inset=34)
            b = tk.Frame(inner, bg=c.card)
            b.pack(anchor="w")
            FButton(b, self, T("Choose file …"), self.on_pick_custom_fw).pack(side="left")
            cf = self.custom_fw
            if cf:
                i = cf["info"]
                sha = " ".join(i["sha256"][k:k + 16] for k in range(0, 64, 16))   # umbrechbar
                lines = [f"{Path(cf['path']).name}  ·  {i['size'] / 1048576:.1f} MB",
                         f"SHA-256: {sha}",
                         T("Detected version: {version}").format(version=i["version"] or T("unknown")) +
                         (T("  (identical to official file)") if i.get("official") else "")]
                if cf.get("signature"):
                    lines.append(T("Signature: {file}").format(file=Path(cf["signature"]).name))
                for line in lines:
                    self.wrap(tk.Label(inner, text=line, font=self.f_caption, bg=c.card, fg=c.text2,
                                       justify="left"), self.px(50)).pack(anchor="w")
                for w in i["warnings"]:
                    self._status_line(inner, "warn", w)
        bar = tk.Frame(body, bg=c.bg)
        bar.pack(anchor="w", pady=(10, 0))
        self.btn_fw_sel = FButton(bar, self, T("Install selected firmware"), self.on_install_selected,
                                  accent=not custom)
        self.btn_fw_sel.pack(side="left")

    def on_pick_custom_fw(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self, title=T("Choose custom firmware file"),
                                          filetypes=[(T("Firmware"), "*.sbin *.zip *.bin *.img"), (T("All files"), "*.*")])
        if not path:
            return
        try:
            data, info = wda.inspect_custom_firmware(path, self.fw_type)
        except OSError as e:
            self.dialog(T("File can't be read"), str(e), "OK")
            return
        sig_path = None
        if wda.DEVICE_TYPES[self.fw_type]["signature_url"] and not info["official"]:
            # Gen 3 nimmt Firmware nur zusammen mit der passenden Signatur von Microsoft an
            sig_path = filedialog.askopenfilename(parent=self, title=T("Choose the matching signature file"),
                                                  filetypes=[(T("Signature"), "*.sign"), (T("All files"), "*.*")])
            if not sig_path:
                return
        self.custom_fw = {"path": path, "data": data, "info": info, "signature": sig_path}
        self.log(T("Custom firmware selected: {path} ({size} bytes, SHA-256 {sha})").format(
            path=path, size=info["size"], sha=info["sha256"]))
        self.render()

    def on_install_selected(self):
        if self.fw_sel < len(self.fw_list):
            self.on_firmware(meta=self.fw_list[self.fw_sel])
            return
        cf = self.custom_fw
        if not cf:
            self.dialog(T("No file"), T("Please choose a firmware file first."), "OK")
            return
        i = cf["info"]
        warn = "\n".join(f"• {T(w)}" for w in i["warnings"]) or T("• no issues detected")
        word = T("RISK")
        text = (Path(cf["path"]).name + "\n" +
                T("Detected version: {version}").format(version=i["version"] or T("unknown")) + "\n\n" +
                T("Check:") + "\n" + warn + "\n\n" +
                T("This can make the adapter permanently unusable. Type {word} to confirm:").format(word=word))
        vals = self.dialog(T("Install custom firmware – HIGH RISK"), text, T("Install"), T("Cancel"),
                           fields=[(T("Confirmation"), False)])
        if not vals or vals[0].strip().upper() != word.upper():
            if vals is not None:
                self.dialog(T("Cancelled"), T("The confirmation was not correct – nothing was installed."), "OK")
            return
        try:
            if i["official"]:
                files = wda.firmware_parts(i["meta"], cf["data"])
            else:
                cfg = wda.DEVICE_TYPES[self.fw_type]
                files = [("NewImage", cfg["firmware_name"], cf["data"])]
                if cf.get("signature"):
                    files.append(("signature", cfg["signature_name"], Path(cf["signature"]).read_bytes()))
        except (OSError, wda.AdapterError) as e:
            self.dialog(T("File can't be read"), str(e), "OK")
            return
        self._start_firmware(files, i["version"] or T("custom file"), confirm=False)

    def _status_line(self, parent, kind, text):
        c = self.c
        fg = {"info": c.accent, "warn": c.warn, "err": c.err, "ok": c.ok}[kind]
        icon = {"info": IC["info"], "warn": IC["warn"], "err": IC["err"], "ok": IC["ok"]}[kind]
        f = tk.Frame(parent, bg=c.card)
        f.pack(anchor="w")
        tk.Label(f, text=icon, font=self.f_icon, bg=c.card, fg=fg).pack(side="left", padx=(0, 8), anchor="n")
        self.wrap(tk.Label(f, text=text, font=self.f_body, bg=c.card, fg=c.text, justify="left"),
                  self.px(100)).pack(side="left")

    # Seite: Info ----------------------------------------------------------------------------
    def _page_about(self, body):
        c = self.c
        self.title_label(body, T("About"))
        card = self.card(body)
        inner = tk.Frame(card, bg=c.card)
        inner.pack(fill="x", padx=20, pady=18)
        tk.Label(inner, text=f"{APP_NAME} {APP_VERSION}", font=self.f_subtitle, bg=c.card, fg=c.text).pack(anchor="w")
        lines = [
            T("Unofficial configuration tool for the Microsoft Wireless Display Adapter (Gen "
              "1.5). Not made by Microsoft."),
            T("Built from an analysis of the \"Surface Wireless Display Adapter\" app "
              "4.232.137.0."),
        ]
        if self.fw_meta:
            lines.append(T("Included firmware: {version}  ·  SHA-256 {sha}…").format(
                version=self.fw_meta["version"], sha=self.fw_meta["sha256"][:16]))
        for line in lines:
            self.wrap(tk.Label(inner, text=line, font=self.f_body, bg=c.card, fg=c.text2, justify="left"),
                      self.px(60)).pack(anchor="w", pady=(4, 0))

        self.section(body, T("App language"))
        card = self.card(body)
        ctl = self.row(card, IC["lang"], T("App language"),
                       T("Language of this app. Available in every language the adapter supports."), first=True)
        codes = list(i18n.LANGUAGES)
        self.app_lang_box = ttk.Combobox(ctl, values=list(i18n.LANGUAGES.values()), state="readonly", width=24,
                                         font=self.f_body)
        self.app_lang_box.current(codes.index(i18n.current()))
        self.app_lang_box.bind("<<ComboboxSelected>>",
                               lambda e: self.set_app_language(codes[self.app_lang_box.current()]))
        self.app_lang_box.pack(side="left")

        self.section(body, T("Log"))
        card = self.card(body)
        box = tk.Text(card, height=14, font=self.f_mono, bg=c.input, fg=c.text, relief="flat", wrap="word",
                      insertbackground=c.text, highlightthickness=0, padx=10, pady=8)
        box.insert("1.0", "\n".join(self.log_lines) or T("(no entries yet)"))
        box.configure(state="disabled")
        box.pack(fill="x", padx=1, pady=1)
        b = tk.Frame(body, bg=c.bg)
        b.pack(anchor="w", pady=(10, 0))
        FButton(b, self, T("Copy log"), self.copy_log, icon=IC["copy"]).pack(side="left")

    def set_app_language(self, code):
        """Sprache wechseln: speichern und Navigation + Seite in der neuen Sprache neu aufbauen."""
        if code == i18n.current():
            return
        i18n.set_language(code)
        i18n.save_language(code)
        self._fonts()                    # passende Schrift für die neue Sprache
        self._styles()
        self.nav.destroy()
        self.content.destroy()
        self.unbind("<Configure>")
        self._build_shell()
        if self.compact:
            self._set_compact(True)
        self.show_page(self.page)

    # Zustand, Hintergrundarbeit -------------------------------------------------------------
    def log(self, text):
        import datetime
        self.log_lines.append(f"{datetime.datetime.now():%H:%M:%S}  {text}")

    def copy_log(self):
        self.clipboard_clear()
        self.clipboard_append("\n".join(self.log_lines))

    def _update_buttons(self):
        on = self.adapter is not None and not self.busy
        for name in ("btn_rename", "btn_lang", "btn_reboot", "btn_fw", "btn_fw_sel", "btn_reset", "btn_wp",
                     "btn_pw", "tg_pin", "tg_pw"):
            b = getattr(self, name, None)
            if b is not None and b.winfo_exists():
                b.set_enabled(on)

    def run_bg(self, label, work, done=None, write=True):
        """work() im Hintergrund; done(ergebnis) danach im GUI-Thread."""
        if write:
            if self.busy:
                return
            self.busy = True
            self._update_buttons()
        if label:
            self.log(label)

        def target():
            try:
                self.events.put(("done", (done, write), work()))
            except Exception as e:
                self.events.put(("error", (label, write), e))

        threading.Thread(target=target, daemon=True).start()

    def post(self, fn, *args):
        self.events.put(("call", fn, args))

    def _drain_events(self):
        try:
            while True:
                kind, a, b = self.events.get_nowait()
                if kind == "call":
                    a(*b)
                    continue
                cb_or_label, write = a
                if write:
                    self.busy = False
                else:
                    self.checking = False
                if kind == "done":
                    if cb_or_label:
                        cb_or_label(b)
                elif write:
                    if isinstance(b, (OSError, wda.ConnectionLost)):   # Zeitüberschreitung/Abbruch = Funkloch
                        self._glitch()
                    self.log(T("ERROR: {error}").format(error=b))
                    self.dialog(T("That didn't work"), f"{cb_or_label}\n\n{b}", "OK")
                self._update_buttons()
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _tick(self):
        """Wie die Original-App: Adapter automatisch erkennen und Verbindung überwachen."""
        if not self.busy and not self.checking:
            self.checking = True
            if self.adapter is None:
                self.run_bg(None, self._find_adapter, self._on_found, write=False)
            else:
                self.run_bg(None, self._ping, self._on_ping, write=False)
        self.after(3000, self._tick)

    def _find_adapter(self):
        candidates = wda.arp_candidates()
        if self.last_ip and self.last_ip not in candidates:
            candidates.insert(0, self.last_ip)
        for ip in candidates:
            if wda.probe(ip, use_https=False):
                return self._load(wda.Adapter(ip, use_https=False))
        return None

    def _load(self, a):
        version, dtype = a.retrieve_version()
        codes, cur = a.get_language_info()
        info = {"name": a.get_device_name(), "version": version, "type": dtype, "languages": codes, "lang": cur}
        try:
            info["overscan"] = a.get_overscan()
        except wda.AdapterError:
            info["overscan"] = None
        try:
            info["protected"] = str(a.get_password_protect()).lower() == "true"
        except wda.AdapterError:
            info["protected"] = False
        try:
            info["pbc"] = a.get_pbc_mode()
        except wda.AdapterError:
            info["pbc"] = None
        try:
            info["wallpaper"] = a.get_wallpaper_id()
        except wda.AdapterError:
            info["wallpaper"] = None
        return a, info

    def _on_found(self, res):
        if not res or self.adapter is not None:
            return
        self.adapter, self.info = res
        self.last_ip = self.adapter.host
        self.connected_at = time.time()
        self.ping_failures = 0
        if self.info["type"] != self.fw_type and not self.fw_dl:
            self._load_fw_library(self.info["type"])
        self.password = None
        if self.fw["result"] and not self.fw["running"]:
            self.fw["result"] = None
        self.log(T("Connected: {name} ({type}, firmware {version}) at {host}").format(
            name=self.info["name"], type=self.info["type"], version=self.info["version"], host=self.adapter.host))
        self.render()

    def _ping(self):
        """Adapter erreichbar? Bei Miracast zusätzlich: steht er noch in der ARP-Tabelle (Wi-Fi Direct)?"""
        host = self.adapter.host
        try:
            self.adapter.get_device_name()
        except Exception:
            return False
        if host.startswith("192.168.") and ":" not in host:
            return host in wda.arp_candidates()
        return True

    # Stabilität der Miracast-Verbindung ------------------------------------------------
    STABLE_AFTER = 20      # s nach dem Verbinden (alte Firmware bricht bei HDCP-Problemen nach ~13 s ab)
    GLITCH_WINDOW = 60     # s, in denen eine Unterbrechung als „instabil“ zählt

    def _glitch(self):
        now = time.time()
        if not self.unstable_for():
            self.log(T("Connection to {host} interrupted").format(host=self.last_ip))
        self.glitches = [g for g in self.glitches if now - g < self.GLITCH_WINDOW] + [now]

    def unstable_for(self):
        """Sekunden seit der letzten Unterbrechung, wenn die Verbindung gerade instabil ist, sonst None."""
        now = time.time()
        recent = [g for g in self.glitches if now - g < self.GLITCH_WINDOW]
        return int(now - recent[-1]) if recent else None

    def link_is_stable(self):
        return self.unstable_for() is None and time.time() - self.connected_at >= self.STABLE_AFTER

    def confirm_stable_link(self):
        """Vor Update/Zurücksetzen: bei wackeliger Verbindung warnen (Abbruch mittendrin wäre sinnlos)."""
        if self.link_is_stable():
            return True
        since = self.unstable_for()
        if since is None:
            text = T("The adapter has only been connected for {seconds} s. Wait until the connection has been "
                     "stable for at least {needed} s.").format(seconds=int(time.time() - self.connected_at),
                                                                needed=self.STABLE_AFTER)
        else:
            text = self._unstable_text(since)
        return self.dialog(T("Connection unstable"), text, T("Try anyway"), T("Cancel"))

    def _unstable_text(self, since):
        return T("The Miracast connection to this adapter keeps dropping (last interruption {seconds} s ago). "
                 "Updates and resets need a stable connection. With firmware 2.0.8350 this is usually caused by "
                 "HDCP on this PC – update the adapter from another PC or turn off HDCP support in the graphics "
                 "driver.").format(seconds=since)

    def _stability_bar(self, body):
        since = self.unstable_for()
        self._shown_unstable = since is not None
        if since is not None:
            self.infobar(body, "warn", T("Connection unstable"), self._unstable_text(since))

    def _on_ping(self, ok):
        if self.adapter is None or self.busy:
            return
        if not ok:
            self._glitch()
        self.ping_failures = 0 if ok else self.ping_failures + 1
        if self.ping_failures >= 2:
            self.log(T("Connection to {host} lost").format(host=self.adapter.host))
            self.adapter = None
            self.info = {}
            self.need_reboot = False
            self.render()
        elif (self.unstable_for() is not None) != self._shown_unstable:
            self.render()            # Hinweis „instabil“ ein- bzw. ausblenden

    def reload_info(self):
        a = self.adapter
        self.run_bg(T("Reloading adapter data …"), lambda: self._load(a), self._on_reload)

    def _on_reload(self, res):
        self.adapter, self.info = res
        self.render()

    # Aktionen ----------------------------------------------------------------------------------
    def open_connect(self):
        try:
            os.startfile(CONNECT_URI)
        except OSError:
            self.dialog(T("Connect"), T("Please press the Windows logo key + K and select the adapter."), "OK")

    def on_full_scan(self):
        subnets = [ip.rsplit(".", 1)[0] + ".0/24" for ip in wda.local_wifi_direct_ips()]
        if not subnets:
            self.dialog(T("No connection found"),
                        T("There is no Miracast connection. Please connect to the adapter with the Windows "
                          "logo key + K first."), "OK")
            return

        def done(found):
            if not found:
                self.dialog(T("No adapter found"), T("No adapter was found in {networks}.").format(
                    networks=", ".join(subnets)), "OK")
                return
            self.last_ip = next(iter(found))
            self.log(T("Found: {found}").format(found=found))

        self.btn_scan.set_enabled(False)
        self.run_bg(T("Advanced search in {networks} …").format(networks=", ".join(subnets)),
                    lambda: wda.discover(subnets, 0, use_https=False), done)

    def ensure_password(self):
        """Fragt bei aktivem Kennwortschutz einmal nach dem Kennwort und prüft es."""
        if not self.info.get("protected") or self.password:
            self.adapter.password = self.password
            return True
        vals = self.dialog(T("Enter password"), T("Enter your password to change adapter settings."),
                           "OK", T("Cancel"), fields=[(T("Password"), True)])
        if not vals or not vals[0]:
            return False
        pw = vals[0]
        try:
            ok = self.adapter.verify_password(pw)
        except Exception as e:
            self.dialog(T("Error"), str(e), "OK")
            return False
        if not ok:
            self.dialog(T("Incorrect password"), T("Incorrect password. Please try again."), "OK")
            return False
        self.password = self.adapter.password = pw
        return True

    def _after_write(self, resp, what):
        self.log(T("{what}: OK").format(what=what))
        if resp.get("NeedRebootEffective"):
            self.need_reboot = True
        a = self.adapter
        self.run_bg(None, lambda: self._load(a), self._on_reload)

    def on_rename(self):
        name = self.name_entry.get().strip()
        if not wda.valid_device_name(name):
            self.dialog(T("Invalid name"), T("The name must be 1 to 32 characters long and may only contain these characters: "
                                             "a–z, A–Z, 0–9, + - _ ( ) { } [ ]"), "OK")
            return
        if name == self.info["name"]:
            return
        if not self.dialog(T("Rename adapter?"), f"\"{self.info['name']}\"  →  \"{name}\"", T("Rename"), T("Cancel")):
            return
        if not self.ensure_password():
            return
        self.run_bg(T("Setting adapter name to {name} …").format(name=name),
                    lambda: self.adapter.set_device_name(name),
                    lambda r: self._after_write(r, T("Adapter name \"{name}\"").format(name=name)))

    def on_language(self):
        i = self.lang_box.current()
        if i < 0:
            return
        code = self.lang_codes[i]
        if code.lower() == self.info["lang"].lower():
            return
        label = wda.LANGUAGES.get(code.lower(), code)
        if not self.dialog(T("Change language?"),
                           T("Switch the adapter's display language to {language} ({code})?").format(
                               language=label, code=code),
                           T("Change"), T("Cancel")):
            return
        if not self.ensure_password():
            return
        self.run_bg(T("Setting language to {code} …").format(code=code), lambda: self.adapter.set_language(code),
                    lambda r: self._after_write(r, T("Language {code}").format(code=code)))

    def on_pin(self, enable):
        mode = "Disabled" if enable else "Auto"
        text = (T("From now on, the adapter shows a PIN when a new device connects, which must be "
                  "entered on the PC.") if enable else T("From now on, devices can connect to the adapter without a PIN."))
        if not self.dialog(T("Turn on PIN when connecting?") if enable else T("Turn off PIN when connecting?"), text,
                           T("Apply"), T("Cancel")):
            return
        if not self.ensure_password():
            return
        self.run_bg(T("Setting connection mode to {mode} …").format(mode=mode), lambda: self.adapter.set_pbc_mode(mode),
                    lambda r: self._after_write(r, T("PIN when connecting on") if enable
                                                else T("PIN when connecting off")))

    def on_password_toggle(self, enable):
        if enable:
            vals = self.dialog(T("Create a password for this adapter"),
                               T("Choose a password you don't use for email or other accounts. 6–64 characters: "
                                 "a–z, A–Z, 0–9, + - _ ( ) { } [ ]"),
                               T("Create"), T("Cancel"), fields=[(T("Password"), True), (T("Confirm password"), True)])
            if not vals:
                return
            pw, pw2 = vals
            if not wda.PASSWORD_RE.match(pw):
                self.dialog(T("Invalid password"), T("6–64 characters, only a–z, A–Z, 0–9, + - _ ( ) { } [ ]"), "OK")
                return
            if pw != pw2:
                self.dialog(T("Passwords don't match"), T("Please confirm the new password."), "OK")
                return

            def done(r):
                self.password = pw
                self._after_write(r, T("Password protection on"))

            self.run_bg(T("Turning on password protection …"), lambda: self.adapter.set_password_protect(True, pw), done)
        else:
            vals = self.dialog(T("Turn off password protection"),
                               T("Enter your password to turn off password protection."),
                               T("Turn off"), T("Cancel"), fields=[(T("Password"), True)])
            if not vals or not vals[0]:
                return
            pw = vals[0]

            def done(r):
                self.password = None
                self.adapter.password = None
                self._after_write(r, T("Password protection off"))

            self.run_bg(T("Turning off password protection …"), lambda: self.adapter.set_password_protect(False, pw), done)

    def on_change_password(self):
        vals = self.dialog(T("Change password"), T("6–64 characters: a–z, A–Z, 0–9, + - _ ( ) { } [ ]"), T("Change"),
                           T("Cancel"), fields=[(T("Old password"), True), (T("New password"), True),
                                                (T("Confirm new password"), True)])
        if not vals:
            return
        old, new, new2 = vals
        if not wda.PASSWORD_RE.match(new):
            self.dialog(T("Invalid password"), T("6–64 characters, only a–z, A–Z, 0–9, + - _ ( ) { } [ ]"), "OK")
            return
        if new != new2:
            self.dialog(T("Passwords don't match"), T("Please confirm the new password."), "OK")
            return

        def done(r):
            self.password = self.adapter.password = new
            self._after_write(r, T("Password changed"))

        self.run_bg(T("Changing password …"), lambda: self.adapter.change_password(old, new), done)

    def on_reset(self):
        if not self.confirm_stable_link():
            return
        if not self.dialog(T("Reset adapter now?"),
                           T("This will clear all your custom settings and your adapter will restart."),
                           T("Reset"), T("Cancel")):
            return
        if not self.ensure_password():
            return
        self.run_bg(T("Resetting adapter to default settings …"), self.adapter.reset_to_factory,
                    self._on_rebooted)

    def on_wallpaper(self, wid):
        if self.busy or self.adapter is None or wid == self.info.get("wallpaper"):
            return
        if not self.dialog(T("Change wallpaper?"), T("Show built-in image {n} on the adapter?").format(n=wid),
                           T("Apply"), T("Cancel")):
            return
        if not self.ensure_password():
            return
        self.run_bg(T("Setting wallpaper {n} …").format(n=wid), lambda: self.adapter.set_predefined_wallpaper(wid),
                    lambda r: self._after_write(r, T("Wallpaper {n}").format(n=wid)))

    def on_custom_wallpaper(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self, title=T("Choose an image for the adapter"),
                                          filetypes=[(T("Images"), "*.png *.jpg *.jpeg *.bmp"), (T("All files"), "*.*")])
        if not path:
            return
        if not self.dialog(T("Upload custom wallpaper?"),
                           Path(path).name + "\n\n" +
                           T("The image is cropped to 1920 × 1080 and darkened for display."),
                           T("Upload"), T("Cancel")):
            return
        if not self.ensure_password():
            return
        a = self.adapter

        def work():
            tint, blur = wda.make_wallpaper_images(path)
            return a.upload_wallpaper(tint, blur)

        self.run_bg(T("Uploading wallpaper {file} …").format(file=Path(path).name), work,
                    lambda r: self._after_write(r, T("Custom wallpaper")))

    def on_reboot(self):
        if not self.dialog(T("Restart adapter?"),
                           T("The connection will be closed. Then connect again with the Windows logo key + K."),
                           T("Restart"), T("Cancel")):
            return
        self.run_bg(T("Restarting adapter …"), self.adapter.reboot, self._on_rebooted)

    def _on_rebooted(self, _):
        self.log(T("Restart triggered"))
        self.need_reboot = False
        self.adapter = None
        self.info = {}
        self.render()

    def on_firmware(self, meta=None):
        meta = meta or self.fw_meta
        try:
            files = wda.firmware_parts(meta)
        except Exception as e:
            self.dialog(T("Firmware file damaged"), str(e), "OK")
            return
        self._start_firmware(files, meta["version"])

    def _start_firmware(self, files, target, confirm=True):
        """files: Upload-Teile aus wda.firmware_parts (Image, bei Gen 3 plus Signatur)."""
        current = self.info["version"]
        if not self.confirm_stable_link():
            return
        if confirm:
            older = wda.version_tuple(target) < wda.version_tuple(current)
            same = wda.version_tuple(target) == wda.version_tuple(current)
            text = (f"Firmware {current}  →  {target}\n\n" +
                    T("Keep this app open and the adapter connected. Don't unplug the adapter from power. "
                      "The update might take a few minutes."))
            if same:
                text = T("The adapter already has firmware {version}. Install it again anyway?").format(
                    version=current) + "\n\n" + text
            elif older:
                text = T("WARNING: {target} is OLDER than the installed {current} (downgrade). The adapter may "
                         "reject it, and older versions have known bugs.").format(target=target,
                                                                                current=current) + "\n\n" + text
            if not self.dialog(T("Update your adapter now?"), text, T("Update now"), T("Cancel")):
                return
        if not self.ensure_password():
            return
        a = self.adapter
        self.fw.update(running=True, pct=0, text=T("Preparing update …"), result=None)
        self.render()

        def status(phase, pct, text):
            self.post(self._fw_progress, pct, text)

        def work():
            import time
            for _ in range(100):            # laufende Hintergrundabfrage erst fertig werden lassen
                if not self.checking:
                    break
                time.sleep(0.1)
            return wda.run_firmware_update(a, files, status, log=lambda m: self.post(self.log, m))

        self.run_bg(T("Updating firmware to {version} …").format(version=target), work, self._fw_done)
        self.after(200, self._fw_watch)

    def _fw_progress(self, pct, text):
        self.fw.update(pct=pct, text=text)
        if self.fw_widgets and self.fw_widgets[0].winfo_exists():
            self.fw_widgets[0].configure(value=pct)
            self.fw_widgets[1].configure(text=text)

    def _fw_watch(self):
        """Fehler im Update auf der Firmware-Seite anzeigen statt nur im Dialog."""
        if self.fw["running"] and not self.busy:
            self.fw.update(running=False, result=("err", T("Update failed"),
                                                  T("We couldn't update your adapter. Make sure your adapter stays connected during "
                                                    "the update and try again. Details are under About › Log.")))
            self.render()
        elif self.fw["running"]:
            self.after(500, self._fw_watch)

    def _fw_done(self, _):
        self.log(T("Firmware transferred, adapter is restarting"))
        self.fw.update(running=False, pct=100, result=(
            "ok", T("Update successful"),
            T("We're restarting your adapter. This may take up to a minute. Then connect again "
              "with the Windows logo key + K – the new version will be shown here.")))
        self.adapter = None
        self.info = {}
        self.render()

    # Dialog im Stil eines ContentDialog -------------------------------------------------------
    def dialog(self, title, text, primary, secondary=None, fields=None):
        """Dialog im Stil eines ContentDialog. Ohne fields: True/False, mit fields: Liste der Eingaben."""
        c = self.c
        top = tk.Toplevel(self)
        top.title(APP_NAME)
        top.configure(bg=c.card)
        top.resizable(False, False)
        top.transient(self)
        result = {"v": None if fields else False}
        body = tk.Frame(top, bg=c.card)
        body.pack(fill="both", padx=24, pady=(22, 18))
        tk.Label(body, text=title, font=self.f_subtitle, bg=c.card, fg=c.text).pack(anchor="w")
        tk.Label(body, text=text, font=self.f_body, bg=c.card, fg=c.text, wraplength=self.px(440),
                 justify="left").pack(anchor="w", pady=(10, 0))
        entries = []
        for label, secret in fields or []:
            tk.Label(body, text=label, font=self.f_caption, bg=c.card, fg=c.text2).pack(anchor="w", pady=(12, 2))
            e = self.entry(body, 40, show="•" if secret else None)
            e.pack(anchor="w", fill="x", ipady=4)
            entries.append(e)
        if entries:
            entries[0].focus_set()
        foot = tk.Frame(top, bg=c.bg)
        foot.pack(fill="x")

        def ok():
            result["v"] = [e.get() for e in entries] if fields else True
            top.destroy()

        btns = tk.Frame(foot, bg=c.bg)
        btns.pack(side="right", padx=24, pady=16)
        FButton(btns, self, primary, ok, accent=True).pack(side="left")
        if secondary:
            FButton(btns, self, secondary, top.destroy).pack(side="left", padx=(8, 0))
        top.bind("<Return>", lambda ev: ok())
        top.bind("<Escape>", lambda ev: top.destroy())
        top.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - top.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - top.winfo_height()) // 3
        top.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        top.grab_set()
        self.wait_window(top)
        return result["v"]


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # scharfe Schrift unter Windows
    except Exception:
        pass
    i18n.set_language(i18n.load_saved_language())    # Standard: Englisch
    App().mainloop()


if __name__ == "__main__":
    main()
