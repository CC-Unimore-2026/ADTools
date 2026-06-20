#!/usr/bin/env python3

import ipaddress
import json
import os
import secrets
import sys

ENV_FILE_PATH = ".env.json"

if os.path.isfile(ENV_FILE_PATH):
    print(f"WARN: {ENV_FILE_PATH} already exists. Nothing done.", file=sys.stderr)
    exit(1)

try:
    vulnbox_ip = input("Enter the vulnbox IP: ")
    ipaddress.IPv4Address(vulnbox_ip)
except ipaddress.AddressValueError:
    print(f"ERROR: {vulnbox_ip} is not a valid IP address!")
    exit(1)

gameserver_url = input("Enter gameserver URL for flag submission: ")
if not gameserver_url.startswith("http://"):
    print(f"ERROR: {gameserver_url} is not a valid URL")
    exit(1)

team_token = input("Enter the team token: ")
try:
    number_of_teams = int(input("Enter the number of teams: "))
except ValueError:
    print("ERROR: Number of teams must be an integer.")
    exit(1)

team_ip_format = input("Enter the Python format string for team IP (use {i}): ")
if "{i}" not in team_ip_format:
    print(f"ERROR: {team_ip_format} is not a valid format string.")
    exit(1)

game_interface = input("Enter network interface name for the game: ")

exploit_vm_endpoint = input("Enter exploit VM endpoint [<ip>:<port>]: ")
if ":" not in exploit_vm_endpoint:
    print("ERROR: only <ip>:<port> format is accepted")

exploit_vm_pubkey = input("Enter exploit VM public key:")
vulnbox_privkey = input(
    "Enter vulnbox private key (provided by the exploit VM's script): "
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

# Patch run_exploit.sh line with new password
try:
    with open("run_exploit.sh", "r") as f:
        lines = f.readlines()
    if len(lines) >= 3:
        lines[2] = f"\t--server-pass {env['ctffarm_password']} \\\n"
        with open("run_exploit.sh", "w") as f:
            f.writelines(lines)
except FileNotFoundError:
    print("WARN: run_exploit.sh not found — skipping password injection.")
