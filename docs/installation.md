# Installation & Setup

This guide covers installing dependencies, configuring the team, and deploying
the tools to the vulnbox.

## Requirements

Install these on your local machine before starting:

```sh
# sshpass is required by Ansible for password auth
sudo pacman -S sshpass   # Arch
# sudo apt install sshpass  # Debian/Ubuntu

# Create the Python venv inside ADTools and install dependencies
# (requests is needed by the exploit farm, push_services.py and deploy_parallel.py)
python3 -m venv .venv
.venv/bin/pip install ansible passlib requests

# Install required Ansible collections
.venv/bin/ansible-galaxy collection install community.docker ansible.posix
```

> All the local scripts (`deploy_parallel.py`, `push_services.py`,
> `patch_service.py`, `exploits/start_sploit.py`) must be run with the venv
> interpreter `.venv/bin/python`, not the system `python3` — that is where
> `requests` and `ansible` live.

A Linux host is assumed (it can probably be launched from Windows too, but this is untested).

---

## Team Configuration

Values from the competition portal go into `.env.json` (created in step 2).

| Field | Value |
|---|---|
| Team ID | <team id> |
| Vulnbox IP | <vulnbox_ip> |
| Initial VM password | `******` |
| Team token | `***` |
| Game interface | `game` (check with `ip link` on vulnbox — **not** what the portal says) |
| Gameserver URL | `http://10.10.0.1:8080/flags` |
| Number of teams | 85 |
| Team IP format | `10.60.{i}.1` |

---

## Step-by-Step Setup

### 0. Add SSH keys (optional but recommended)

Each team member should generate a key pair and add their public key to `ssh_keys`:

```sh
ssh-keygen -t ed25519 -C "yourname" -f ~/.ssh/vulnbox_ed25519 -N ""
cat ~/.ssh/vulnbox_ed25519.pub >> ssh_keys
```

### 1. Add the vulnbox to /etc/hosts

```sh
sudo bash hosts.sh <vulnbox_ip> 10.60.0.1
```

This makes Ansible resolve the hostname `vulnbox` correctly. The NOP team is `10.60.0.1`.

### 2. Create .env.json

`.env.json` is the single source of truth: connection target, GitHub identities,
team config, and generated secrets. Copy the committed template and fill in your
values:

```sh
cp env.json.example .env.json
chmod 600 .env.json
$EDITOR .env.json
```

Field reference:

| Field | Fill with |
|---|---|
| `vulnbox_ip` | Vulnbox IPv4 |
| `gameserver_url` | Flag submission URL (must start with `http://`) |
| `team_token` | Team token from the competition portal |
| `number_of_teams` | Team count |
| `teams_format` | Python f-string for team IPs, **must** keep the `f'...'` wrapper and contain `{i}` |
| `game_interface` | Game NIC on the vulnbox (`ip link` — not what the portal says) |
| `github_org` / `github_token` | Org + token with **push** access — used to publish the vulnbox services |
| `tool_repos_org` / `tool_repos_token` | Org + token with **read** access — used to clone the tool repos |
| `exploit_vm_endpoint` / `exploit_vm_pubkey` / `vulnbox_privkey` | WireGuard (leave blank until the VPS is ready) |

Leave the **secret** fields (`root_password`, `packmate_password`,
`ctffarm_password`, `flag_dashboard_key`, `flag_dashboard_password`) blank:
`deploy_parallel.py` auto-generates any missing secret on first run, writes it
back into `.env.json` (mode 0600), and patches the `--server-pass` line of
`exploits/run_exploit.sh` with the generated `ctffarm_password`.

> **Note:** `.env.json` is gitignored and holds all secrets. Keep it safe and never commit it.

### 3. Deploy

Run all modules in the correct order (common → parallel → kickstarterpy):

```sh
.venv/bin/python deploy_parallel.py \
  --vulnbox-password **** \
  --modules common kickstarterpy s4dfarm packmate dashboard
```

To deploy only specific modules (e.g., after a partial failure or to redeploy a single tool):

