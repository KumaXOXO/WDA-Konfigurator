# Development

Everything here runs on plain Python 3.10+ with the standard library. Pillow is the only
optional dependency (custom wallpapers and the screenshot tool), PyInstaller is needed only to
build the EXE.

```bash
python -m pip install pillow            # optional, for wallpapers + screenshots
python -m pip install pyinstaller       # only for building the EXE
python wda_gui.py
```


## Layout

| Path | Purpose |
|---|---|
| `wda_gui.py` | the GUI: a custom Fluent-styled tkinter shell, three pages |
| `wda_tool.py` | adapter protocol, firmware library, downloads, CLI |
| `wda_diag.py` | read-only Miracast diagnostics recorder |
| `i18n.py`, `locales/` | translations |
| `firmware/` | local firmware library, one folder per version |
| `tools/mock_adapter.py` | a fake adapter so you can work without hardware |
| `tools/screenshots.py` | regenerates `docs/screenshots/` against the mock |
| `tools/check_locales.py` | validates the translation files |
| `tools/make_pt_pt.py` | derives pt-PT from pt-BR |
| `build/` | build script, icon generator, thumbnail generator |

`wda_tool.py` has no dependency on the GUI, so it can be imported on its own — which is what
the mock adapter and the diagnostics tool do.


## Working without an adapter

`tools/mock_adapter.py` is a local HTTP server that answers the same `Action=` calls as a real
adapter and keeps its settings in memory. It reproduces the quirks that actually matter:
`Type_S` reports no `Type` field, `GetLanguangeInfo` keeps the adapter's misspelling, bad names
and passwords come back as `-3` / `-7` / `-4`, and a Gen 3 refuses an image that arrives without
its `signature` part.

```bash
python tools/mock_adapter.py --type Gen-1.5 --version 2.0.8385
# second console:
python wda_tool.py --host 127.0.0.1:8099 info
python wda_tool.py --host 127.0.0.1:8099 --yes rename Mock-1
python wda_tool.py --host 127.0.0.1:8099 -v language de-DE
```

Options: `--port` (8099), `--type` (`Type_S`, `Gen-1.5`, `Gen-3`), `--version`, `--name`,
`--password`, `--wallpaper`. A firmware "install" ramps its progress to 100 % over 20 s. TLS is
not implemented, so a mocked Gen 3 speaks plain HTTP.

`Adapter._connection()` accepts `ip:port`, so no production code needs changing. The GUI only
looks in the ARP table, though, and will never find `127.0.0.1` on its own — the screenshot
tool redirects the search, see below.


## Screenshots

`docs/screenshots/*.png` are generated, not taken by hand, so they can be refreshed after any
UI change:

```bash
python tools/screenshots.py                     # all of them
python tools/screenshots.py --only dark         # one group
python tools/screenshots.py --scale 1.5         # sharper, bigger files
```

It starts the mock on port 8111, points `wda.arp_candidates` at it, builds the window at a
fixed size and captures only the client area (`winfo_rootx/y` begins below the title bar), so
no OS chrome ends up in the image.

Two details worth knowing before you edit it:

* **`_wallpaper_thumb` is stubbed to return `None` on purpose.** The built-in wallpaper images
  belong to Microsoft and must not end up in repository screenshots. The tiles render as plain
  "Image 1…4" placeholders instead. Do not "fix" this.
* **Each group runs in its own subprocess.** Creating and destroying several Tk interpreters in
  one process, with the GUI's worker threads still attached, aborts with
  `Tcl_AsyncDelete: async handler deleted by the wrong thread` and loses buffered output. The
  child calls `os._exit(0)` once the files are written, bypassing Tcl teardown entirely.

Groups are registered in `GROUPS`; a new one is a function `shot_x(out, scale)` that builds an
app with `make_app(...)`, calls `grab(app, out, "name")` and destroys it. `resize(app, height)`
keeps short pages from having a big empty area underneath.


## Translations

The source language is English and lives in the code: every user-visible string is wrapped in
`T("…")`. Each translation is one flat JSON file, `locales/<code>.json`, mapping the English
text to the translated one. A missing key falls back to English, so an incomplete file is
harmless.

