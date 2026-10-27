#!/usr/bin/env python3
"""Miracast diagnostics: records a connection attempt with a Wireless Display Adapter.

Every 0.25 s: peer in the ARP table, TCP connections into the Miracast network (RTSP = 7236),
HTTP reachability of the adapter. Afterwards the Windows WLAN events are merged in.
Read-only – nothing is changed on the adapter.

Usage:  python wda_diag.py [seconds]      (default: 300)
"""
import datetime
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import wda_tool as wda

NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
events = []
lock = threading.Lock()


def log(text):
    t = datetime.datetime.now()
    with lock:
        events.append((t, text))
    print(f"{t:%H:%M:%S.%f}"[:-3] + "  " + text, flush=True)


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=10, creationflags=NOWIN).stdout.decode(
            "cp850", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return ""


def tcp_connections(prefix):
    """{(local, remote): state} for connections into the 192.168.x Miracast network."""
    out = {}
    for line in run(["netstat", "-ano", "-p", "tcp"]).splitlines():
        p = line.split()
        if len(p) >= 4 and p[0] == "TCP" and (p[1].startswith(prefix) or p[2].startswith(prefix)):
            out[(p[1], p[2])] = p[3]
    return out


def station_info():
    txt = run(["netsh", "wlan", "show", "interfaces"])
    ssid = re.search(r"^\s*SSID\s*:\s*(.+)$", txt, re.M)
    chan = re.search(r"^\s*(?:Kanal|Channel)\s*:\s*(\d+)", txt, re.M)
    state = re.search(r"^\s*(?:Status|State)\s*:\s*(.+)$", txt, re.M)
    return (state.group(1).strip() if state else "?", ssid.group(1).strip() if ssid else "-",
            chan.group(1) if chan else "-")


def probe_adapter(ip, stop):
    """Query the adapter repeatedly (read-only) while it is there."""
    a = wda.Adapter(ip, use_https=False)
    first = True
    fails = 0
    while not stop.is_set():
        t0 = time.time()
        try:
            if first:
                v, typ = a.retrieve_version()
                log(f"HTTP  adapter {ip}: {a.get_device_name()}, {typ}, firmware {v}  "
                    f"({(time.time() - t0) * 1000:.0f} ms)")
                first = False
            else:
                a.get_device_name()
                if fails:
                    log(f"HTTP  adapter {ip} responds again")
            fails = 0
        except Exception as e:
            fails += 1
            if fails in (1, 5):
                log(f"HTTP  adapter {ip} does not respond ({type(e).__name__})")
        stop.wait(1.0)


def wlan_events(since):
    ps = ("Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-WLAN-AutoConfig/Operational';"
          f"StartTime=[datetime]'{since:%Y-%m-%d %H:%M:%S}'}} -ErrorAction SilentlyContinue | Sort-Object TimeCreated | "
          "ForEach-Object { $_.TimeCreated.ToString('HH:mm:ss.fff') + '|' + $_.Id + '|' + "
          "(($_.Message -split \"`n\" | Where-Object { $_ -match 'SSID:|Peer-MAC|Ursache|Reason|Grund' } | "
          "ForEach-Object { $_.Trim() }) -join '; ') }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=60,
                         creationflags=NOWIN).stdout.decode("utf-8", errors="replace")
    names = {8005: "Wi-Fi Direct group starting", 8006: "group started", 20019: "adapter associated",
             20020: "adapter authenticated", 8008: "group stopping", 8003: "disconnected",
             8000: "WLAN connecting", 8001: "WLAN connected", 11004: "security stopped"}
    res = []
    for line in out.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3 and parts[1].isdigit() and int(parts[1]) in names:
            res.append((parts[0], f"WLAN  [{parts[1]}] {names[int(parts[1])]}  {parts[2]}"))
    return res


def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    start = datetime.datetime.now()
    state, ssid, chan = station_info()
    log(f"Start. PC WLAN: {state}, SSID {ssid}, channel {chan}. Recording {duration} s – connect now with "
        f"Windows logo key + K.")
    known_ips, conns, probes = set(), {}, {}
    end = time.time() + duration
    last_station = (state, ssid, chan)
    tick = 0
    while time.time() < end:
        ips = set(wda.arp_candidates())
        for ip in ips - known_ips:
            log(f"ARP   peer {ip} appears (Wi-Fi Direct connected)")
            stop = threading.Event()
            threading.Thread(target=probe_adapter, args=(ip, stop), daemon=True).start()
            probes[ip] = stop
        for ip in known_ips - ips:
            log(f"ARP   peer {ip} disappears (Wi-Fi Direct disconnected)")
            probes.pop(ip).set()
        known_ips = ips
        now = tcp_connections("192.168.")
        for k, st in now.items():
            if conns.get(k) != st and ("7236" in k[0] or "7236" in k[1] or st == "ESTABLISHED"):
                tag = "RTSP" if (":7236" in k[0] or ":7236" in k[1]) else "TCP "
                log(f"{tag}  {k[0]} -> {k[1]}  {st}")
        for k in set(conns) - set(now):
            if ":7236" in k[0] or ":7236" in k[1]:
                log(f"RTSP  {k[0]} -> {k[1]}  closed")
        conns = now
        tick += 1
        if tick % 8 == 0:
            cur = station_info()
            if cur != last_station:
                log(f"PC WLAN now: {cur[0]}, SSID {cur[1]}, channel {cur[2]}")
                last_station = cur
        time.sleep(0.25)
    for stop in probes.values():
        stop.set()
    log("End of recording")

    merged = [(f"{t:%H:%M:%S.%f}"[:-3], txt) for t, txt in events] + wlan_events(start)
    merged.sort(key=lambda x: x[0])
    out = Path(__file__).resolve().parent / f"diagnose-{start:%Y%m%d-%H%M%S}.txt"
    out.write_text("\n".join(f"{t}  {txt}" for t, txt in merged), encoding="utf-8")
    print(f"\nTimeline saved: {out}")


if __name__ == "__main__":
    main()
