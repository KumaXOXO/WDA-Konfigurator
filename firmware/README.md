# Firmware library

**The firmware binaries are not in this repository.** They are Microsoft's files and are not
ours to redistribute. What is tracked here is the metadata: which version exists, how big it
is, what its SHA-256 is and which URL it came from — so a download can be verified byte for
byte against a record made at a known point in time.

Download the real files from Microsoft's own servers:

```bash
python wda_tool.py firmware fetch --type Gen-1.5
python wda_tool.py firmware fetch --type Type_S
python wda_tool.py firmware fetch --type Gen-3        # 128 MB, includes the signature file
```

The GUI does the same automatically the first time a connected adapter needs a firmware it does
not have.


## Layout

```
firmware/
  Type_S/1.3.8384/        WirelessDisplayAdapterFirmware_10.sbin   (17.7 MB)
                          version.xml
                          firmware.json
  Gen-1.5/2.0.8442/       WirelessDisplayAdapterFirmware_20.sbin   (26.1 MB)
                          version.xml
                          firmware.json
  Gen-3/3.9520.47/        WirelessDisplayAdapterFirmware_30.sbin   (128.2 MB)
                          WirelessDisplayAdapterSignature_30.sign  (256 bytes)
                          version.xml
                          firmware.json
```

Any number of versions can live side by side; the app lists them newest first and lets you pick
one deliberately — which is how you downgrade away from the HDCP-plagued 2.0.8350.

`version.xml` is Microsoft's own version manifest, saved exactly as it was served — like the
images, it is downloaded rather than kept in this repository. `firmware.json` is the record this
tool writes, and the only one tracked here:

```json
{
  "device_type": "Gen-1.5",
  "version": "2.0.8442",
  "release_date": "10/28/2020",
  "file": "WirelessDisplayAdapterFirmware_20.sbin",
  "size": 26084208,
  "sha256": "dfc846b75843836e021e92d05be70c01045a1684309abadcbf449ceae37dccdd",
  "source": "https://go.microsoft.com/fwlink/?LinkID=618364",
  "downloaded": "2026-10-27"
}
```

For Gen 3 there is an additional `"signature"` object with the same fields for the `.sign` file.
A Gen 3 adapter rejects an image that arrives without its matching signature.


## Where the app looks

In order:

1. `firmware/` next to the EXE (or next to the scripts, when running from source)
2. the copy embedded in the EXE, if it was built with firmware included
3. `%LOCALAPPDATA%\WDA-Konfigurator\firmware` — the download cache

Identical files found in more than one place are listed once, keyed by SHA-256.


## Verification

Two independent checks, both unconditional:

* **On download** — the received size must match `Content-Length` *and* the
  `firmwarePackageSize` Microsoft publishes in `version.xml`. Redirects that leave
  `microsoft.com` are refused outright.
* **On every read** — size and SHA-256 are recomputed and compared against `firmware.json`
  immediately before the image is uploaded to the adapter. A damaged or swapped file is refused
  rather than sent to the hardware.

If you hit *"Firmware … is damaged (size/SHA-256 does not match)"*, delete that version folder
and fetch it again.


## Known versions

| Type | Version | Released | Size | Notes |
|---|---|---|---|---|
| `Type_S` (Gen 1, model 1627) | 1.3.8384 | 2019-10-15 | 17,695,600 B | not tested on real hardware |
| `Gen-1.5` (model 1733) | 2.0.8442 | 2020-10-28 | 26,084,208 B | tested |
| `Gen-3` (4K) | 3.9520.47 | 2021-11-11 | 128,156,708 B | + 256 B signature; not tested on real hardware |

These were the current versions as of October 2026. Microsoft has not shipped new firmware for
these adapters in years, but `firmware fetch` always asks the manifest rather than assuming.


## Custom firmware

`inspect_custom_firmware()` can tell a plausible image from a random file — header magic, the
embedded build marker, the presence of a bootloader, a sane size — and the GUI shows what it
found plus any warnings. It cannot validate an image the way the adapter does.

Third-party or modified firmware can brick an adapter permanently, and the reset button does
not help once the bootloader is gone. The GUI makes you type `RISK` to confirm for that reason.
