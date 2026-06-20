# ADTools Setup Guide — CyberChallenge.IT A&D

## Requirements

Install these on your local machine before starting:

```sh
# sshpass is required by Ansible for password auth
sudo pacman -S sshpass   # Arch
# sudo apt install sshpass  # Debian/Ubuntu

# Create the Python venv inside ADTools and install dependencies
python3 -m venv .venv
.venv/bin/pip install ansible passlib

# Install required Ansible collections
.venv/bin/ansible-galaxy collection install community.docker ansible.posix
```

---

## Team Configuration

Values from the competition portal go into `.env.json` (generated in step 3).

| Field | Value |
|---|---|
| Team ID | 39 |
| Vulnbox IP | 10.60.39.1 |
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
sudo bash hosts.sh 10.60.39.1 10.60.0.1
```

This makes Ansible resolve the hostname `vulnbox` correctly. The NOP team is `10.60.0.1`.

### 2. Generate .env.json

Run the interactive script and fill in all prompts:

```sh
python3 gen_env.py
```

Or create it directly (adjust values as needed):

```sh
python3 - <<'EOF'
import json, os, secrets

env = {
    'base_path': '/root/',
    'vulnbox_ip': '10.60.39.1',
    'gameserver_url': 'http://10.10.0.1:8080/flags',
    'team_token': '****',
    'number_of_teams': 85,
    'teams_format': "f'10.60.{i}.1'",
    'game_interface': 'game',
    'root_password': secrets.token_hex(32),
    'packmate_password': secrets.token_hex(32),
    'ctffarm_password': secrets.token_hex(32),
    'flag_dashboard_key': secrets.token_hex(32),
    'flag_dashboard_password': secrets.token_urlsafe(12),
    'exploit_vm_endpoint': '',   # fill when VPS is available
    'exploit_vm_pubkey': '',
    'vulnbox_privkey': '',
}

with open('.env.json', 'w') as f:
    json.dump(env, f, indent=4)
os.chmod('.env.json', 0o600)

with open('run_exploit.sh', 'r') as f:
    lines = f.readlines()
lines[2] = f'\t--server-pass {env["ctffarm_password"]} \\\n'
with open('run_exploit.sh', 'w') as f:
    f.writelines(lines)
EOF
```

> **Note:** `.env.json` contains all generated secrets (passwords, keys). Keep it safe and never commit it.

### 3. Deploy

Run all modules in the correct order (common → parallel → kickstarterpy):

```sh
python3 deploy_parallel.py \
  --vulnbox-password **** \
  --modules common kickstarterpy s4dfarm packmate dashboard
```

To deploy only specific modules (e.g., after a partial failure or to redeploy a single tool):

```sh
# After common has already run, use the NEW root password from .env.json
python3 deploy_parallel.py \
  --vulnbox-password $(python3 -c "import json; print(json.load(open('.env.json'))['root_password'])") \
  --modules packmate dashboard
```

> **Important:** `common` changes the root password to the generated `root_password` in `.env.json`. All subsequent deploys must use that new password, not the original VM password.

### 4. Deploy wisscon (when VPS is ready)

Fill in the VPN fields in `.env.json`:

```json
"exploit_vm_endpoint": "VPS_IP:51820",
"exploit_vm_pubkey": "PUBLIC_KEY_FROM_VPS",
"vulnbox_privkey": "PRIVATE_KEY_FROM_VULNBOX_WIREGUARD_CONF"
```

The wireguard private key is on the vulnbox at `/etc/wireguard/wg0.conf` (or similar). Then:

```sh
python3 deploy_parallel.py \
  --vulnbox-password $(python3 -c "import json; print(json.load(open('.env.json'))['root_password'])") \
  --modules wisscon threesome
```

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
| S4DFarm | `http://10.60.39.1:42069` | password: `ctffarm_password` in `.env.json` |
| Packmate | `http://10.60.39.1:65000` | login: `unimore` / password: `packmate_password` in `.env.json` |
| flag_dashboard | `http://10.60.39.1` (default Flask port) | password: `flag_dashboard_password` in `.env.json` |

---

## Known Bugs Fixed During Setup

| File | Bug | Fix |
|---|---|---|
| `deploy_parallel.py` | Hardcoded `"root"` as initial SSH password | Added `--vulnbox-password` CLI argument |
| `deploy_parallel.py` | Used system `ansible-playbook` (not installed) | Changed to `.venv/bin/ansible-playbook` |
| `configs/flag_dashboard.template.env` | Key was `S4DFARM_API_TOKEN` but task searched for `S4DFARM_PASSWORD` | Renamed key to match |
| `tasks/kickstarterpy.yml` | Flag regex `[A-Za-z0-9]{31}=` (allowed lowercase) | Fixed to `[A-Z0-9]{31}=` |
| `tasks/kickstarterpy.yml` | pip blocked by PEP 668 (Ubuntu 24.04) | Added `extra_args: --break-system-packages` |
| `tasks/kickstarterpy.yml` | `packmate_config.py` ran before packmate was ready | Added `wait_for` task on port 65000 |
| `tasks/dashboard.yml` | pip couldn't uninstall debian's `blinker` to upgrade it | Switched to a per-project venv (`/root/flag_dashboard/.venv`) |
| `tasks/dashboard.yml` | `python3-venv` not installed on vulnbox | Added `apt install python3.12-venv` task |
| `.env.json` / packmate | `game_interface` set to `player000` (wrong) | Corrected to `game` (actual interface name on vulnbox) |

> **Tip:** Always check the actual interface name with `ip link show` on the vulnbox — competition portals sometimes list the WireGuard peer name, not the Linux interface name.