Regional variants only carry their differences and point at their base language:

```json
{
  "_fallback": "es-ES",
  "Adapter name": "Nombre del adaptador"
}
```

`fr-CA`, `es-419` and `pt-PT` work this way. `locales/pt-PT.json` is generated from pt-BR by
`tools/make_pt_pt.py` and then corrected by hand.

```bash
python tools/check_locales.py               # missing / unused keys, placeholder mismatches
python tools/check_locales.py --template    # writes locales/_template.json with every text
```

The checker parses the AST for `T("…")` calls, so it finds the real set of strings rather than
grepping. It also compares `{placeholders}` on both sides — a translation that drops `{version}`
would crash at runtime, and that is the most common mistake. It exits non-zero on problems,
which makes it usable as a pre-commit check.

Adding a language means: add the code and its native name to `i18n.LANGUAGES` (the order there
is the order in the dropdown), write `locales/<code>.json`, run the checker. The list is
deliberately limited to languages the adapter itself supports.

Corrections from native speakers are very welcome — the existing files are machine-assisted.


## Build

```bash
build\build.bat            # full build, firmware embedded   (private use)
build\build.bat --clean    # no firmware, no wallpaper previews (release build)
```

`build.bat` generates the icon, optionally the wallpaper previews, and runs PyInstaller in
one-file windowed mode with `locales/` embedded. The output is `WDA-Konfigurator.exe` in the
project root.

The difference matters:

| | full build | `--clean` build |
|---|---|---|
| `locales/` | embedded | embedded |
| Gen 1 + Gen 1.5 firmware | embedded (~41 MB), works offline | not embedded, downloaded on demand |
| Wallpaper previews | embedded, if `app-source/` is present | not embedded |
| Size | ~60 MB | ~18 MB |
| Redistributable | **no** — contains Microsoft firmware | yes |

**Only the `--clean` build may be published.** Microsoft's firmware is not ours to
redistribute; the app downloads it from Microsoft at the moment it is needed, which is the
whole reason that path exists. The released EXE is therefore the `--clean` one.

### Wallpaper previews

`build/make_thumbs.py` scales the four built-in wallpapers down to 288×162 previews — from
`app-source/Images/Wallpapers/`, i.e. from a local copy of the original Microsoft app. That
folder is in `.gitignore` and the previews it produces are Microsoft artwork, so they stay out
of the repository, out of the release EXE and out of the screenshots. Without them the app
shows "Image 1…4" placeholders and works exactly the same.


## Firmware library

See [firmware/README.md](../firmware/README.md) for the on-disk format. Short version: one
folder per version, with the image, Microsoft's `version.xml` and a `firmware.json` carrying
size and SHA-256. The binaries are not in the repository; `python wda_tool.py firmware fetch
--type <T>` downloads them from Microsoft.


## Code style notes

A few conventions that are easy to break accidentally:

* `wda_tool.py` stays importable without the GUI and without Pillow. Pillow is imported inside
  the one function that needs it.
* Every user-visible string goes through `T()`. Strings built by concatenation cannot be
  translated — use `T("… {x} …").format(x=…)`.
* Writes to the adapter go through `Adapter.check()`, which turns a non-zero `ErrorCode` into an
  `AdapterError` with a translated message. Don't read `ErrorCode` by hand.
* The GUI runs adapter I/O on worker threads via `run_bg()` and comes back to the Tk thread
  through `post()`. Never touch widgets from a worker thread.
* `render()` rebuilds the current page from scratch; widget references captured earlier are dead
  after it runs.
* Sizes use `self.px(n)` so high-DPI scaling keeps working.


## Testing against real hardware

Only Gen 1.5 (model 1733) has been verified. If you own a Gen 1 (`Type_S`, model 1627) or a
Gen 3 and are willing to try an update, the useful report is: adapter model, firmware version
before and after, and the log from the About page (**Copy log**). Both generations are
implemented from the original app's own sequence, and Gen 3 additionally needs its HTTPS
certificate pin to still match — that is the most likely thing to have changed.
