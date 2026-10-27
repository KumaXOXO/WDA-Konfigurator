#!/usr/bin/env python3
"""Mock Wireless Display Adapter: ein lokaler Server, der das CGI des Adapters nachbildet.

Damit laesst sich die App ohne Hardware ausprobieren – fuer Entwicklung, Screenshots und
zum Nachstellen von Fehlern. Der Server beantwortet dieselben Action-Aufrufe wie ein echter
Adapter (siehe docs/PROTOCOL.md) und haelt die Einstellungen im Speicher.

    python tools/mock_adapter.py --type Gen-1.5 --version 2.0.8385

Danach in einer zweiten Konsole:

    python wda_tool.py --host 127.0.0.1:8099 info
    python wda_tool.py --host 127.0.0.1:8099 rename Mock-1

Die GUI sucht nur in der ARP-Tabelle und findet 127.0.0.1 daher nicht von allein;
tools/screenshots.py setzt die Suche fuer diesen Zweck um.
"""
import argparse
import json
import re
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wda_tool as wda                                            # noqa: E402

DEFAULT_PORT = 8099
# Sprachen, die ein Gen-1.5-Adapter meldet (GetLanguangeInfo, kommagetrennt)
MOCK_LANGUAGES = ("en-US,en-GB,de-DE,fr-FR,fr-CA,it-IT,es-ES,es-MX,nl-NL,da-DK,sv-SE,nb-NO,fi-FI,"
                  "pt-PT,pt-BR,pl-PL,cs-CZ,ru-RU,ja-JP,ko-KR,zh-CN,zh-TW,th-TH,ar-AE")
INSTALL_SECONDS = 20.0          # so lange "installiert" der Mock nach dem Upload


