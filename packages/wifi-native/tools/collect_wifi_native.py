#!/usr/bin/env python3
"""Collect one filtered native Wi-Fi report without SSIDs, MACs or credentials."""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import re
import subprocess


def command(arguments: list[str]) -> tuple[str, bool]:
    try:
        run = subprocess.run(arguments, capture_output=True, text=True, timeout=25,
                             env={**os.environ, "LC_ALL": "C", "LANG": "C"})
        return run.stdout, run.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return "", False


def collect() -> dict:
    version, version_ok = command(["/usr/bin/sw_vers", "-productVersion"])
    loaded, loaded_ok = command(["/usr/sbin/kextstat", "-l"])
    ports, ports_ok = command(["/usr/sbin/networksetup", "-listallhardwareports"])
    route, route_ok = command(["/sbin/route", "-n", "get", "default"])
    default = re.search(r"^\s*interface:\s*(en\d+)\s*$", route, re.M)
    interfaces = []
    for block in ports.split("\n\n"):
        if not re.search(r"Hardware Port:\s*(?:Wi-Fi|AirPort)\s*$", block, re.M):
            continue
        device = re.search(r"^Device:\s*(en\d+)\s*$", block, re.M)
        if not device:
            continue
        name = device[1]
        power, power_ok = command(["/usr/sbin/networksetup", "-getairportpower", name])
        link, link_ok = command(["/sbin/ifconfig", name])
        interfaces.append({"device": name,
                           "power_on": bool(re.search(r": On\s*$", power)) if power_ok else None,
                           "link_active": bool(re.search(r"^\s*status:\s*active\s*$", link, re.M)) if link_ok else None,
                           "default_route": default[1] == name if route_ok and default else None})
    airport = bool(re.search(r"\bcom\.zxystd\.AirportItlwm\b", loaded)) if loaded_ok else None
    ethernet = bool(re.search(r"\bcom\.zxystd\.itlwm\b", loaded)) if loaded_ok else None
    return {
        "schema": 1, "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "macos": version.strip() if version_ok else None,
        "darwin": platform.release(), "architecture": platform.machine(),
        "airportitlwm_loaded": airport, "itlwm_loaded": ethernet,
        "native_wifi_interfaces": interfaces,
        "native_interface_detected": bool(interfaces) if ports_ok else None,
        "conflicting_intel_drivers": airport and ethernet if loaded_ok else None,
        "collection_errors": [name for name, ok in (("sw_vers", version_ok), ("kextstat", loaded_ok),
                                ("hardware_ports", ports_ok), ("default_route", route_ok)) if not ok],
        "scope": "Read-only snapshot. Scanning, authentication, switching and sleep need user observations.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.exit(1, "Run this collector on the Lenovo under macOS.\n")
    # Exclusive create prevents replacing an existing report or following an output link.
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(collect(), output, indent=2)
        output.write("\n")
    print("Filtered Wi-Fi report saved.")


if __name__ == "__main__":
    main()
