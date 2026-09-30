# net-inventory-healthchecks

Every NOC shift starts with the same question: **"what's broken right now?"**
This repo answers it in one run — a Python health checker that inventories
your lab devices and tests reachability, DNS resolution, and key TCP ports,
plus an Ansible playbook that backs up running configs before you touch
anything.

## What it checks

- **ICMP reachability** — is the device answering ping?
- **DNS resolution** — does the hostname actually resolve?
- **TCP ports** — are the key service ports (SSH, HTTPS, syslog) open?
- **Config backups** — timestamped `show running-config` snapshots via Ansible,
  so a bad change is always reversible.

## Quickstart

```bash
pip install -r requirements.txt
cp devices.yaml.example devices.yaml   # fill in YOUR lab devices
python3 inventory.py                    # real run
python3 inventory.py --dry-run          # simulate, touches no network
```

Exit codes: `0` = all healthy, `1` = something failed, `2` = inventory error.
Every run writes a timestamped report to `reports/`.

## Sample report output

*(SAMPLE — generated with `--dry-run` against the example inventory)*

```markdown
# Network Health Check Report

Generated: 2026-09-30 17:20:00 (UTC)
Mode: DRY-RUN (simulated results)
Devices checked: 4

## core-switch-lab (192.0.2.11) — HEALTHY

- ICMP ping: **PASS** — SIMULATED: 1/1 replies
- DNS: **PASS** — SIMULATED: resolves to 192.0.2.99
- TCP/22: **PASS** — SIMULATED: open
- TCP/443: **PASS** — SIMULATED: open

**Summary: 4/4 devices healthy.**
```

## Scope

**Lab devices and documentation IPs only.** The example inventory uses
RFC 5737 reserved ranges (`192.0.2.0/24`, `203.0.113.0/24`) that can never
be real hosts. Your real `devices.yaml` stays on your machine — it is
git-ignored and never committed. **Real credentials are never committed** —
see `docs/shift-use.md` for safe credential practices (environment
variables / ansible-vault, never hardcoded).

## How a shift uses this

See [`docs/shift-use.md`](docs/shift-use.md): pre-shift health check,
post-change verification with diff, and Ansible config backups.

## Keywords

network automation, Python, Ansible, health checks, inventory, NOC tooling,
ICMP monitoring, DNS validation, TCP port checks, config backup
