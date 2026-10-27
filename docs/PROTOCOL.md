# The Wireless Display Adapter configuration protocol

This document describes how the Microsoft Wireless Display Adapter is configured over the
network. It is the reference the code in this repository is written against.

### Why this document exists

Microsoft removed the *Microsoft/Surface Wireless Display Adapter* app from the Microsoft
Store, and it no longer installs on current Windows builds. Without it the adapter cannot be
renamed, its display language cannot be changed, password protection cannot be turned on, and
— most importantly — its firmware cannot be updated. The hardware still works, so the only
thing missing is a program that speaks to it.

The protocol below was recovered by observing the traffic between the original app
(version 4.232.137.0) and a Gen 1.5 adapter, and by reading the app's own resource files and
managed assemblies, for the sole purpose of writing an independent program that can talk to
hardware the author owns. This is interoperability information: it is not copied code, and
nothing here reproduces any part of Microsoft's app or firmware. In the EU this kind of
analysis is explicitly permitted for exactly this purpose (Directive 2009/24/EC Art. 6, in
Germany § 69e UrhG; see also CJEU C‑406/10, *SAS Institute v. World Programming*). The
resulting facts — URLs, parameter names, status codes — are not themselves protectable.

Nothing in this repository is Microsoft code. Firmware is downloaded from Microsoft's own
servers at the moment it is needed, not redistributed.


## 1. Transport

The adapter runs a tiny CGI web service, reachable only while the Miracast / Wi‑Fi Direct link
is up. Windows puts the adapter on a private `192.168.x.x` network of its own when you connect
with **Windows logo key + K**.

| | Gen 1 (`Type_S`, model 1627) | Gen 1.5 (model 1733) | Gen 3 (4K) |
|---|---|---|---|
| Scheme | `http://` (port 80) | `http://` (port 80) | `https://` (port 443) |
| Certificate | – | – | self‑signed, **pinned** |
| `Timestamp` parameter | yes | yes | no |
| Firmware signature | no | no | yes, required |

All requests go to one path:

```
GET http://<adapter>/cgi-bin/msupload.sh?Action=<Command>&<Key>=<Value>&…
```

The response is always JSON. Writes additionally return `ErrorCode`.

```http
GET /cgi-bin/msupload.sh?Action=GetDeviceName HTTP/1.1
Connection: Keep-Alive

HTTP/1.1 200 OK
Content-Type: application/json

{"DeviceName": "Living-Room-TV", "ErrorCode": 0}
```

Timeouts used by the original app, and therefore here as well: 5 s per command
(`DeviceProviderBase.HttpTimeOut`), 3 s for a reachability ping (`HttpHelper.Ping`), 2 s between
firmware‑state polls (`FirmwareUploadManager.RetrieveTime`).

### 1.1 The `Timestamp` parameter

Gen 1 and Gen 1.5 expect a `Timestamp` on some commands. The value is a .NET
`DateTime.Now.Ticks` — 100‑nanosecond intervals since 0001‑01‑01, in **local** time:

```python
delta = datetime.datetime.now() - datetime.datetime(1, 1, 1)
ticks = (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10
```

The adapter does not validate it; it exists to defeat caching. Gen 3 does not use it.

### 1.2 Gen 3 and HTTPS

A Gen 3 adapter only answers over TLS and presents a self‑signed certificate, so ordinary
certificate validation cannot succeed. The original app pins the certificate by SHA‑1
thumbprint instead, and so does this tool:

```
B4A330EC50D8DB1D2EE4E3EAFA38595500F36022
```

The client therefore disables hostname and chain checking, requires TLS 1.2 or newer, and then
compares the SHA‑1 of the DER‑encoded peer certificate against the constant above. A mismatch
aborts the connection. Because the firmware is old, the cipher security level is lowered to
`DEFAULT:@SECLEVEL=1`; without it, modern OpenSSL builds refuse the handshake.

Since `Type` is only reported *after* a successful request, the generation cannot be known in
advance. `Adapter.detect_scheme()` therefore tries HTTPS first and falls back to HTTP.


## 2. Commands

### 2.1 Read

| Action | Response fields | Notes |
|---|---|---|
| `RetrieveVersion` | `Version`, `Type` | needs `Timestamp`. **Gen 1 omits `Type`** — a missing field means `Type_S` |
| `GetDeviceName` | `DeviceName` | also used as a cheap liveness ping |
| `GetLanguangeInfo` | `LanguageCode`, `CurrentLanguage` | the misspelling is the adapter's, not a typo here. `LanguageCode` is a comma‑separated list of supported codes |
| `GetOverscanSetting` | `IsAutoAdjust`, `OverscanSettingValue` | |
| `GetPasswordProtectState` | `PasswordProtect` | `"true"` / `"false"` as strings |
| `VerifyAuthorizedPassword` | `VerifyResult` | parameter `AuthorizedPassword`; `Timestamp` on Gen 1/1.5 |
| `GetPBCMode` | `PBCModeStatus` | `Auto` = connect without PIN, `Disabled` = PIN required (the app calls this "PinOnly") |
| `GetWallpaperID` | `WallpaperID` | `1`–`4` = built‑in image, `0` = custom upload |
| `RetrieveFirmwareUpgradeState` | `Progress`, `State` | needs `Timestamp`; see §3 |

