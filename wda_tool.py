#!/usr/bin/env python3
"""Configuration tool for the Microsoft (Surface) Wireless Display Adapter.

Rebuilt from an analysis of the app version 4.232.137.0 (see docs/PROTOCOL.md).
Python standard library only (Pillow is optional, for custom wallpapers).
Every write access asks for confirmation first.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from i18n import T

CGI_PATH = "/cgi-bin/msupload.sh"
HTTP_TIMEOUT = 5.0            # DeviceProviderBase.HttpTimeOut = 5000 ms
PING_TIMEOUT = 3.0            # HttpHelper.Ping timeout = 3000 ms
UPLOAD_TIMEOUT = 900.0
POLL_INTERVAL = 2.0           # FirmwareUploadManager.RetrieveTime = 2000 ms
UDP_HEARTBEAT_PORT = 7238
DEVICE_NAME_INVALID = re.compile(r"([^a-zA-Z0-9_\+\-\(\)\[\]\}\{])")


def valid_device_name(name):
    """Rule of the original app: 1–32 characters from a-z A-Z 0-9 + - _ ( ) { } [ ]."""
    return 1 <= len(name) <= 32 and not DEVICE_NAME_INVALID.search(name)


# From XMLResources/*/*.xml of the app
DEVICE_TYPES = {
    "Type_S": {
        "generation": "Gen 1",
        "https": False,
        "timestamp": True,
        "version_url": "https://go.microsoft.com/fwlink/?LinkID=389554",
        "firmware_url": "https://go.microsoft.com/fwlink/?LinkID=389555",
        "signature_url": None,
        "firmware_name": "WirelessDisplayAdapterFirmware_10.sbin",
    },
    "Gen-1.5": {
        "generation": "Gen 1.5",
        "https": False,
        "timestamp": True,
        "version_url": "https://go.microsoft.com/fwlink/?LinkID=618365",
        "firmware_url": "https://go.microsoft.com/fwlink/?LinkID=618364",
        "signature_url": None,
        "firmware_name": "WirelessDisplayAdapterFirmware_20.sbin",
    },
    "Gen-3": {
        "generation": "Gen 3",
        "https": True,
        "timestamp": False,
        "version_url": "https://go.microsoft.com/fwlink/?LinkID=2124801",
        "firmware_url": "https://go.microsoft.com/fwlink/?LinkID=2130433",
        "signature_url": "https://go.microsoft.com/fwlink/?LinkID=2130316",
        "firmware_name": "WirelessDisplayAdapterFirmware_30.sbin",
        "signature_name": "WirelessDisplayAdapterSignature_30.sign",
    },
}
GEN3_CERT_SHA1 = "B4A330EC50D8DB1D2EE4E3EAFA38595500F36022"

# Display languages of the adapter (code → native name)
LANGUAGES = {
    "en-us": "English", "en-gb": "English (United Kingdom)", "de-de": "Deutsch",
    "fr-fr": "Français (France)", "fr-ca": "Français (Canada)", "it-it": "Italiano",
    "es-es": "Español (España)", "es-mx": "Español (México)", "es-419": "Español (América Latina)",
    "nl-nl": "Nederlands", "da-dk": "Dansk", "sv-se": "Svenska", "nb-no": "Norsk bokmål",
    "fi-fi": "Suomi", "pt-pt": "Português (Portugal)", "pt-br": "Português (Brasil)",
    "pl-pl": "Polski", "cs-cz": "Čeština", "ru-ru": "Русский", "ja-jp": "日本語",
    "ko-kr": "한국어", "zh-cn": "中文(简体)", "zh-tw": "中文(繁體)", "th-th": "ไทย", "ar-ae": "العربية",
}

# DeviceCommunicationErrorType of the app
ERROR_CODES = {
    -1: "Firmware image is invalid", -2: "Writing to RAM failed",
    -3: "Invalid device name", -4: "Incorrect password", -5: "Firmware update error",
    -6: "Old password is incorrect", -7: "New password has the wrong format",
    -8: "Setting could not be changed", -9: "Firmware update was aborted",
    -10: "Firmware is not password protected", -11: "Error ending the Miracast session",
    -12: "Adapter is not in projection mode", -13: "A previous firmware update is still running",
}


def error_text(code):
    return T(ERROR_CODES.get(code, "unknown"))


class AdapterError(Exception):
    pass


class ConnectionLost(AdapterError):
    """The Miracast/Wi-Fi Direct link to the adapter went away."""


class UploadAborted(AdapterError):
    def __init__(self, sent, total, cause, response):
        self.sent, self.total, self.cause, self.response = sent, total, cause, response
        super().__init__(T("Upload aborted after {sent:.1f} of {total:.1f} MB ({cause}). Adapter response: {response}")
                         .format(sent=sent / 1048576, total=total / 1048576, cause=cause,
                                 response=response or T("none")))


def dotnet_ticks():
    """.NET DateTime.Now.Ticks (100 ns since 0001-01-01, local time)."""
    delta = datetime.datetime.now() - datetime.datetime(1, 1, 1)
    return str((delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10)


class Adapter:
    def __init__(self, host, use_https=None, password=None, verbose=False):
        self.host = host
        self.use_https = use_https
        self.password = password
        self.verbose = verbose
        self.device_type = None
        self.version = None

    # --- Transport -------------------------------------------------------
    def _connection(self, https, timeout):
        # host may be "ip:port"; otherwise 80 or 443
        if not https:
            return http.client.HTTPConnection(self.host, timeout=timeout)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE   # self-signed; verified by fingerprint below
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        except ssl.SSLError:
            pass
        conn = http.client.HTTPSConnection(self.host, context=ctx, timeout=timeout)
        conn.connect()
        der = conn.sock.getpeercert(binary_form=True)
        thumb = hashlib.sha1(der).hexdigest().upper()
        if thumb != GEN3_CERT_SHA1:
            conn.close()
            raise AdapterError(T("Certificate fingerprint does not match: {thumb} (expected {expected})")
                               .format(thumb=thumb, expected=GEN3_CERT_SHA1))
        return conn

    def _url(self, params):
        return CGI_PATH + "?" + "&".join(
            f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in params)

    def _request(self, method, params, body=None, headers=None, timeout=HTTP_TIMEOUT, progress=None):
        if self.use_https is None:
            self.detect_scheme()
        path = self._url(params)
        if self.verbose:
            print(f"> {method} {'https' if self.use_https else 'http'}://{self.host}{path}", file=sys.stderr)
        conn = self._connection(self.use_https, timeout)
        try:
            hdrs = {"Connection": "Keep-Alive"}
            hdrs.update(headers or {})
            if body and progress:
                self._send_body(conn, method, path, hdrs, body, progress)
            else:
                conn.request(method, path, body=body, headers=hdrs)
            resp = conn.getresponse()
            text = resp.read().decode("utf-8", errors="replace")
        finally:
            conn.close()
        if self.verbose:
            print(f"< {resp.status} {text}", file=sys.stderr)
        if resp.status >= 400:
            raise AdapterError(f"HTTP {resp.status}: {text[:200]}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise AdapterError(T("Response is not JSON: {text}").format(text=repr(text[:200])))

    @staticmethod
    def _send_body(conn, method, path, hdrs, body, progress):
        """Send the body in blocks (visible progress). If the adapter aborts, include its response."""
        conn.putrequest(method, path)
        for k, v in hdrs.items():
            conn.putheader(k, v)
        conn.endheaders()
        step = 32 * 1024
        sent = 0
        try:
            for i in range(0, len(body), step):
                conn.send(body[i:i + step])
                sent = min(i + step, len(body))
                progress(sent, len(body))
        except OSError as e:
            raise UploadAborted(sent, len(body), e, Adapter._early_response(conn)) from e

    @staticmethod
    def _early_response(conn):
        """Response the adapter may still have sent before aborting."""
        try:
            conn.sock.settimeout(2)
            resp = conn.getresponse()
            return f"HTTP {resp.status} {resp.read(400).decode('utf-8', 'replace').strip()}"
        except Exception:
            return None

    def command(self, action, *params, timestamp=False):
        p = [("Action", action)]
        if timestamp:
            p.append(("Timestamp", dotnet_ticks()))
        p.extend(params)
        return self._request("GET", p)

    def detect_scheme(self):
        """Gen 3 speaks HTTPS, Gen 1/1.5 HTTP – try both."""
        last = None
        for https in (True, False):
            try:
                self.use_https = https
                conn = self._connection(https, PING_TIMEOUT)
                conn.request("GET", self._url([("Action", "GetDeviceName")]))
                conn.getresponse().read()
                conn.close()
                return https
            except (OSError, http.client.HTTPException, AdapterError) as e:
                last = e
        self.use_https = None
        raise AdapterError(T("Adapter at {host} is not reachable ({error})").format(host=self.host, error=last))

    # --- Read ------------------------------------------------------------
    def retrieve_version(self):
        r = self.command("RetrieveVersion", timestamp=True)
        self.version = str(r.get("Version", "0.0.0"))
        self.device_type = r.get("Type") or "Type_S"   # missing on Gen 1 → Type_S
        return self.version, self.device_type

    @property
    def config(self):
        if self.device_type is None:
            self.retrieve_version()
        cfg = DEVICE_TYPES.get(self.device_type)
        if cfg is None:
            raise AdapterError(T("Unknown device type: {type}").format(type=repr(self.device_type)))
        return cfg

    def get_device_name(self):
        return self.command("GetDeviceName").get("DeviceName", "MicrosoftWirelessDisplay")

    def get_language_info(self):
        r = self.command("GetLanguangeInfo")   # sic, that's the command's name
        codes = [c.strip() for c in str(r.get("LanguageCode", "")).split(",") if c.strip()]
        return codes, str(r.get("CurrentLanguage", "")).strip()

    def get_overscan(self):
        return self.command("GetOverscanSetting")

    def get_password_protect(self):
        return self.command("GetPasswordProtectState").get("PasswordProtect")

    def verify_password(self, password):
        r = self.command("VerifyAuthorizedPassword", ("AuthorizedPassword", password),
                         timestamp=self.config["timestamp"])
        return str(r.get("VerifyResult")).lower() in ("true", "1")

    def firmware_state(self):
        return self.command("RetrieveFirmwareUpgradeState", timestamp=True)

    # --- Write -----------------------------------------------------------
    def _auth(self):
        return [("AuthorizedPassword", self.password)] if self.password is not None else []

    @staticmethod
    def check(resp):
        code = int(resp.get("ErrorCode", 0))
        if code != 0:
            raise AdapterError(T("Adapter reports error {code}: {text}").format(code=code, text=error_text(code)))
        return resp

    def set_device_name(self, name):
        return self.check(self.command("SetDeviceName", ("NewDeviceName", name), *self._auth()))

    def set_language(self, code):
        return self.check(self.command("SetLanguage", ("LanguageCode", code), *self._auth(),
                                       timestamp=self.config["timestamp"]))

    def set_overscan(self, auto, value):
        return self.check(self.command("SetOverscanSetting", ("IsAutoAdjust", str(auto).lower()),
                                       ("OverscanSettingValue", int(value)), *self._auth(),
                                       timestamp=self.config["timestamp"]))

    def reboot(self):
        return self.check(self.command("Reboot", timestamp=True))

    def start_firmware_update(self, mode="Manual"):
        return self.check(self.command("StartFirmwareUpdate", ("Mode", mode)))

    def _post_multipart(self, params, parts, timeout=UPLOAD_TIMEOUT, progress=None):
        """parts: list of (form field, file name, content type, bytes, extra headers)."""
        boundary = str(uuid.uuid4())
        chunks = []
        for field, filename, ctype, data, extra in parts:
            head = (f"--{boundary}\r\n"
                    f"Content-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
                    f"Content-Type: {ctype}\r\n" + "".join(f"{k}: {v}\r\n" for k, v in extra.items()) + "\r\n")
            chunks.append(head.encode() + data + b"\r\n")
        body = b"".join(chunks) + f"--{boundary}--\r\n".encode()
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body))}
        return self._request("POST", params, body=body, timeout=timeout, progress=progress or (lambda d, t: None),
                             headers=headers)

    def link_alive(self):
        """Is the adapter still reachable? (short check, e.g. after an aborted upload)"""
        try:
            self.command("GetDeviceName")
            return True
        except (OSError, http.client.HTTPException, AdapterError):
            return False

    def upload_firmware(self, files, progress=None, log=None):
        """files: list of (form field, file name, bytes).

        If the transfer is aborted, check whether the Miracast link is still there: if not,
        report a lost connection (a retry would fail the same way); if yes, retry once.
        An incomplete upload is discarded by the adapter – it keeps its current firmware.
        """
        parts = [(field, name, "application/octet-stream", data, {}) for field, name, data in files]
        params = [("Action", "UploadFirmware"), ("Type", self.device_type)]
        for attempt in (1, 2):
            try:
                return self.check(self._post_multipart(params, parts, progress=progress))
            except UploadAborted as e:
                if log:
                    log(T("Attempt {n}: {error}").format(n=attempt, error=e))
                time.sleep(3)
                if not self.link_alive():
                    raise ConnectionLost(T("The connection to the adapter was lost during the transfer (Miracast "
                                           "disconnected). The firmware was not installed; the adapter keeps its "
                                           "current version.")) from e
                if attempt == 2:
                    raise
                time.sleep(2)

    # --- PIN, password, reset (Gen 1.5: SetPinCode, ChangePassword) ---------
    def get_pbc_mode(self):
        """'Auto' = connect without PIN, 'Disabled' = PIN only ('PinOnly' in the app)."""
        return str(self.command("GetPBCMode").get("PBCModeStatus", "Unknown"))

    def set_pbc_mode(self, mode):
        return self.check(self.command("SetPBCMode", ("PBCModeStatus", mode), *self._auth(),
                                       timestamp=self.config["timestamp"]))

    def set_password_protect(self, state, password):
        """Password protection on (password = new password) or off (password = current password)."""
        return self.check(self.command("SetPasswordProtect", ("State", str(bool(state)).lower()),
                                       ("AuthorizedPassword", password), timestamp=self.config["timestamp"]))

    def change_password(self, old, new):
        return self.check(self.command("ChangePassword", ("OldPassword", old), ("NewPassword", new)))

    def reset_to_factory(self):
        return self.check(self.command("ResetToFactory", *self._auth()))

    # --- Wallpaper (Gen 1.5 from firmware 2.0.8385) ---------------------------
    def get_wallpaper_id(self):
        return int(self.command("GetWallpaperID").get("WallpaperID", 0))

    def set_predefined_wallpaper(self, wallpaper_id):
        return self.check(self.command("SetPredefinedWallpaper", ("WallpaperID", int(wallpaper_id)), *self._auth()))

    def upload_wallpaper(self, black_tint_png, blur_png):
        parts = [(name, f"{name}.png", "image/png", data, {"Content-Encoding": "binary"})
                 for name, data in (("WallpaperBlackTint", black_tint_png), ("WallpaperBlur", blur_png))]
        return self.check(self._post_multipart([("Action", "UploadWallpaper"), *self._auth()], parts,
                                               timeout=120))


PASSWORD_RE = re.compile(r"^[a-zA-Z0-9+\-_(){}\[\]]{6,64}$")   # rule of the original app


def make_wallpaper_images(path):
    """Prepare a custom image for the adapter: 1920×1080, darkened and blurred.

    The original app creates both variants itself; darkening and blur are approximated
    here (the exact values are not in the managed code). Needs Pillow.
    """
    import io
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    img = ImageOps.fit(Image.open(path).convert("RGB"), (1920, 1080), Image.LANCZOS)
    tint = ImageEnhance.Brightness(img).enhance(0.6)
    blur = ImageEnhance.Brightness(img.filter(ImageFilter.GaussianBlur(30))).enhance(0.6)
    out = []
    for im in (tint, blur):
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        out.append(buf.getvalue())
    return out


def run_firmware_update(adapter, files, on_status, timeout=900, log=None):
    """Same sequence as the app: [StartFirmwareUpdate], UploadFirmware, poll the state.

    on_status(phase, percent, text) is called for upload ("upload") and installation ("install").
    """
    if adapter.config["signature_url"]:
        on_status("start", 0, "StartFirmwareUpdate…")
        adapter.start_firmware_update("Manual")
    adapter.upload_firmware(files, progress=lambda done, total: on_status(
        "upload", done * 100 // total, T("Transferring firmware: {done}/{total} MB").format(
            done=done // 1048576, total=total // 1048576)), log=log)
    on_status("install", 0, T("Transferred. The adapter is installing the firmware…"))
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        try:
            st = adapter.firmware_state()
        except (OSError, http.client.HTTPException, AdapterError) as e:
            on_status("install", 100, T("The adapter no longer responds ({error}) – probably restarting.")
                      .format(error=e.__class__.__name__))
            return
        code = int(st.get("ErrorCode", 0))
        prog = int(st.get("Progress", 0))
        if code != 0:
            raise AdapterError(T("Update failed: {code} {text}").format(code=code, text=error_text(code)))
        on_status("install", prog, T("Installing {percent}% (state {state})").format(percent=prog,
                                                                                  state=st.get("State")))
        if prog >= 100:
            return
    raise AdapterError(T("Timed out waiting for the firmware update"))


# --- Local firmware library ----------------------------------------------
def _firmware_dirs():
    """Firmware library: 'firmware' folder next to the EXE or script, plus the one embedded in the EXE
    and the download cache (firmware fetched from Microsoft at runtime, e.g. Gen 3)."""
    if getattr(sys, "frozen", False):          # running as .exe (PyInstaller)
        cache = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "WDA-Konfigurator" / "firmware"
        return [Path(sys.executable).parent / "firmware", Path(sys._MEIPASS) / "firmware", cache]
    return [Path(__file__).resolve().parent / "firmware"]


FIRMWARE_DIRS = _firmware_dirs()
FIRMWARE_DIR = FIRMWARE_DIRS[0]
FIRMWARE_CACHE = FIRMWARE_DIRS[-1]


def list_local_firmware(device_type):
    """All firmware versions from firmware/<type>/**/firmware.json whose file exists, newest first."""
    found = {}
    for base in FIRMWARE_DIRS:
        for meta_file in (base / device_type).rglob("firmware.json") if (base / device_type).exists() else []:
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            meta["_path"] = str(meta_file.parent / meta["file"])
            if Path(meta["_path"]).exists():
                found.setdefault(meta["sha256"], meta)          # same file only once
    return sorted(found.values(), key=lambda m: version_tuple(m["version"]), reverse=True)


def _read_checked(path, entry):
    data = Path(path).read_bytes()
    if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise AdapterError(T("Firmware {file} is damaged (size/SHA-256 does not match)").format(file=entry["file"]))
    return data


def read_firmware(meta):
    """Read a firmware file and check size + SHA-256 against firmware.json."""
    return _read_checked(meta["_path"], meta)


def firmware_parts(meta, data=None):
    """Upload parts for UploadFirmware: the image as 'NewImage', for Gen 3 plus the signature as 'signature'."""
    cfg = DEVICE_TYPES[meta["device_type"]]
    parts = [("NewImage", cfg["firmware_name"], data if data is not None else read_firmware(meta))]
    sig = meta.get("signature")
    if cfg["signature_url"]:
        if not sig:
            raise AdapterError(T("The signature file for this firmware is missing."))
        parts.append(("signature", cfg["signature_name"],
                      _read_checked(Path(meta["_path"]).with_name(sig["file"]), sig)))
    return parts


def load_local_firmware(device_type):
    """Newest local firmware: (meta, bytes) or (None, None)."""
    metas = list_local_firmware(device_type)
    return (metas[0], read_firmware(metas[0])) if metas else (None, None)


def inspect_custom_firmware(path, device_type):
    """Check a custom firmware file. Returns key figures and warnings – but prevents nothing."""
    data = Path(path).read_bytes()
    info = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "version": None, "warnings": []}
    known = {m["sha256"]: m for m in list_local_firmware(device_type)}
    if info["sha256"] in known:
        info["meta"] = known[info["sha256"]]
        info["version"] = info["meta"]["version"]
        info["official"] = True
        return data, info
    info["official"] = False
    if not 1_000_000 <= len(data) <= 200_000_000:
        info["warnings"].append(T("Unusual size ({size:.1f} MB)").format(size=len(data) / 1048576))
    generation = DEVICE_TYPES[device_type]["generation"]
    if device_type in ("Type_S", "Gen-1.5"):
        # layout of the official Gen-1 and Gen-1.5 images: 02 00 00 00 … 44 33 22 11 … '<build>_ENG_microsoft' … U-Boot
        if data[:4] != b"\x02\x00\x00\x00" or data[16:20] != b"\x44\x33\x22\x11":
            info["warnings"].append(T("Header does not match a {generation} firmware").format(generation=generation))
        m = re.search(rb"(\d{4})_ENG_microsoft", data[:8 * 1024 * 1024])
        if m:
            info["version"] = ("1.3." if device_type == "Type_S" else "2.0.") + m.group(1).decode()
        else:
            info["warnings"].append(T("No version marker found"))
        if b"U-Boot" not in data[:8 * 1024 * 1024]:
            info["warnings"].append(T("No bootloader (U-Boot) found"))
    elif device_type == "Gen-3":
        # the official Gen-3 image (install_ota.gz.Release) is a gzip archive
        if data[:2] != b"\x1f\x8b":
            info["warnings"].append(T("Header does not match a {generation} firmware").format(generation=generation))
    return data, info


def fetch_official_firmware(device_type, base_dir=None, progress=None):
    """Download the current official firmware from Microsoft into firmware/<type>/<version>/.

    Writes firmware.json (version, size, SHA-256) next to it so the GUI and the build find it.
    progress(done, total) is called during the download.
    """
    cfg = DEVICE_TYPES[device_type]
    base = Path(base_dir or FIRMWARE_CACHE) / device_type
    cloud = cloud_version(device_type)
    target = base / cloud["version"]
    data = download(cfg["firmware_url"], target / cfg["firmware_name"], cloud["size"], progress)
    meta = {"device_type": device_type, "version": cloud["version"], "release_date": cloud["date"],
            "file": cfg["firmware_name"], "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "source": cfg["firmware_url"], "downloaded": datetime.date.today().isoformat()}
    if cfg["signature_url"]:                   # Gen 3: the adapter only accepts the image with its signature
        sig = download(cfg["signature_url"], target / cfg["signature_name"])
        meta["signature"] = {"file": cfg["signature_name"], "size": len(sig),
                             "sha256": hashlib.sha256(sig).hexdigest(), "source": cfg["signature_url"]}
    (target / "version.xml").write_bytes(cloud["xml"])
    (target / "firmware.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta["_path"] = str(target / meta["file"])
    return meta


# --- Discovery -------------------------------------------------------------
def arp_candidates():
    """Peers on 192.168.x interfaces from the Windows ARP table.

    During a Miracast connection Windows adds the adapter there as a static entry,
    so it can be found immediately without scanning the whole network.
    """
    import subprocess
    try:
        out = subprocess.run(["arp", "-a"], capture_output=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    text = out.decode("cp850", errors="replace")
    found, iface = [], None
    for line in text.splitlines():
        m = re.match(r"^\S.*?:\s+(\d+\.\d+\.\d+\.\d+)\s+---", line)
        if m:
            iface = m.group(1)
            continue
        m = re.match(r"^\s+(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})", line)
        if not (m and iface and iface.startswith("192.168.")):
            continue
        ip, mac = m.group(1), m.group(2).lower()
        net = ipaddress.ip_network(iface + "/24", strict=False)
        addr = ipaddress.ip_address(ip)
        if addr in net and addr != net.broadcast_address and ip != iface and mac != "ff-ff-ff-ff-ff-ff":
            found.append(ip)
    return found


def local_wifi_direct_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
    return sorted(ip for ip in ips if ip.startswith("192.168."))


def probe(ip, use_https=None):
    a = Adapter(ip, use_https=use_https)
    try:
        if use_https is None:
            a.detect_scheme()
        return ip, a.use_https, a.get_device_name()
    except (OSError, http.client.HTTPException, AdapterError):
        return None


def discover(subnets, listen_udp, use_https=None):
    found = {}
    if listen_udp:
        print(f"Listening {listen_udp}s on UDP {UDP_HEARTBEAT_PORT} (adapter heartbeats)…")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", UDP_HEARTBEAT_PORT))
        s.settimeout(1.0)
        end = time.time() + listen_udp
        while time.time() < end:
            try:
                data, addr = s.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                hb = json.loads(data.decode("utf-8", "replace"))
                ip = hb.get("IPAddress") or addr[0]
                found[ip] = f"UDP: {hb.get('DongleName')} ({hb.get('ModelName')})"
            except json.JSONDecodeError:
                pass
        s.close()
    for ip in arp_candidates():
        res = probe(ip, use_https)
        if res:
            found[ip] = f"{res[2]} ({'HTTPS' if res[1] else 'HTTP'})"
    if found:
        return found
    targets = []
    for net in subnets:
        targets += [str(h) for h in ipaddress.ip_network(net, strict=False).hosts()]
    if targets:
        print(f"Checking {len(targets)} addresses in {', '.join(subnets)}…")
        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
            for res in ex.map(lambda ip: probe(ip, use_https), targets):
                if res:
                    ip, https, name = res
                    found[ip] = f"{name} ({'HTTPS' if https else 'HTTP'})"
    return found


# --- Firmware downloads ----------------------------------------------------
def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "wda-tool"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    host = urllib.parse.urlparse(resp.geturl()).hostname or ""
    if not (host == "microsoft.com" or host.endswith(".microsoft.com")):
        raise AdapterError(T("Redirect to unexpected host: {url}").format(url=resp.geturl()))
    return resp


def cloud_version(device_type):
    cfg = DEVICE_TYPES[device_type]
    raw = fetch(cfg["version_url"]).read()
    root = ET.fromstring(raw)
    return {
        "version": root.findtext("firmwareVersion"),
        "date": root.findtext("firmwareReleaseDate"),
        "size": int(root.findtext("firmwarePackageSize") or 0),
        "xml": raw,
    }


def _print_progress(done, total):
    print(f"\r  {done * 100 // total:3d}%  {done}/{total} bytes", end="", flush=True)


def download(url, dest, expected_size=None, progress=None):
    """progress(done, total); without it, progress is printed to the console."""
    quiet = progress is not None
    progress = progress or _print_progress
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = fetch(url, timeout=120)
    total = int(resp.headers.get("Content-Length") or 0)
    if dest.exists() and total and dest.stat().st_size == total:
        if not quiet:
            print(f"  {dest.name}: already downloaded ({total} bytes)")
        return dest.read_bytes()
    if not quiet:
        print(f"  Downloading {resp.geturl()}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    done = 0
    with open(tmp, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                progress(done, total)
    if not quiet:
        print()
    if total and done != total:
        raise AdapterError(T("Download incomplete: {done}/{total} bytes").format(done=done, total=total))
    if expected_size and done != expected_size:
        raise AdapterError(T("Size {size} does not match firmwarePackageSize {expected}").format(
            size=done, expected=expected_size))
    tmp.replace(dest)
    return dest.read_bytes()


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0"))


# --- CLI -----------------------------------------------------------------
def confirm(args, text):
    print(f"\nWRITE ACCESS to adapter {args.host}: {text}")
    if args.dry_run:
        print("(--dry-run: nothing sent)")
        return False
    if args.yes:
        return True
    return input("Continue? [y/N] ").strip().lower() in ("y", "yes", "j", "ja")


def need_host(args):
    if not args.host:
        sys.exit("Please specify --host <IP> (or run 'discover' first).")
    return Adapter(args.host, password=args.password, verbose=args.verbose)


def cmd_discover(args):
    subnets = args.subnet or [ip.rsplit(".", 1)[0] + ".0/24" for ip in local_wifi_direct_ips()]
    if not subnets and not args.udp:
        sys.exit("No 192.168.x.x interface found. Connect via Miracast (Windows + K) or use --subnet.")
    found = discover(subnets, args.udp)
    if not found:
        print("No adapter found.")
    for ip, desc in sorted(found.items()):
        print(f"  {ip:15s}  {desc}")


def cmd_info(args):
    a = need_host(args)
    version, dtype = a.retrieve_version()
    cfg = a.config
    print(f"Address:      {'https' if a.use_https else 'http'}://{a.host}")
    print(f"Device name:  {a.get_device_name()}")
    print(f"Type:         {dtype} ({cfg['generation']})")
    print(f"Firmware:     {version}")
    codes, cur = a.get_language_info()
    print(f"Language:     {cur} ({LANGUAGES.get(cur.lower(), '?')})")
    print(f"Languages:    {', '.join(codes)}")
    try:
        ov = a.get_overscan()
        print(f"Overscan:     auto={ov.get('IsAutoAdjust')} value={ov.get('OverscanSettingValue')}")
    except AdapterError as e:
        print(f"Overscan:     ({e})")
    try:
        print(f"Password protection: {a.get_password_protect()}")
    except AdapterError:
        pass


def cmd_rename(args):
    if not valid_device_name(args.name):
        sys.exit("Invalid name: 1–32 characters, only A-Z, a-z, 0-9 and _ + - ( ) [ ] { }")
    a = need_host(args)
    old = a.get_device_name()
    if not confirm(args, f"device name '{old}' -> '{args.name}'"):
        return
    r = a.set_device_name(args.name)
    print("OK." + (" Takes effect after a restart." if r.get("NeedRebootEffective") else ""))


def cmd_language(args):
    a = need_host(args)
    codes, cur = a.get_language_info()
    if not args.code:
        for c in codes:
            print(f"{'*' if c.lower() == cur.lower() else ' '} {c:7s} {LANGUAGES.get(c.lower(), '')}")
        return
    if codes and args.code.lower() not in (c.lower() for c in codes):
        sys.exit(f"The adapter does not support '{args.code}'. Available: {', '.join(codes)}")
    code = next((c for c in codes if c.lower() == args.code.lower()), args.code)
    if not confirm(args, f"display language '{cur}' -> '{code}'"):
        return
    r = a.set_language(code)
    print("OK." + (" Takes effect after a restart." if r.get("NeedRebootEffective") else ""))


def cmd_brightness(args):
    sys.exit("Brightness cannot be set: neither the app nor the adapter protocol has such a command "
             "(see docs/PROTOCOL.md). Brightness is controlled by the display. The adapter's only picture "
             "setting is 'overscan'.")


def cmd_overscan(args):
    a = need_host(args)
    cur = a.get_overscan()
    if args.value is None and not args.auto:
        print(f"auto={cur.get('IsAutoAdjust')} value={cur.get('OverscanSettingValue')}")
        return
    auto = bool(args.auto)
    value = args.value if args.value is not None else int(cur.get("OverscanSettingValue", 0))
    if not confirm(args, f"overscan -> auto={auto}, value={value}"):
        return
    a.set_overscan(auto, value)
    print("OK.")


def cmd_firmware(args):
    if args.action == "fetch":
        meta = fetch_official_firmware(args.type, args.cache)
        print(f"Saved: {args.type} {meta['version']} ({meta['size']} bytes, SHA-256 {meta['sha256']})")
        return
    a = need_host(args)
    version, dtype = a.retrieve_version()
    cfg = a.config
    meta, fw = load_local_firmware(dtype)
    if meta:
        target = meta["version"]
        print(f"Adapter:         {dtype}, firmware {version}")
        print(f"Local firmware:  {target} ({meta['file']}, SHA-256 verified)")
    else:
        cloud = cloud_version(dtype)
        target = cloud["version"]
        print(f"Adapter:    {dtype}, firmware {version}")
        print(f"Microsoft:  {target} from {cloud['date']}, {cloud['size']} bytes")
    newer = version_tuple(target) > version_tuple(version)
    print("Update available." if newer else "Adapter is up to date.")
    if args.action == "check":
        return
    if not newer and not args.force:
        print("Nothing to do (use --force to install anyway).")
        return

    if not meta:
        print("\nDownloading the official firmware:")
        meta = fetch_official_firmware(dtype, args.cache)
        print(f"  SHA-256 firmware:  {meta['sha256']}")
        if meta.get("signature"):
            print(f"  SHA-256 signature: {meta['signature']['sha256']}")
    files = firmware_parts(meta, fw)
    fw = files[0][2]

    if not confirm(args, f"install firmware {version} -> {target} ({len(fw)} bytes). "
                         "Do NOT unplug the adapter during the update."):
        return

    def show(phase, pct, text):
        print(f"\r  {text:70s}", end="", flush=True)

    run_firmware_update(a, files, show, args.timeout, log=print)
    print("\nDone. After the restart, check the version with 'info'.")


def main():
    p = argparse.ArgumentParser(description="Configure a Microsoft Wireless Display Adapter")
    p.add_argument("--host", help="IP address of the adapter")
    p.add_argument("--password", help="admin password of the adapter, if set")
    p.add_argument("--yes", action="store_true", help="write without asking")
    p.add_argument("--dry-run", action="store_true", help="only show write accesses")
    p.add_argument("-v", "--verbose", action="store_true", help="print HTTP traffic")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("discover", help="find adapters")
    s.add_argument("--subnet", action="append", help="e.g. 192.168.137.0/24 (can be repeated)")
    s.add_argument("--udp", type=int, default=0, metavar="SEC", help="also listen for UDP heartbeats")
    s.set_defaults(func=cmd_discover)

    sub.add_parser("info", help="show name, type, firmware, language").set_defaults(func=cmd_info)

    s = sub.add_parser("rename", help="rename the adapter")
    s.add_argument("name")
    s.set_defaults(func=cmd_rename)

    s = sub.add_parser("language", help="list languages or set the display language")
    s.add_argument("code", nargs="?", help="e.g. de-DE")
    s.set_defaults(func=cmd_language)

    sub.add_parser("brightness", help="(not supported, see docs/PROTOCOL.md)").set_defaults(func=cmd_brightness)

    s = sub.add_parser("overscan", help="show or set overscan")
    s.add_argument("--auto", action="store_true", help="adjust automatically")
    s.add_argument("--value", type=int, help="overscan value")
    s.set_defaults(func=cmd_overscan)

    s = sub.add_parser("firmware", help="check, update or download firmware")
    s.add_argument("action", choices=["check", "update", "fetch"],
                   help="fetch = download the official firmware from Microsoft into the 'firmware' folder")
    s.add_argument("--type", default="Gen-1.5", choices=list(DEVICE_TYPES), help="device type for 'fetch'")
    s.add_argument("--force", action="store_true", help="install even if not newer")
    s.add_argument("--cache", default=str(FIRMWARE_DIR), help="download folder")
    s.add_argument("--timeout", type=int, default=900, help="max. time to wait for the update (s)")
    s.set_defaults(func=cmd_firmware)

    args = p.parse_args()
    try:
        args.func(args)
    except AdapterError as e:
        sys.exit(f"Error: {e}")
    except KeyboardInterrupt:
        sys.exit("Cancelled.")


if __name__ == "__main__":
    main()
