#!/usr/bin/env python3

import ipaddress
import json
import os
import secrets
import sys

ENV_FILE_PATH = ".env.json"
DOTENV_PATH = ".env"

if os.path.isfile(ENV_FILE_PATH):
    print(f"WARN: {ENV_FILE_PATH} already exists. Nothing done.", file=sys.stderr)
    exit(1)


def load_dotenv(path):
    """Carica un file KEY=value come dizionario di default per i prompt."""
    defaults = {}
    if not os.path.isfile(path):
        return defaults
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            defaults[key.strip().upper()] = value.strip().strip('"').strip("'")
    return defaults


DEFAULTS = load_dotenv(DOTENV_PATH)
if DEFAULTS:
    print(f"[INFO] Loaded defaults from {DOTENV_PATH} (press Enter to accept).")


def ask(label, env_key, required=True):
    """Chiede un valore mostrando il default da .env; Enter accetta il default."""
    default = DEFAULTS.get(env_key, "")
    suffix = f" (default {default})" if default else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if not value:
            value = default
        if value or not required:
            return value
        print("ERROR: a value is required.")


try:
    vulnbox_ip = ask("Enter the vulnbox IP", "VULNBOX_IP")
    ipaddress.IPv4Address(vulnbox_ip)
except ipaddress.AddressValueError:
    print(f"ERROR: {vulnbox_ip} is not a valid IP address!")
    exit(1)

gameserver_url = ask("Enter gameserver URL for flag submission", "GAMESERVER_URL")
if not gameserver_url.startswith("http://"):
    print(f"ERROR: {gameserver_url} is not a valid URL")
    exit(1)

team_token = ask("Enter the team token", "TEAM_TOKEN")
try:
    number_of_teams = int(ask("Enter the number of teams", "NUMBER_OF_TEAMS"))
except ValueError:
    print("ERROR: Number of teams must be an integer.")
    exit(1)

team_ip_format = ask("Enter the Python format string for team IP (use {i})", "TEAM_IP_FORMAT")
if "{i}" not in team_ip_format:
    print(f"ERROR: {team_ip_format} is not a valid format string.")
    exit(1)

game_interface = ask("Enter network interface name for the game", "GAME_INTERFACE")

github_org = ask(
    "Enter GitHub organization to push the vulnbox services to",
    "GITHUB_ORG",
    required=False,
)
github_token = ask(
    "Enter GitHub token with push access to that org (used to publish services)",
    "GITHUB_TOKEN",
    required=False,
)

tool_repos_org = ask(
    "Enter GitHub organization hosting the tool repos "
    "(KickStarterPy, threesome, dashboard, wisscon)",
    "TOOL_REPOS_ORG",
    required=False,
)
tool_repos_token = ask(
    "Enter GitHub token with read access to the tool repos org",
    "TOOL_REPOS_TOKEN",
    required=False,
)

exploit_vm_endpoint = ask(
    "Enter exploit VM endpoint [<ip>:<port>]", "EXPLOIT_VM_ENDPOINT", required=False
)
if exploit_vm_endpoint and ":" not in exploit_vm_endpoint:
    print("ERROR: only <ip>:<port> format is accepted")

exploit_vm_pubkey = ask(
    "Enter exploit VM public key", "EXPLOIT_VM_PUBKEY", required=False
)
vulnbox_privkey = ask(
    "Enter vulnbox private key (provided by the exploit VM's script)",
    "VULNBOX_PRIVKEY",
    required=False,
)

# Generate secure random secrets
env = {
    "base_path": "/root/",
    "vulnbox_ip": vulnbox_ip,
    "gameserver_url": gameserver_url,
    "team_token": team_token,
    "number_of_teams": number_of_teams,
    "teams_format": f"f'{team_ip_format}'",
    "game_interface": game_interface,
    "github_org": github_org,
    "github_token": github_token,
    "tool_repos_org": tool_repos_org,
    "tool_repos_token": tool_repos_token,
    "root_password": secrets.token_hex(32),
    "packmate_password": secrets.token_hex(32),
    "ctffarm_password": secrets.token_hex(32),
    "flag_dashboard_key": secrets.token_hex(32),
    "flag_dashboard_password": secrets.token_urlsafe(12),
    "exploit_vm_endpoint": exploit_vm_endpoint,
    "exploit_vm_pubkey": exploit_vm_pubkey,
    "vulnbox_privkey": vulnbox_privkey,
}

with open(ENV_FILE_PATH, "w") as f:
    json.dump(env, f, indent=4)

os.chmod(ENV_FILE_PATH, 0o600)

# Patch exploits/run_exploit.sh line with new password
RUN_EXPLOIT_PATH = "exploits/run_exploit.sh"
try:
    with open(RUN_EXPLOIT_PATH, "r") as f:
        lines = f.readlines()
    if len(lines) >= 3:
        lines[2] = f"\t--server-pass {env['ctffarm_password']} \\\n"
        with open(RUN_EXPLOIT_PATH, "w") as f:
            f.writelines(lines)
except FileNotFoundError:
    print(f"WARN: {RUN_EXPLOIT_PATH} not found — skipping password injection.")
