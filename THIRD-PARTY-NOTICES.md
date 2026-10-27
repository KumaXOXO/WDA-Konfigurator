# Third-party notices

This project is licensed under the [MIT License](LICENSE). That license covers the code,
documentation and translations written for this repository — nothing else. The items below
belong to other parties.


## Microsoft Corporation

### Trademarks

"Microsoft", "Surface", "Windows", "Miracast"¹ and "Wireless Display Adapter" are trademarks of
their respective owners. This project is **not** affiliated with, authorised by, sponsored by or
endorsed by Microsoft Corporation. The names are used only to identify the hardware this tool
talks to, as permitted by nominative fair use.

¹ "Miracast" is a certification mark of the Wi-Fi Alliance.

### Firmware

The firmware images for the Wireless Display Adapter are Microsoft's software and are **not
distributed with this project**, neither in the repository nor in the released EXE. The tool
downloads them from Microsoft's own servers (`go.microsoft.com` / `download.microsoft.com`) at
the moment they are needed, and refuses any redirect that leaves `microsoft.com`.

Only the metadata is stored here — version number, release date, file size, SHA-256 and the
source URL — so that a download can be verified against a record made at a known point in time.
Microsoft's firmware remains subject to Microsoft's own terms. Installing it on your adapter is
the same act the original Microsoft app performed.

### Wallpaper images

The four wallpapers built into the adapter firmware are Microsoft artwork. They are not in this
repository, not in the released EXE and not in the documentation screenshots — which is why the
preview tiles in those screenshots are empty placeholders. Previews are only generated locally,
from a copy of the original app that the user already has (see
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#wallpaper-previews)).

### The original application

No code, resource or binary from the *Microsoft/Surface Wireless Display Adapter* app is part of
this repository. Its app package is excluded by `.gitignore` and never published.

The network protocol this tool speaks was determined by observing the traffic between that app
(version 4.232.137.0) and an adapter owned by the author, and by examining the app's resource
files, for the single purpose of writing an independent program able to configure that hardware
after the official app became unavailable. Facts obtained that way — URLs, parameter names,
status codes, file layouts — are interoperability information, not expression: in the EU this
is expressly permitted (Directive 2009/24/EC Art. 6; in Germany § 69e UrhG, with § 69g(2)
voiding contrary contract terms), and the CJEU confirmed in C‑406/10 (*SAS Institute v. World
Programming*) that functionality, formats and protocols are not themselves protected by
copyright. See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the resulting description.


## Fonts and icons

The interface draws its icons from **Segoe Fluent Icons** and **Segoe MDL2 Assets**, and its
text in **Segoe UI** / **Segoe UI Variable** — all shipped with Windows and used as installed
system fonts. No font file is redistributed. On a system without them, tkinter falls back to a
default font and the icon glyphs may appear as boxes.


## Python and bundled components

* **Python** (Python Software Foundation License) — only the standard library is used at
  runtime; `tkinter` provides the interface.
* **Pillow** ([MIT-CMU licence](https://github.com/python-pillow/Pillow/blob/main/LICENSE)) —
  optional, used for custom wallpapers and for generating the documentation screenshots.
* **PyInstaller** (GPL v2 with an [exception](https://pyinstaller.org/en/stable/license.html)
  permitting the distribution of bundled applications under any licence) — used to build the
  EXE, and parts of its bootloader are embedded in the resulting executable.

A released `WDA-Konfigurator.exe` therefore contains: this project's code (MIT), a CPython
interpreter with the standard library, Tcl/Tk, the PyInstaller bootloader, and the translation
files from `locales/`. It contains no Microsoft material.


## Reporting a problem

If you believe something in this repository infringes your rights, please open an issue or
contact the maintainer, and it will be removed while the question is looked at.
