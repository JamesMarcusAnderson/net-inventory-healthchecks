# Using This During a Shift

This repo is built for one job: answering **"what's broken right now?"**
at the start of a shift, and **"did my change break anything?"** after one.

## Pre-shift health check (5 minutes)

```bash
pip install -r requirements.txt
cp devices.yaml.example devices.yaml   # once; fill in your LAB devices
python3 inventory.py
```

- Exit code `0` = everything healthy. Exit code `1` = something failed —
  the report names it. Exit code `2` = your inventory file has a problem.
- Every run writes a timestamped report to `reports/healthcheck-<UTC>.md`.
  Keep the one from shift start; it is your baseline if something goes
  sideways later.

## Post-change verification

Made a config change or bounced a device? Re-run and diff:

```bash
python3 inventory.py
diff reports/healthcheck-<before>.md reports/healthcheck-<after>.md
```

If the only deltas are the device you touched, you are clean.

## Config backups with Ansible

```bash
ansible-galaxy collection install cisco.ios   # once
export ANSIBLE_NET_USER='your-lab-user'
export ANSIBLE_NET_PASSWORD='your-lab-password'   # or use --ask-pass
ansible-playbook backup-configs.yml --check       # dry run first
ansible-playbook backup-configs.yml -i lab-inventory.ini
```

Backups land in `backups/<hostname>-<UTC>.cfg` with `0600` permissions.
`backups/` is git-ignored — configs never belong in version control.

## Safe credential management (non-negotiable)

1. **Never hardcode credentials.** Not in scripts, not in playbooks,
   not in inventory files, not in commit messages.
2. **Environment variables or vault.** This repo reads
   `ANSIBLE_NET_USER` / `ANSIBLE_NET_PASSWORD` from the environment.
   For anything shared or scheduled, use `ansible-vault` instead and keep
   the vault password out of the repo.
3. **`.gitignore` is your seatbelt.** `devices.yaml` (real inventory),
   `reports/`, `backups/`, `.env`, and `*.vault-password` files are all
   ignored. If a secret ever lands in a commit, rotate it — rewriting
   history does not un-leak it.
4. **Lab scope only.** The example inventory uses RFC 5737 documentation
   addresses (`192.0.2.0/24`, `203.0.113.0/24`) that cannot be real hosts.
   Your real `devices.yaml` stays on your machine, never in git.
