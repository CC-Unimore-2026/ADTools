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
| `exploit_vm_endpoint` / `exploit_vm_pubkey` / `vulnbox_privkey` | WireGuard — leave blank until the VPS is ready, then fill from `exploit_vm_setup.sh` output (see §4) |

Leave the **secret** fields (`root_password`, `packmate_password`,
`ctffarm_password`, `flag_dashboard_key`, `flag_dashboard_password`) blank:
`deploy_parallel.py` auto-generates any missing secret on first run, writes it
back into `.env.json` (mode 0600), and patches the `--server-pass` line of
`exploits/run_exploit.sh` with the generated `ctffarm_password`. `tick_start`
is also auto-generated with the current UTC time if left empty.

> **Note:** `.env.json` is gitignored and holds all secrets. Keep it safe and never commit it.

### 3. Deploy

Run all modules in the correct order (common → parallel → kickstarterpy):

```sh
.venv/bin/python deploy_parallel.py \
  --vulnbox-password **** \
  --modules common kickstarterpy s4dfarm tulip dashboard
```

To deploy only specific modules (e.g., after a partial failure or to redeploy a single tool):

```sh
# After common has already run, use the NEW root password from .env.json
.venv/bin/python deploy_parallel.py \
  --vulnbox-password $(.venv/bin/python -c "import json; print(json.load(open('.env.json'))['root_password'])") \
  --modules tulip dashboard
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

wisscon is a site-to-site WireGuard tunnel between the vulnbox and a separate
**exploit VM** (VPS): the exploit VM is the WireGuard *server*, the vulnbox is
the *client* that NATs the tunnel out its `game_interface` so the exploit VM can
reach every team at `10.60.{i}.1`. Set up the two sides in order.

**a) Exploit VM (server).** Copy `exploit_vm_setup.sh` to the VPS and run it
there as root. It installs WireGuard, generates *both* key pairs, brings up the
tunnel (persisted across reboot), opens the firewall, and prints the three
values you need next:

```sh
scp exploit_vm_setup.sh <vps>:
ssh <vps> 'sudo ./exploit_vm_setup.sh'          # defaults: port 51820, gamenet 10.60.0.0/16
# override:  sudo ./exploit_vm_setup.sh <port> <gamenet>
# force endpoint IP:  sudo PUBLIC_IP=1.2.3.4 ./exploit_vm_setup.sh
```

The script embeds wisscon's exact server config (tunnel `192.168.200.0/24`), so
no GitHub token is needed on the VPS. It is idempotent — re-running rebuilds the
tunnel with fresh keys (re-paste the new values below).

**b) Vulnbox (client).** Paste the three values the script printed into
`.env.json`:

```json
"exploit_vm_endpoint": "VPS_IP:51820",
"exploit_vm_pubkey": "PUBLIC_KEY_FROM_VPS",
"vulnbox_privkey": "PRIVATE_KEY_FROM_VPS_SCRIPT"
```

If the VPS is reachable over IPv6, the endpoint **must** bracket the address:
`"[2a01:4f8:c17:7cce::1]:51820"`. The setup script already prints it in the
correct form — copy it verbatim.

Then deploy the vulnbox side (the `wisscon` module runs
`client-wg-config.sh`, which NATs `192.168.200.0/24` out the `game_interface`):

```sh
.venv/bin/python deploy_parallel.py \
  --vulnbox-password $(.venv/bin/python -c "import json; print(json.load(open('.env.json'))['root_password'])") \
  --modules wisscon threesome
```

Verify: `wg show` on both ends should list the peer with a recent handshake, and
from the exploit VM `ping 10.60.0.1` (the NOP team) should reply.

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
| `tulip` | Tulip | `65002` | Pcap flow analysis, flag extraction, and codegen (HTTP/TLS/WebSocket support) |
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
| Tulip | `http://<vulnbox_ip>:65002` | — (no built-in auth; use VPN or reverse proxy) |
| flag_dashboard | `http://<vulnbox_ip>` (default Flask port) | password: `flag_dashboard_password` in `.env.json` |