```sh
# After common has already run, use the NEW root password from .env.json
.venv/bin/python deploy_parallel.py \
  --vulnbox-password $(.venv/bin/python -c "import json; print(json.load(open('.env.json'))['root_password'])") \
  --modules packmate dashboard
```

> **Important:** `common` changes the root password to the generated `root_password` in `.env.json`. All subsequent deploys must use that new password, not the original VM password.

> **Publishing the services:** when the deploy finishes, `deploy_parallel.py`
> scans `/root` on the vulnbox, lists the service folders it finds (everything
> that is not a deployed tool), and asks for confirmation before pushing each
> one as a **private** repository to `github_org` using `github_token`. Answer
> `y` to push, anything else to skip. Pass `--skip-push` to disable this step,
> or run it on its own at any time:
>
> ```sh
> .venv/bin/python push_services.py
> ```

### 4. Deploy wisscon (when VPS is ready)

Fill in the VPN fields in `.env.json`:

```json
"exploit_vm_endpoint": "VPS_IP:51820",
"exploit_vm_pubkey": "PUBLIC_KEY_FROM_VPS",
"vulnbox_privkey": "PRIVATE_KEY_FROM_VULNBOX_WIREGUARD_CONF"
```

The wireguard private key is on the vulnbox at `/etc/wireguard/wg0.conf` (or similar). Then:

```sh
.venv/bin/python deploy_parallel.py \
  --vulnbox-password $(.venv/bin/python -c "import json; print(json.load(open('.env.json'))['root_password'])") \
  --modules wisscon threesome
```

---

## Patching Running Services

Once `push_services.py` has snapshotted each service into a git repo on the
vulnbox, `patch_service.py` uses that git history to apply fixes with one-step
rollback. Every applied patch is a commit, so reverting is just moving the ref —
no manual backups. After each change it rebuilds the service's docker stack
(`docker compose up -d --build`, run from the service root).

```sh
# Apply a unified diff and rebuild
.venv/bin/python patch_service.py apply <service> ./fix.diff -m "patch sqli in login"

# Or commit changes you already made directly on the box (no diff file)
.venv/bin/python patch_service.py apply <service>

# Show the patch history
.venv/bin/python patch_service.py log <service>

# Roll back the last patch (default HEAD~1) and rebuild
.venv/bin/python patch_service.py rollback <service>

# Roll back to a specific commit
.venv/bin/python patch_service.py rollback <service> --to <commit>

# Just rebuild the stack
.venv/bin/python patch_service.py restart <service>
```

Pass `--no-restart` to `apply`/`rollback` to skip the docker rebuild. Connection
(`vulnbox` host + `root_password`) is read from `.env.json`, same as
`push_services.py`.

---

## What Each Module Does

| Module | Tool | Port | Description |
|---|---|---|---|
| `common` | — | — | Installs Docker, adds SSH keys, changes root password |
| `s4dfarm` | S4DFarm | `127.0.0.1:42069` | Flag submission farm (web UI + celery workers) |
| `packmate` | Packmate | `65000` | Traffic capture and analysis (pcap viewer) |
| `kickstarterpy` | KickStarterPy | — | Automates pushing flag patterns to Packmate |
| `dashboard` | flag_dashboard | — | Unified web dashboard aggregating s4dfarm + packmate |
| `wisscon` | wisscon + WireGuard | — | Site-to-site VPN between vulnbox and exploit VM |
| `threesome` | threesome | — | TCP proxy that intercepts service traffic and runs Python filter modules to block attacks |
| `git_deploy` | KickStarterPy | — | Sets up git push–based exploit deployment |

---

## Services After Deployment

| Service | URL | Credentials |
|---|---|---|
| S4DFarm | `http://<vulnbox_ip>:42069` | password: `ctffarm_password` in `.env.json` |
| Packmate | `http://<vulnbox_ip>:65000` | login: `unimore` / password: `packmate_password` in `.env.json` |
| flag_dashboard | `http://<vulnbox_ip>` (default Flask port) | password: `flag_dashboard_password` in `.env.json` |
