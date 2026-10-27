#!/usr/bin/env python3
"""Screenshots der App aufnehmen – ohne Adapter, gegen tools/mock_adapter.py.

    python tools/screenshots.py [--out docs/screenshots] [--scale 1.25]

Startet den Mock-Adapter, lenkt die Adaptersuche der GUI darauf um und fotografiert
jede Seite. Aufgenommen wird nur der Fensterinhalt (ohne Titelleiste und Rahmen).

Die Vorschaubilder der vorinstallierten Hintergrundbilder bleiben dabei absichtlich leer:
sie gehoeren Microsoft und sollen nicht in den Screenshots im Repository landen.

Braucht Pillow (python -m pip install pillow).
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab                                        # noqa: E402

import i18n                                                      # noqa: E402
import wda_tool as wda                                           # noqa: E402
import wda_gui                                                   # noqa: E402
from tools import mock_adapter                                   # noqa: E402

PORT = 8111
WINDOW = (1600, 1000)           # Fenstergroesse in Bildpunkten; passt auf 1920x1080
SETTLE = 0.45                   # Zeit zum Fertigzeichnen vor der Aufnahme


def start_mock(**kwargs):
    adapter = mock_adapter.MockAdapter(verbose=False, **kwargs)
    server, _ = mock_adapter.serve(adapter, port=PORT, background=True)
    return adapter, server


def make_app(theme="light", language="en-US", scale=1.25, find_adapter=True, size=WINDOW):
    """App bauen, auf den Mock zeigen lassen und darauf warten, dass sie verbunden ist."""
    wda_gui.system_theme = lambda: theme
    wda.arp_candidates = (lambda: [f"127.0.0.1:{PORT}"]) if find_adapter else (lambda: [])
    wda_gui.App._wallpaper_thumb = lambda self, wid: None        # keine Microsoft-Bilder
    i18n.set_language(language)

    app = wda_gui.App()
    app.tk.call("tk", "scaling", 96.0 * scale / 72.0)            # schaerfere Aufnahme
    app.s = scale
    app._fonts()
    app._styles()
    app.nav.destroy()
    app.content.destroy()
    app.unbind("<Configure>")
    app._build_shell()
    icon = ROOT / "build" / "wda.ico"                            # Fenstersymbol auch beim Start aus dem Quelltext
    if icon.exists():
        app.iconbitmap(default=str(icon))
    app.geometry(f"{size[0]}x{size[1]}+40+10")
    app.show_page("adapter")
    app.attributes("-topmost", True)
    app.update()

    deadline = time.time() + 20
    while find_adapter and app.adapter is None and time.time() < deadline:
        app.update()
        time.sleep(0.05)
    if find_adapter and app.adapter is None:
        raise SystemExit("mock adapter was not detected – is port 8111 free?")
    return app


def grab(app, out, name, settle=SETTLE):
    """Nur den Fensterinhalt aufnehmen (winfo_rootx/y beginnt unter der Titelleiste)."""
    app.lift()
    app.update_idletasks()
    app.update()
    time.sleep(settle)
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    box = (x, y, x + app.winfo_width(), y + app.winfo_height())
    img = ImageGrab.grab(bbox=box, all_screens=True)
    path = out / f"{name}.png"
    img.save(path, optimize=True)
    print(f"  {path.relative_to(ROOT)}  {img.width}x{img.height}")
    return path


def resize(app, height, width=WINDOW[0]):
    """Fensterhoehe an die Seite anpassen, damit kein grosser leerer Bereich entsteht."""
    app.geometry(f"{width}x{height}+40+10")
    app.update_idletasks()
    app.update()
    time.sleep(0.15)


def scroll(app, fraction):
    """Im Inhaltsbereich scrollen (die ScrollArea wird bei jedem render() neu angelegt)."""
    area = app.content.winfo_children()[0]
    app.update_idletasks()
    area.canvas.yview_moveto(fraction)
    app.update()


def shot_pages(out, scale):
    """Verbundener Gen-1.5-Adapter mit verfuegbarem Update: alle drei Seiten, hell."""
    adapter, server = start_mock(device_type="Gen-1.5", version="2.0.8385", name="Living-Room-TV")
    try:
        app = make_app(scale=scale)
        grab(app, out, "adapter")
        scroll(app, 0.42)
        grab(app, out, "adapter-wallpaper")

        resize(app, 720)
        app.show_page("firmware")
        grab(app, out, "firmware")

        resize(app, 900)
        app.fw_sel = len(app.fw_list)                 # "Custom firmware file …"
        app.render()
        scroll(app, 1.0)
        grab(app, out, "firmware-custom")

        resize(app, 720)
        app.fw_sel = 0
        app.fw = {"running": True, "pct": 68, "result": None,
                  "text": "Transferring firmware: 17/24 MB"}
        app.render()
        grab(app, out, "firmware-update")

        resize(app, 940)
        app.fw = {"running": False, "pct": 0, "text": "", "result": None}
        app.log("Connected: Living-Room-TV (Gen-1.5, firmware 2.0.8385) at 192.168.137.247")
        app.log("Display language 'en-US' -> 'de-DE' – OK")
        app.log("Wallpaper set to image 2 – OK")
        app.show_page("about")
        grab(app, out, "about")
        app.destroy()
    finally:
        server.shutdown()
        server.server_close()


def shot_dark(out, scale):
    """Dunkles Design mit eingeschaltetem Passwortschutz."""
    adapter, server = start_mock(device_type="Gen-1.5", version="2.0.8442",
                                 name="Conference-Room", password="Secret-42")
    try:
        app = make_app(theme="dark", scale=scale)
        grab(app, out, "adapter-dark")
        resize(app, 640)
        app.show_page("firmware")
        grab(app, out, "firmware-dark")
        app.destroy()
    finally:
        server.shutdown()
        server.server_close()


def shot_dialog(out, scale):
    """Sicherheitsrueckfrage vor dem Zuruecksetzen (modaler Dialog)."""
    adapter, server = start_mock(device_type="Gen-1.5", version="2.0.8442", name="Living-Room-TV")
    try:
        app = make_app(scale=scale)

        def capture():
            grab(app, out, "dialog-reset", settle=0.6)
            for w in app.winfo_children():          # Dialog schliessen, damit es weitergeht
                if w.winfo_class() == "Toplevel":
                    w.destroy()

        app.after(700, capture)
        app.dialog("Reset adapter?",
                   "All custom settings (name, language, password, wallpaper) are cleared and the "
                   "adapter restarts with its factory defaults. This cannot be undone.",
                   "Reset", "Cancel")
        app.destroy()
    finally:
        server.shutdown()
        server.server_close()


def shot_languages(out, scale):
    """Dieselbe Seite in zwei weiteren Sprachen – zeigt die Lokalisierung."""
    adapter, server = start_mock(device_type="Gen-1.5", version="2.0.8385", name="Wohnzimmer-TV")
    try:
        for code, name in (("de-DE", "ui-german"), ("ja-JP", "ui-japanese")):
            app = make_app(language=code, scale=scale)
            grab(app, out, name)
            app.destroy()
    finally:
        server.shutdown()
        server.server_close()
    i18n.set_language("en-US")


def shot_connect(out, scale):
    """Startzustand ohne verbundenen Adapter."""
    app = make_app(find_adapter=False, scale=scale, size=(1600, 760))
    grab(app, out, "connect")
    app.destroy()


def shot_gen3(out, scale):
    """Gen-3-Adapter: Hinweis, dass Updates dafuer nicht an echter Hardware geprueft sind."""
    adapter, server = start_mock(device_type="Gen-3", version="3.9520.40", name="Office-4K")
    try:
        app = make_app(scale=scale, size=(1600, 780))
        app.show_page("firmware")
        grab(app, out, "firmware-gen3")
        app.destroy()
    finally:
        server.shutdown()
        server.server_close()


GROUPS = {"pages": shot_pages, "dark": shot_dark, "dialog": shot_dialog,
          "languages": shot_languages, "connect": shot_connect, "gen3": shot_gen3}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="docs/screenshots", help="Zielordner (Standard: docs/screenshots)")
    p.add_argument("--scale", type=float, default=1.25, help="Aufnahmeskalierung (Standard: 1.25)")
    p.add_argument("--only", choices=sorted(GROUPS), help="nur diese Gruppe aufnehmen")
    args = p.parse_args()

    out = (ROOT / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    if args.only:
        GROUPS[args.only](out, args.scale)
        sys.stdout.flush()
        # Tk raeumt mehrere nacheinander erzeugte Fenster samt Hintergrundfaeden nicht sauber ab
        # ("Tcl_AsyncDelete"), darum hier hart beenden – die Bilder sind geschrieben.
        os._exit(0)

    print(f"Screenshots -> {out}")
    for name in GROUPS:                 # jede Gruppe in einem eigenen Prozess, sonst stoert Tk sich selbst
        print(f"{name}:", flush=True)
        cmd = [sys.executable, str(Path(__file__).resolve()), "--only", name,
               "--out", str(out), "--scale", str(args.scale)]
        if subprocess.run(cmd, cwd=ROOT).returncode != 0:
            raise SystemExit(f"group {name} failed")
    print("done")


if __name__ == "__main__":
    main()
