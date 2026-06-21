# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Tooling to deploy and operate an Attack/Defence CTF vulnbox, tailored to the
CyberChallenge.IT (CCIT) network topology. The vulnbox is a remote Ubuntu host;
this repo runs locally and pushes tools to it over SSH via Ansible. Most design
assumptions (IP format `10.60.{i}.1`, `game` interface, gameserver endpoints)
are CCIT-specific and may not transfer to other A/D games.

## Architecture

Three layers:

1. **Orchestrator (local):** `deploy_parallel.py` wraps `ansible-playbook`. It
   does NOT run modules naively in parallel — order is enforced:
   - `common` runs **first, alone** (installs Docker, SSH keys, and *changes the
     root password* to `root_password` from `.env.json`).
   - remaining modules run concurrently (one thread each).
   - `kickstarterpy` and `git_deploy` run **last, sequentially**, after the
     parallel batch.
   - finally it calls `push_services.main()` (unless `--skip-push`): SSH into
     the vulnbox, list service folders under `/root`, confirm, and publish each
     as a private GitHub repo. See `push_services.py`.
   Because `common` rotates the root password, every deploy after it must use
   the new `root_password` from `.env.json`, not the original VM password. This
   is the #1 source of auth failures.

2. **Ansible (`vulnbox_deploy.yml` + `tasks/*.yml`):** one task file per module.
   `vulnbox_deploy.yml` includes each `tasks/<module>.yml` gated on whether the
   module is in the `modules` extra-var. The valid module set is hard-coded in
   the playbook's validation `fail` task — keep it in sync when adding a module
   (add the `tasks/<name>.yml`, the include block, AND the allow-list).
   Inventory is the single host alias `vulnbox` (resolved via `/etc/hosts`).

3. **Runtime tools on the vulnbox (Docker):** S4DFarm (flag submission farm,
   `127.0.0.1:42069`), Packmate (pcap capture/analysis, `65000`), threesome
   (TCP proxy for filtering attacks), flag_dashboard, wisscon (WireGuard VPN),
   KickStarterPy. Most are upstream projects deployed via `tasks/git_deploy.yml`
   / git clone; this repo holds only configs (`configs/`) and patches
   (`patches/`).

## Config flow

`.env.json` (gitignored, mode 0600) is the single source of truth for the
target + all generated secrets. Generated interactively by `gen_env.py`, then
passed to Ansible as `--extra-vars @.env.json`. `gen_env.py` also patches the
`--server-pass` line (line 3) of `run_exploit.sh` with the generated
`ctffarm_password`. There is no `.env.json.example`; see `docs/installation.md`
for the field list.

`teams_format` is stored as a Python f-string literal (e.g. `"f'10.60.{i}.1'"`)
and `eval`'d downstream to enumerate team IPs.

`github_org` / `github_token` (prompted by `gen_env.py`) are used by
`push_services.py` to publish the vulnbox service folders as private repos.
This token is distinct from the `GITHUB_TOKEN` in `deploy_parallel.py`, which is
the `token` extra-var used by Ansible to clone the private *tool* repos.
`push_services.py` decides what counts as a "service" by excluding the deployed
tool dirs — keep its `TOOL_DIRS` set in sync if a module's `/root` dest changes.

## Common commands

Setup (one time):
```sh
python3 -m venv .venv
.venv/bin/pip install ansible passlib requests
.venv/bin/ansible-galaxy collection install community.docker ansible.posix
.venv/bin/python gen_env.py                 # creates .env.json (refuses if it exists)
sudo bash hosts.sh <vulnbox_ip> <nop_ip>   # adds `vulnbox` alias to /etc/hosts
```

Deploy (first run uses the *initial* VM password):
```sh
.venv/bin/python deploy_parallel.py --vulnbox-password <initial_pw> \
  --modules common kickstarterpy s4dfarm packmate dashboard
```

Redeploy a single module (use the *new* root password from .env.json):
```sh
.venv/bin/python deploy_parallel.py \
  --vulnbox-password $(.venv/bin/python -c "import json;print(json.load(open('.env.json'))['root_password'])") \
  --modules threesome
```

Run an Ansible module directly (what deploy_parallel.py shells out to):
```sh
.venv/bin/ansible-playbook vulnbox_deploy.yml -i vulnbox, -u root \
  --extra-vars "ansible_user=root ansible_password=<pw> token=<gh_token>" \
  --extra-vars @.env.json --extra-vars '{"modules":["s4dfarm"]}'
```

Exploits / farm:
```sh
.venv/bin/python exploit_template.py <vulnbox_ip>   # single target, manual
bash run_exploit.sh ./myexploit.py                  # all teams via S4DFarm
```

All local scripts run under `.venv/bin/python` (it has `requests` + `ansible`),
not the system `python3`. The exploit farm passes `--interpreter .venv/bin/python`
so sploits inherit the same env.

Pull services off / push patches to the vulnbox:
```sh
bash vulnbox_download.sh    # rsync /root/* (minus tools) into ./services
bash vulnbox_patch.sh       # rsync ./services/* back to vulnbox:/root
```

## Writing exploits

`exploit_template.py` is the sploit skeleton run by `start_sploit.py` (S4DFarm).
Contract enforced by the farm: executable with shebang on line 1, takes victim
host as `argv[1]`, prints each flag on its own line with `flush=True`. Edit only
the `CONFIG` block and `attack(host, flag_id)`; `get_flag_ids()` parsing is
service-specific (depends on the attack-info JSON shape). The template
intentionally has placeholders `<service name>` / `<port>` that raise until
filled — do not "fix" them with dummy values.

## threesome filters

threesome is a hot-reloading TCP proxy. Per service it generates `<svc>_in.py`
(attacker→service) and `<svc>_out.py` (service→attacker, e.g. block flag leaks)
under `proxy/filter_modules/<svc>/`. Filters are methods on a `Module` class
returning `True` to block. Saving the file hot-reloads it (syntax errors keep
the last good version). Version filters in `configs/threesome_filters/` and copy
them in `tasks/threesome.yml`. Full reference: `docs/threesome.md`.

## Gotchas

- Secrets (`GITHUB_TOKEN` in `deploy_parallel.py`, passwords in `run_exploit.sh`
  / `hosts.sh` / `vulnbox_download.sh`) are committed as `***` placeholders in
  the repo history; real values live only in `.env.json` at runtime. Never
  commit real secrets.
- `ubuntu_version` in `vulnbox_deploy.yml` (default `jammy`) gates the Docker
  apt repo — set it to match the actual vulnbox Ubuntu release.
- Comments and CLI help in `deploy_parallel.py` / `gen_env.py` are in Italian;
  keep that style when editing those files.