---

## Adding Filters to Threesome

Threesome is a **TCP proxy**: it sits in front of your services and intercepts every connection. For each configured service it generates two Python filter modules — `_in` (attacker → your service) and `_out` (your service → attacker). You write Python functions in those modules to detect and block attacks. No restart needed — modules are **hot-reloaded** whenever you save the file.

### Step 1 — Configure which services to proxy

Edit `/root/threesome/proxy/config/config.json` on the vulnbox. Add one entry per service:

```json
{
    "services": [
        {
            "name": "myservice",
            "port": 8080
        },
        {
            "name": "http_service",
            "port": 80,
            "http": true
        },
        {
            "name": "https_service",
            "port": 443,
            "http": true,
            "ssl": {
                "server_certificate": "server.pem",
                "server_key": "server.pem"
            }
        }
    ],
    "global_config": {
        "keyword": "UNIMORE",
        "verbose": false,
        "interface": "game",
        "dos": {
            "enabled": true,
            "duration": 60,
            "interval": 2
        },
        "max_stored_messages": 10,
        "max_message_size": 65535
    }
}
```

**Key `global_config` options:**
- `keyword` — string sent back to attackers when a packet is blocked (useful for finding attacks in Packmate)
- `interface` — the game network interface (`game` on this vulnbox)
- `dos.enabled` — when `true`, keeps the attacker's socket alive for `duration` seconds instead of closing it immediately, wasting their time

### Step 2 — Run the proxy (first time)

On first run, threesome auto-generates two module files per service inside `proxy/filter_modules/<service_name>/`:
- `<service_name>_in.py` — filters inbound traffic (attacker → service)
- `<service_name>_out.py` — filters outbound traffic (service → attacker, e.g. to hide flag leaks)

```sh
cd /root/threesome
docker compose up --build -d
# or without docker:
cd proxy && python3 proxy.py
```

### Step 3 — Write filter functions

Open the generated module file (e.g. `proxy/filter_modules/myservice/myservice_in.py`) and add methods to the `Module` class. Each method receives a `Stream` object and returns `True` to block or `False` to pass.

```python
from src.stream import Stream, TCPStream, HTTPStream

class Module():

    # --- TCP filter example ---
    def sqli(self, stream: TCPStream):
        """block SQL injection attempts"""
        keywords = [b"' OR '", b"1=1", b"UNION SELECT", b"DROP TABLE"]
        return any(k in stream.current_message.upper() for k in keywords)

    def long_payload(self, stream: TCPStream):
        """block suspiciously large payloads"""
        return len(stream.current_message) > 4096

    # --- HTTP filter example ---
    def path_traversal(self, stream: HTTPStream):
        """block path traversal attempts"""
        return b"../" in stream.current_message or b"..%2F" in stream.current_message.upper()

    def block_flag_leak(self, stream: HTTPStream):
        """
        _out module: block responses that contain a flag
        put this in the _out module to prevent leaking flags to attackers
        """
        import re
        return bool(re.search(rb'[A-Z0-9]{31}=', stream.current_message))

    def execute(self, stream: Stream):
        ignored_functions = []
        attacks = [getattr(Module, attr) for attr in dir(Module)
                   if callable(getattr(Module, attr))
                   and not attr.startswith('__')
                   and attr != "execute"
                   and attr not in ignored_functions]
        for attack in attacks:
            try:
                if attack(self, stream):
                    return attack.__name__
            except IndexError:
                pass
            except Exception as e:
                if isinstance(e, KeyboardInterrupt):
                    raise e
                print(f"[ ERROR in MODULE: {attack.__name__} ]: {e}")
        return None
```

> **Hot reload:** just save the file — threesome picks up changes immediately without restarting. If the file has a syntax error, the previous working version keeps running.

### Stream reference

| Class | Attribute | Type | Description |
|---|---|---|---|
| `TCPStream` | `current_message` | `bytes` | Current packet (modify this to alter what gets sent) |
| `TCPStream` | `previous_messages` | `deque[bytes]` | Previous packets, newest first |
| `HTTPStream` | `current_message` | `bytes` | Raw HTTP bytes (modify this to alter the response) |
| `HTTPStream` | `current_http_message` | `HttpMessage` | Parsed current request/response |
| `HTTPStream` | `previous_http_messages` | `deque[HttpMessage]` | Previous parsed messages, newest first |

`HttpMessage` fields: `.method`, `.url`, `.path`, `.headers` (dict), `.parameters` (dict), `.raw_body`.

> If you modify the body of an HTTP message, update the `Content-Length` header in `current_message` accordingly.

### Skipping a filter temporarily

Add the function name to `ignored_functions` inside `execute()`:

```python
ignored_functions = ["sqli"]  # disable sqli filter without deleting it
```

### Monitor blocked attacks

```sh
# On the vulnbox:
watch cat /root/threesome/proxy/log.txt

# Or via docker logs:
docker logs --follow proxy
```

### Deploy filters via Ansible

To version-control your filter modules, store them in `configs/threesome_filters/` locally and copy them in `tasks/threesome.yml` after the setup step:

```yaml
- name: Setup threesome
  command: bash /root/threesome/setup.sh {{ game_interface }}

- name: Copy filter modules
  ansible.builtin.copy:
    src: ./configs/threesome_filters/
    dest: /root/threesome/proxy/filter_modules/
    # files are hot-reloaded automatically, no restart needed
```

### Redeploy threesome only

```sh
python3 deploy_parallel.py \
  --vulnbox-password $(python3 -c "import json; print(json.load(open('.env.json'))['root_password'])") \
  --modules threesome
```