### 2.2 Write

Every write returns `{"ErrorCode": n}`. If password protection is on, `AuthorizedPassword=<password>`
must be appended to each of these; if it is off, the parameter is ignored.

| Action | Parameters |
|---|---|
| `SetDeviceName` | `NewDeviceName` |
| `SetLanguage` | `LanguageCode` (+ `Timestamp` on Gen 1/1.5) |
| `SetOverscanSetting` | `IsAutoAdjust` (`true`/`false`), `OverscanSettingValue` (+ `Timestamp`) |
| `SetPBCMode` | `PBCModeStatus` = `Auto` \| `Disabled` (+ `Timestamp`) |
| `SetPasswordProtect` | `State` (`true`/`false`), `AuthorizedPassword` (+ `Timestamp`). Turning it **on** sends the new password, turning it **off** sends the current one |
| `ChangePassword` | `OldPassword`, `NewPassword` |
| `SetPredefinedWallpaper` | `WallpaperID` = 1…4 |
| `ResetToFactory` | – |
| `Reboot` | needs `Timestamp` |
| `StartFirmwareUpdate` | `Mode` = `Manual`; **Gen 3 only** |

### 2.3 Input rules

These are the original app's client‑side rules; the adapter rejects violations with an error
code, so validating first just gives a better message.

* **Device name** — 1 to 32 characters from `a–z A–Z 0–9 + - _ ( ) { } [ ]`.
  Regex of the invalid set: `([^a-zA-Z0-9_\+\-\(\)\[\]\}\{])`
* **Password** — `^[a-zA-Z0-9+\-_(){}\[\]]{6,64}$`
* **Language** — must be one of the codes from `GetLanguangeInfo`

### 2.4 Error codes

`ErrorCode: 0` means success. The names come from the app's `DeviceCommunicationErrorType`.

| Code | Meaning |
|---|---|
| `-1` | Firmware image is invalid |
| `-2` | Writing to RAM failed |
| `-3` | Invalid device name |
| `-4` | Incorrect password |
| `-5` | Firmware update error |
| `-6` | Old password is incorrect |
| `-7` | New password has the wrong format |
| `-8` | Setting could not be changed |
| `-9` | Firmware update was aborted |
| `-10` | Firmware is not password protected |
| `-11` | Error ending the Miracast session |
| `-12` | Adapter is not in projection mode |
| `-13` | A previous firmware update is still running |

### 2.5 What the adapter cannot do

There is **no brightness command**. The original app did not offer one either; the setting
people remember belongs to the TV, not the adapter. `wda_tool.py brightness` exists only to say
so.


## 3. Firmware update

The sequence is the same one the original app uses:

```
(Gen 3 only)  GET  …?Action=StartFirmwareUpdate&Mode=Manual
              POST …?Action=UploadFirmware&Type=<Type>      ← multipart/form-data
   repeat     GET  …?Action=RetrieveFirmwareUpgradeState&Timestamp=…
              until Progress >= 100 or the adapter stops answering (it is rebooting)
```

The upload is a `multipart/form-data` POST with a random UUID boundary:

| Form field | File name | Content type | Generations |
|---|---|---|---|
| `NewImage` | `WirelessDisplayAdapterFirmware_10/20/30.sbin` | `application/octet-stream` | all |
| `signature` | `WirelessDisplayAdapterSignature_30.sign` | `application/octet-stream` | **Gen 3 only, mandatory** |

A Gen 3 adapter refuses an image without its matching 256‑byte signature file with `ErrorCode: -1`.

The body is sent in 32 KB blocks so that progress can be reported. Transfers are large (18 MB
for Gen 1, 26 MB for Gen 1.5, 128 MB for Gen 3) and the Miracast link is not always stable, so:

* if the send fails, the client waits 3 s and asks `GetDeviceName`;
* **no answer** → the link is gone. Retrying is pointless, so it reports a lost connection;
* **answer** → one single retry, then give up.

An interrupted upload is discarded by the adapter. It keeps the firmware it already has, which
is what makes the retry safe. Once `UploadFirmware` has been acknowledged, however, the adapter
is writing flash — do not unplug it.

`RetrieveFirmwareUpgradeState` returns `Progress` 0…100 and a `State` string (`Upgrading`,
`Done`). The adapter usually stops responding near the end because it reboots; that is success,
not failure, and the client treats a connection loss during the install phase as "probably
restarting". Any non‑zero `ErrorCode` during polling aborts the update. The overall timeout is
900 s.


## 4. Wallpaper

