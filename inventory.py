#!/usr/bin/env python3
"""net-inventory-healthchecks / inventory.py

Pre-shift network health checker for a NOC lab.

Reads a YAML inventory of lab devices and, for each device, checks:
  1. ICMP reachability (ping)
  2. DNS resolution of the device's hostname
  3. TCP connectivity on each listed key port
Then writes a timestamped Markdown report.

Usage:
    pip install -r requirements.txt
    cp devices.yaml.example devices.yaml   # then edit with YOUR LAB devices
    python3 inventory.py                     # real run
    python3 inventory.py --dry-run           # simulate, no network touched
    python3 inventory.py --lab               # same as a real run; documents intent

Exit codes: 0 = all devices healthy, 1 = one or more checks failed,
            2 = inventory/usage error.

Only the Python standard library plus PyYAML is required.
"""

import argparse
import datetime as dt
import os
import shutil
import socket
import subprocess
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - handled with a clear message
    sys.stderr.write(
        "ERROR: PyYAML is required. Install it with:\n"
        "    pip install -r requirements.txt\n"
    )
    sys.exit(2)

DEFAULT_INVENTORY = "devices.yaml"
DEFAULT_OUTDIR = "reports"
PING_BIN = shutil.which("ping")


def check_ping(host, timeout):
    """Return (ok: bool, detail: str). Never raises."""
    if PING_BIN is None:
        return False, "ping binary not found on this host"
    try:
        proc = subprocess.run(
            [PING_BIN, "-c", "1", "-W", str(timeout), host],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
        if proc.returncode == 0:
            return True, "1/1 replies"
        return False, "no reply (packet loss or host down)"
    except subprocess.TimeoutExpired:
        return False, "ping timed out"
    except OSError as exc:  # e.g. permission problems with raw sockets
        return False, f"ping failed to run: {exc}"


def check_dns(name, timeout):
    """Return (ok: bool, detail: str). Never raises."""
    if not name:
        return None, "skipped (no dns_name in inventory)"
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        infos = socket.getaddrinfo(name, None, family=socket.AF_UNSPEC)
        addrs = sorted({info[4][0] for info in infos})
        return True, "resolves to " + ", ".join(addrs)
    except socket.gaierror as exc:
        return False, f"DNS resolution failed: {exc}"
    except (socket.timeout, OSError) as exc:
        return False, f"DNS lookup error: {exc}"
    finally:
        socket.setdefaulttimeout(old_timeout)


def check_tcp(host, port, timeout):
    """Return (ok: bool, detail: str). Never raises."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "open"
    except socket.timeout:
        return False, "timed out (filtered or host not answering)"
    except ConnectionRefusedError:
        return False, "connection refused"
    except socket.gaierror as exc:
        return False, f"DNS failure for TCP check: {exc}"
    except OSError as exc:
        return False, f"unreachable: {exc}"


def simulate_device(device):
    """Deterministic fake results for --dry-run. Clearly labeled."""
    results = {
        "ping": (True, "SIMULATED: 1/1 replies"),
        "dns": (True, "SIMULATED: resolves to 192.0.2.99"),
        "ports": {p: (True, "SIMULATED: open") for p in device.get("ports", [])},
    }
    return results


def check_device(device, timeout, dry_run):
    """Run all checks for one device. Returns a dict of results."""
    if dry_run:
        return simulate_device(device)

    host = device["host"]
    results = {
        "ping": check_ping(host, timeout),
        "dns": check_dns(device.get("dns_name"), timeout),
        "ports": {},
    }
    for port in device.get("ports", []):
        try:
            port_num = int(port)
        except (TypeError, ValueError):
            results["ports"][port] = (False, f"invalid port value: {port!r}")
            continue
        results["ports"][port_num] = check_tcp(host, port_num, timeout)
    return results


def device_healthy(results):
    """A device is healthy only if every non-skipped check passed."""
    checks = [results["ping"], results["dns"]]
    checks.extend(results["ports"].values())
    for ok, _detail in checks:
        if ok is None:  # skipped
            continue
        if not ok:
            return False
    return True


def load_inventory(path):
    """Load and validate the inventory file. Raises on problems."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"inventory file not found: {path}\n"
            "Copy the example and edit it for your lab:\n"
            "    cp devices.yaml.example devices.yaml"
        )
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "devices" not in data:
        raise ValueError(f"{path}: expected top-level mapping with a 'devices' list")
    devices = data["devices"]
    if not isinstance(devices, list) or not devices:
        raise ValueError(f"{path}: 'devices' must be a non-empty list")
    for i, dev in enumerate(devices):
        if not isinstance(dev, dict) or "name" not in dev or "host" not in dev:
            raise ValueError(
                f"{path}: devices[{i}] must be a mapping with at least "
                "'name' and 'host'"
            )
    return devices


def fmt(ok):
    if ok is None:
        return "SKIP"
    return "PASS" if ok else "FAIL"


def render_report(devices, all_results, when, dry_run):
    """Build the Markdown report text."""
    lines = [
        "# Network Health Check Report",
        "",
        f"Generated: {when} (UTC)",
        f"Mode: {'DRY-RUN (simulated results)' if dry_run else 'live'}",
        f"Devices checked: {len(devices)}",
        "",
    ]
    healthy = 0
    for device, results in zip(devices, all_results):
        ok = device_healthy(results)
        healthy += ok
        status = "HEALTHY" if ok else "DEGRADED"
        lines.append(f"## {device['name']} ({device['host']}) — {status}")
        lines.append("")
        ok_ping, detail_ping = results["ping"]
        lines.append(f"- ICMP ping: **{fmt(ok_ping)}** — {detail_ping}")
        ok_dns, detail_dns = results["dns"]
        lines.append(f"- DNS: **{fmt(ok_dns)}** — {detail_dns}")
        for port, (ok_port, detail_port) in results["ports"].items():
            lines.append(f"- TCP/{port}: **{fmt(ok_port)}** — {detail_port}")
        lines.append("")
    lines.append(f"**Summary: {healthy}/{len(devices)} devices healthy.**")
    if healthy != len(devices):
        lines.append("Investigate every FAIL before signing off on the shift.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check reachability, DNS, and key ports for lab devices "
                    "in a YAML inventory, and write a timestamped report."
    )
    parser.add_argument(
        "-i", "--inventory", default=DEFAULT_INVENTORY,
        help=f"inventory YAML file (default: {DEFAULT_INVENTORY})",
    )
    parser.add_argument(
        "-o", "--output-dir", default=DEFAULT_OUTDIR,
        help=f"where to write reports (default: {DEFAULT_OUTDIR})",
    )
    parser.add_argument(
        "-t", "--timeout", type=int, default=3,
        help="per-check timeout in seconds (default: 3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="simulate results without touching the network",
    )
    parser.add_argument(
        "--lab", action="store_true",
        help="explicitly mark this run as lab-scoped (documentation aid; "
             "same behavior as a normal run)",
    )
    args = parser.parse_args(argv)

    if args.timeout < 1 or args.timeout > 30:
        sys.stderr.write("ERROR: --timeout must be between 1 and 30 seconds\n")
        return 2

    try:
        devices = load_inventory(args.inventory)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2

    all_results = [check_device(d, args.timeout, args.dry_run) for d in devices]
    when = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    report = render_report(devices, all_results, when, args.dry_run)

    os.makedirs(args.output_dir, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = os.path.join(args.output_dir, f"healthcheck-{stamp}.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")

    print(report)
    print(f"\nReport written to {report_path}")

    any_failed = any(not device_healthy(r) for r in all_results)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
