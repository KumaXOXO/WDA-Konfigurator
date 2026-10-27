<div align="center">

# WDA Konfigurator

**Unofficial configuration tool for the Microsoft Wireless Display Adapter** — a replacement
for the discontinued *Surface Wireless Display Adapter* app.

Rename it, change its display language, set a wallpaper, require a PIN or a password,
and install official Microsoft firmware. In 20 languages, light and dark.

[Download](#download) · [User guide](docs/USAGE.md) · [Protocol](docs/PROTOCOL.md) · [Development](docs/DEVELOPMENT.md)

![The adapter page](docs/screenshots/adapter.png)

</div>

---

Microsoft pulled its Wireless Display Adapter app from the Store and it no longer installs on
current Windows builds. The hardware still works perfectly — there was just no longer a way to
configure or update it. This tool is that way.

> **Tested hardware:** only the **Gen 1.5** adapter (model 1733). Firmware updates for **Gen 1**
> (`Type_S`, model 1627) and **Gen 3** are implemented exactly like in the original app — same
> commands, same files from Microsoft — but could **not be tested on a real device**, because the
> author doesn't own one. The app says so where it matters. If you try it, please report whether
> it worked.

> Not affiliated with or endorsed by Microsoft. "Microsoft", "Surface" and "Wireless Display
> Adapter" are trademarks of Microsoft Corporation. This project contains **no** Microsoft code,
> app files or firmware; firmware is downloaded from Microsoft's own servers when it is needed.
> See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).


## Features

- Detects the adapter automatically as soon as you connect with **Windows logo key + K**
- Rename the adapter, change the language it shows on the display
- Built-in wallpapers or upload your own image
- "Enter a PIN when connecting a new device", password protection, reset to defaults, restart
- **Firmware updates** with the official Microsoft firmware, verified by SHA-256:

  | Adapter | Newest firmware | Tested on real hardware |
  |---|---|---|
  | Gen 1 (`Type_S`, model 1627) | 1.3.8384 | ❌ no device available |
  | Gen 1.5 (model 1733) | 2.0.8442 | ✅ |
  | Gen 3 (4K) | 3.9520.47 + signature | ❌ no device available |

- Install an **older** version on purpose, or a custom file (behind a hard confirmation)
- Detects an unstable Miracast link and warns before an update or reset
- Fluent / Windows 11 look, light & dark mode, responsive, high-DPI aware
- UI in all 20 languages the adapter supports (default: English)
- A command-line tool (`wda_tool.py`) and a Miracast diagnostics recorder (`wda_diag.py`)

Brightness cannot be set — the adapter has no such command, and the original app didn't offer
one either.


## Screenshots

| | |
|---|---|
| ![Firmware](docs/screenshots/firmware.png) | ![Update running](docs/screenshots/firmware-update.png) |
| **Firmware** — compares versions, downloads from Microsoft, verifies the checksum | **Update** — progress for transfer and installation, with the warnings that matter |
| ![Dark mode](docs/screenshots/adapter-dark.png) | ![Custom firmware](docs/screenshots/firmware-custom.png) |
| **Dark mode** — follows the Windows setting | **Custom firmware** — inspected, and gated behind a typed confirmation |
| ![German](docs/screenshots/ui-german.png) | ![Japanese](docs/screenshots/ui-japanese.png) |
| **20 languages** — switchable at runtime… | …with a font that suits each one |

More in the [user guide](docs/USAGE.md).


## Download

Grab `WDA-Konfigurator.exe` from the [latest release](../../releases/latest). It is a single
file — no installer, no dependencies, no Python needed. Then press **Windows logo key + K**,
connect to your adapter, and the app picks it up.

Windows will warn about an unsigned executable from an unknown publisher; there is no code
signing certificate behind this project. If you'd rather not trust a binary, run it from source
(below) or [build it yourself](docs/DEVELOPMENT.md#build).

The released EXE ships **without** Microsoft firmware. The first time a connected adapter needs
one, the app downloads it from Microsoft and keeps it in
`%LOCALAPPDATA%\WDA-Konfigurator\firmware`, so later updates work offline.


## Run from source

Requirements: Windows 10/11 with Miracast support, Python 3.10+. Pillow is optional and only
needed for custom wallpapers.

```bash
python wda_gui.py
```

To pre-download firmware into the local library instead of waiting until it's needed:

```bash
python wda_tool.py firmware fetch --type Gen-1.5     # Type_S | Gen-1.5 | Gen-3
```


## Command line

```bash
python wda_tool.py discover
python wda_tool.py --host 192.168.137.247 info
python wda_tool.py --host 192.168.137.247 rename Room-1
python wda_tool.py --host 192.168.137.247 language de-DE
python wda_tool.py --host 192.168.137.247 firmware update
```

Every write asks for confirmation; `--yes` skips the question, `--dry-run` only shows what would
happen. Global flags go **before** the subcommand. Full reference in the
[user guide](docs/USAGE.md#6-command-line).


## How it works

The adapter runs a small web service, reachable over the Miracast / Wi-Fi Direct link:

```
GET http://<adapter>/cgi-bin/msupload.sh?Action=<command>&… → JSON
```

Gen 3 uses HTTPS with a pinned certificate. Firmware and wallpapers are uploaded as
`multipart/form-data`; Gen 3 additionally needs `StartFirmwareUpdate` first and the signature
file as a second part. The adapter is found through the Windows ARP table, so no IP address has
to be typed.

The full protocol — every command, every error code, the firmware container format, the
discovery mechanisms — is documented in **[docs/PROTOCOL.md](docs/PROTOCOL.md)**, together with
how it was determined and why that is permitted.

You can run the whole thing without hardware: `tools/mock_adapter.py` is a local server that
answers like a real adapter.


## Translations

UI texts are English in the code (`T("…")`); each language is one file in `locales/`. Regional
variants (`es-419`, `fr-CA`, `pt-PT`) contain only the differences and fall back to their main
language.

```bash
python tools/check_locales.py               # missing / unused keys, placeholder mismatches
python tools/check_locales.py --template    # locales/_template.json for a new language
```

Corrections from native speakers are very welcome — see
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#translations).


## License

[MIT](LICENSE) — for the code, documentation and translations in this repository. It does **not**
cover Microsoft's firmware, which is downloaded from Microsoft and remains subject to Microsoft's
terms. See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).


## Project layout

| Path | Content |
|---|---|
| `wda_gui.py` | the GUI (tkinter) |
| `wda_tool.py` | adapter protocol, firmware library, CLI |
| `wda_diag.py` | records a Miracast connection attempt (diagnostics) |
| `i18n.py`, `locales/` | translations |
| `firmware/` | firmware library — metadata only, [binaries are not in the repo](firmware/README.md) |
| `tools/` | mock adapter, screenshot generator, translation checks |
| `build/` | build script, icon and thumbnail generators |
| `docs/` | [usage](docs/USAGE.md), [protocol](docs/PROTOCOL.md), [development](docs/DEVELOPMENT.md) |