Gen 1.5 adapters running firmware 2.0.8385 or newer show a wallpaper behind the "ready to
connect" screen. Four images are built into the firmware (`SetPredefinedWallpaper`,
`WallpaperID` 1–4); a custom one is uploaded with:

```
POST …?Action=UploadWallpaper[&AuthorizedPassword=…]
```

as `multipart/form-data` with **two** PNG parts, each with `Content-Encoding: binary`:

| Form field | File name | Purpose |
|---|---|---|
| `WallpaperBlackTint` | `WallpaperBlackTint.png` | darkened variant, shown behind the text |
| `WallpaperBlur` | `WallpaperBlur.png` | blurred variant, used while connecting |

The original app renders both variants from the picked image on the PC. The exact filter values
are not visible in the managed code, so this tool approximates them: fit to 1920×1080, then
brightness ×0.6, and for the second part a Gaussian blur with radius 30 before the same
darkening. After a successful upload the adapter reports `WallpaperID: 0`.


## 5. Firmware distribution

Microsoft publishes each generation's firmware behind a permanent `go.microsoft.com/fwlink`
redirect: one for a small XML version manifest, one for the image, and for Gen 3 one for the
signature.

| Type | Version manifest | Image | Signature |
|---|---|---|---|
| `Type_S` | `LinkID=389554` | `LinkID=389555` | – |
| `Gen-1.5` | `LinkID=618365` | `LinkID=618364` | – |
| `Gen-3` | `LinkID=2124801` | `LinkID=2130433` | `LinkID=2130316` |

The manifest is small and tells you the current version, its date and the exact byte size:

```xml
<vers>
  <rev>1</rev>
  <firmwareVersion>2.0.8442</firmwareVersion>
  <firmwareReleaseDate>10/28/2020</firmwareReleaseDate>
  <firmwarePackageSize>26084208</firmwarePackageSize>
  <osVersionRequiredByApp>8.1.0.0</osVersionRequiredByApp>
  <osVersionRequiredByFirmware>8.1.0.0</osVersionRequiredByFirmware>
  <firmwareReleaseDescription Languagekey="en-us">https://go.microsoft.com/fwlink/?LinkID=717114</firmwareReleaseDescription>
  …
</vers>
```

Two safeguards apply to every download: the redirect target must end in `microsoft.com`
(anything else is refused), and the received size must match both `Content-Length` and
`firmwarePackageSize`. The SHA‑256 of what arrived is recorded in `firmware.json` and verified
again every single time the file is read, right before it is uploaded to the adapter — see
[firmware/README.md](../firmware/README.md).

### 5.1 Recognising a firmware image

Enough of the container format is known to tell a plausible image from a random file. This is a
sanity check for the "custom firmware" option, not a signature check — the adapter is the only
thing that really validates an image.

**Gen 1 and Gen 1.5** (`.sbin`, a packed flash layout):

| Offset | Bytes | Meaning |
|---|---|---|
| `0x00` | `02 00 00 00` | container marker |
| `0x10` | `44 33 22 11` | magic, little‑endian `0x11223344` |

Within the first 8 MB there is an ASCII build marker matching `(\d{4})_ENG_microsoft` — `8442`
in `2.0.8442` — and the string `U-Boot` from the bootloader.

**Gen 3**: the image (`install_ota.gz.Release`) is a plain gzip archive and starts with `1f 8b`.


## 6. Finding the adapter

Three mechanisms, cheapest first:

1. **ARP table.** While a Miracast session is up, Windows adds the adapter as a static entry.
   `arp -a` lists it under a `192.168.x.x` interface; every peer in that /24 (excluding the
   interface address itself and the broadcast entry) is a candidate, which is then probed with
   `GetDeviceName`. This is what the GUI uses, and it is essentially instant.
2. **UDP heartbeats.** Adapters broadcast a small JSON heartbeat to port **7238** containing
   `IPAddress`, `DongleName` and `ModelName`. `wda_tool.py discover --udp 10` listens for them.
3. **Subnet scan.** As a last resort, `discover --subnet 192.168.137.0/24` probes every host in
   a /24 with 64 threads.

The Miracast session itself runs RTSP on TCP **7236**; `wda_diag.py` watches that port to tell a
dropped video link apart from an unreachable web service.


## 7. Reproducing this without hardware

`tools/mock_adapter.py` implements every command above as a local HTTP server, so the protocol
description can be exercised directly:

```bash
python tools/mock_adapter.py --type Gen-1.5 --version 2.0.8385
python wda_tool.py --host 127.0.0.1:8099 info
python wda_tool.py --host 127.0.0.1:8099 --yes rename Mock-1
```

It reproduces the quirks that matter: no `Type` field for `Type_S`, the `GetLanguangeInfo`
spelling, the error codes for bad names and passwords, and a Gen 3 that rejects an unsigned
image. It does not implement TLS, so Gen 3 is simulated over plain HTTP.