class MockAdapter:
    """Zustand eines Adapters. Alle Aenderungen gelten nur bis zum Programmende."""

    def __init__(self, device_type="Gen-1.5", version="2.0.8385", name="MicrosoftWirelessDisplay",
                 password=None, pbc="Auto", wallpaper=2, verbose=True):
        self.device_type = device_type
        self.version = version
        self.name = name
        self.password = password
        self.pbc = pbc
        self.wallpaper = wallpaper
        self.language = "en-US"
        self.overscan = {"IsAutoAdjust": "true", "OverscanSettingValue": 0}
        self.verbose = verbose
        self.upload_started_at = None
        self.lock = threading.Lock()

    # --- Hilfen ----------------------------------------------------------
    def log(self, text):
        if self.verbose:
            print(f"{time.strftime('%H:%M:%S')}  {text}", flush=True)

    def check_password(self, params):
        """Wie der echte Adapter: ohne Passwortschutz ist das Feld egal, sonst muss es passen."""
        if self.password is None:
            return None
        if params.get("AuthorizedPassword") != self.password:
            return {"ErrorCode": -4}
        return None

    def install_progress(self):
        if self.upload_started_at is None:
            return 0
        done = (time.time() - self.upload_started_at) / INSTALL_SECONDS
        return min(100, int(done * 100))

    # --- Aktionen --------------------------------------------------------
    def handle(self, action, params, body=None):
        with self.lock:
            fn = getattr(self, f"do_{action}", None)
            if fn is None:
                return {"ErrorCode": -8, "Note": f"unknown action {action}"}
            return fn(params, body) if fn.__code__.co_argcount == 3 else fn(params)

    def do_RetrieveVersion(self, params):
        out = {"Version": self.version, "ErrorCode": 0}
        if self.device_type != "Type_S":          # Gen 1 meldet kein Type-Feld
            out["Type"] = self.device_type
        return out

    def do_GetDeviceName(self, params):
        return {"DeviceName": self.name, "ErrorCode": 0}

    def do_SetDeviceName(self, params):
        err = self.check_password(params)
        if err:
            return err
        name = params.get("NewDeviceName", "")
        if not wda.valid_device_name(name):
            return {"ErrorCode": -3}
        self.name = name
        self.log(f"name -> {name}")
        return {"ErrorCode": 0}

    def do_GetLanguangeInfo(self, params):       # Schreibweise wie im Original
        return {"LanguageCode": MOCK_LANGUAGES, "CurrentLanguage": self.language, "ErrorCode": 0}

    def do_SetLanguage(self, params):
        err = self.check_password(params)
        if err:
            return err
        self.language = params.get("LanguageCode", self.language)
        self.log(f"language -> {self.language}")
        return {"ErrorCode": 0}

    def do_GetOverscanSetting(self, params):
        return {**self.overscan, "ErrorCode": 0}

    def do_SetOverscanSetting(self, params):
        err = self.check_password(params)
        if err:
            return err
        self.overscan = {"IsAutoAdjust": params.get("IsAutoAdjust", "true"),
                         "OverscanSettingValue": int(params.get("OverscanSettingValue", 0))}
        return {"ErrorCode": 0}

    def do_GetPasswordProtectState(self, params):
        return {"PasswordProtect": str(self.password is not None).lower(), "ErrorCode": 0}

    def do_SetPasswordProtect(self, params):
        want = str(params.get("State", "")).lower() == "true"
        given = params.get("AuthorizedPassword", "")
        if want:
            if not wda.PASSWORD_RE.match(given):
                return {"ErrorCode": -7}
            self.password = given
        else:
            if self.password is not None and given != self.password:
                return {"ErrorCode": -4}
            self.password = None
        self.log(f"password protection -> {want}")
        return {"ErrorCode": 0}

    def do_ChangePassword(self, params):
        if self.password is not None and params.get("OldPassword") != self.password:
            return {"ErrorCode": -6}
        if not wda.PASSWORD_RE.match(params.get("NewPassword", "")):
            return {"ErrorCode": -7}
        self.password = params["NewPassword"]
        return {"ErrorCode": 0}

    def do_VerifyAuthorizedPassword(self, params):
        ok = self.password is None or params.get("AuthorizedPassword") == self.password
        return {"VerifyResult": str(ok).lower(), "ErrorCode": 0}

    def do_GetPBCMode(self, params):
        return {"PBCModeStatus": self.pbc, "ErrorCode": 0}

    def do_SetPBCMode(self, params):
        err = self.check_password(params)
        if err:
            return err
        self.pbc = params.get("PBCModeStatus", self.pbc)
        self.log(f"PBC -> {self.pbc}")
        return {"ErrorCode": 0}

    def do_GetWallpaperID(self, params):
        return {"WallpaperID": self.wallpaper, "ErrorCode": 0}

    def do_SetPredefinedWallpaper(self, params):
        err = self.check_password(params)
        if err:
            return err
        self.wallpaper = int(params.get("WallpaperID", self.wallpaper))
        self.log(f"wallpaper -> {self.wallpaper}")
        return {"ErrorCode": 0}

    def do_UploadWallpaper(self, params, body):
        err = self.check_password(params)
        if err:
            return err
        self.wallpaper = 0                       # eigenes Bild
        self.log(f"custom wallpaper, {len(body or b'')} bytes")
        return {"ErrorCode": 0}

    def do_ResetToFactory(self, params):
        err = self.check_password(params)
        if err:
            return err
        self.name, self.language, self.password, self.wallpaper, self.pbc = (
            "MicrosoftWirelessDisplay", "en-US", None, 1, "Auto")
        self.log("reset to factory")
        return {"ErrorCode": 0}

    def do_Reboot(self, params):
        self.log("reboot")
        return {"ErrorCode": 0}

    def do_StartFirmwareUpdate(self, params):
        self.log(f"StartFirmwareUpdate (Mode={params.get('Mode')})")
        return {"ErrorCode": 0}

    def do_UploadFirmware(self, params, body):
        parts = sorted(re.findall(rb'name="([^"]+)"', body or b""))
        needs_signature = bool(wda.DEVICE_TYPES.get(self.device_type, {}).get("signature_url"))
        if needs_signature and b"signature" not in parts:
            self.log("firmware rejected: signature missing")
            return {"ErrorCode": -1}
        self.upload_started_at = time.time()
        self.log(f"firmware upload: {len(body or b'') / 1048576:.1f} MB, parts="
                 f"{[p.decode() for p in parts]}")
        return {"ErrorCode": 0}

    def do_RetrieveFirmwareUpgradeState(self, params):
        prog = self.install_progress()
        state = "Upgrading" if prog < 100 else "Done"
        if prog >= 100 and self.upload_started_at is not None:
            self.upload_started_at = None
            self.log("firmware installed")
        return {"Progress": prog, "State": state, "ErrorCode": 0}


class Handler(BaseHTTPRequestHandler):
    adapter = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass                                     # eigenes Logging im MockAdapter

    def _dispatch(self, body=None):
        url = urllib.parse.urlparse(self.path)
        if url.path != wda.CGI_PATH:
            self.send_error(404)
            return
        params = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        action = params.get("Action", "")
        payload = json.dumps(self.adapter.handle(action, params, body)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body, left = bytearray(), length
        while left > 0:                          # grosse Uploads blockweise lesen
            chunk = self.rfile.read(min(left, 1 << 20))
            if not chunk:
                break
            body += chunk
            left -= len(chunk)
        self._dispatch(bytes(body))


def serve(adapter, port=DEFAULT_PORT, background=False):
    """Server starten. background=True gibt (server, thread) zurueck, sonst laeuft er bis Strg+C."""
    handler = type("BoundHandler", (Handler,), {"adapter": adapter})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    if background:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread
    adapter.log(f"mock adapter on http://127.0.0.1:{port}{wda.CGI_PATH} "
                f"({adapter.device_type}, firmware {adapter.version})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    return server, None


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--type", default="Gen-1.5", choices=sorted(wda.DEVICE_TYPES))
    p.add_argument("--version", default="2.0.8385", help="gemeldete Firmware-Version")
    p.add_argument("--name", default="MicrosoftWirelessDisplay")
    p.add_argument("--password", help="Passwortschutz mit diesem Passwort einschalten")
    p.add_argument("--wallpaper", type=int, default=2)
    args = p.parse_args()
    serve(MockAdapter(args.type, args.version, args.name, args.password, wallpaper=args.wallpaper),
          port=args.port)


if __name__ == "__main__":
    main()
