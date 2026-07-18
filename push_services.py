#!/usr/bin/env python3
"""
Scan the root home on the vulnbox, identify the service folders, and publish
each one as a private repository in a GitHub organization.

Runs after the Ansible setup (called automatically by deploy_parallel.py) or
standalone:

    python3 push_services.py

Reads everything it needs from .env.json:
  - vulnbox connection (hostname `vulnbox` from /etc/hosts, root_password)
  - github_org / github_token (filled in by hand from env.json.example)

A "service" is any directory directly under /root that is not one of the tools
this repo deploys (and not a hidden dotfile dir). The git init/commit/push runs
remotely on the vulnbox, where the sources already live.
"""

import json
import subprocess
import sys

import requests

ENV_FILE_PATH = ".env.json"
VULNBOX_HOST = "vulnbox"  # alias added to /etc/hosts by hosts.sh

# Directories under /root that this repo deploys — never treated as services.
TOOL_DIRS = {
    "ctffarm",
    "packmate",
    "tulip",
    "threesome",
    "wisscon",
    "flag_dashboard",
    "KickStarterPy",
    "snap",
}


def load_env() -> dict:
    try:
        with open(ENV_FILE_PATH) as f:
            return json.load(f)
    except Exception as e:
        sys.exit(f"[ERROR] Could not read {ENV_FILE_PATH}: {e}")


def run_ssh(password: str, remote_cmd: str) -> subprocess.CompletedProcess:
    """Run a command on the vulnbox over SSH using password auth."""
    cmd = [
        "sshpass",
        "-p",
        password,
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        f"root@{VULNBOX_HOST}",
        remote_cmd,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def list_services(password: str) -> list:
    """Return the service directory names found under /root on the vulnbox."""
    res = run_ssh(
        password,
        "find /root -mindepth 1 -maxdepth 1 -type d -printf '%f\\n'",
    )
    if res.returncode != 0:
        sys.exit(f"[ERROR] Failed to list /root on the vulnbox:\n{res.stderr.strip()}")

    services = []
    for name in res.stdout.splitlines():
        name = name.strip()
        if not name or name.startswith("."):
            continue
        if name in TOOL_DIRS:
            continue
        services.append(name)
    return sorted(services)


def repo_name(service: str) -> str:
    """Sanitize a folder name into a valid GitHub repo name."""
    return service.replace(" ", "-")


def create_repo(org: str, token: str, name: str) -> bool:
    """Create a private repo in the org. Returns True if it exists/was created."""
    resp = requests.post(
        f"https://api.github.com/orgs/{org}/repos",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={"name": name, "private": True, "auto_init": False},
        timeout=30,
    )
    if resp.status_code in (200, 201):
        print(f"  [GitHub] created {org}/{name}")
        return True
    # 422 with "name already exists" -> reuse the existing repo
    if resp.status_code == 422 and "already exists" in resp.text:
        print(f"  [GitHub] {org}/{name} already exists, reusing")
        return True
    print(f"  [ERROR] GitHub repo creation failed ({resp.status_code}): {resp.text}")
    return False


def push_service(password: str, org: str, token: str, service: str) -> bool:
    name = repo_name(service)
    if not create_repo(org, token, name):
        return False

    remote_url = f"https://x-access-token:{token}@github.com/{org}/{name}.git"
    # Service dirs may already be git repos owned by a different uid than the
    # SSH user (root) — git then refuses with "detected dubious ownership".
    # Mark the path safe before any git op.
    remote_cmd = (
        f"git config --global --add safe.directory /root/{service!r} && "
        f"cd /root/{service!r} && "
        "git init -q && "
        "git add -A && "
        "git -c user.email=ctf@vulnbox -c user.name=ctf "
        "commit -q -m 'initial service snapshot' --allow-empty && "
        "git branch -M main && "
        "git remote remove origin 2>/dev/null; "
        f"git remote add origin {remote_url!r} && "
        "git push -u origin main --force"
    )
    res = run_ssh(password, remote_cmd)
    if res.returncode == 0:
        print(f"  [push] {service} -> {org}/{name} OK")
        return True
    print(f"  [ERROR] push failed for {service}:\n{res.stdout.strip()}\n{res.stderr.strip()}")
    return False


def main(env: dict = None, password: str = None) -> None:
    env = env or load_env()
    org = env.get("github_org")
    token = env.get("github_token")
    password = password or env.get("root_password")

    if not org or not token:
        print("[WARN] github_org / github_token not set in .env.json — skipping service push.")
        return
    if not password:
        sys.exit("[ERROR] No vulnbox password available (root_password missing in .env.json).")

    print("\n[INFO] Scanning /root on the vulnbox for services...")
    services = list_services(password)

    if not services:
        print("[INFO] No service folders found. Nothing to push.")
        return

    print(f"\nFound {len(services)} service(s):")
    for s in services:
        print(f"  - {s}  ->  {org}/{repo_name(s)}")

    answer = input(
        f"\nPush these {len(services)} service(s) as PRIVATE repos to '{org}'? [y/N] "
    ).strip().lower()
    if answer not in ("y", "yes"):
        print("[INFO] Aborted. Nothing pushed.")
        return

    ok = 0
    for s in services:
        print(f"\n[PUSH] {s}")
        if push_service(password, org, token, s):
            ok += 1
    print(f"\n[DONE] Pushed {ok}/{len(services)} service(s) to '{org}'.")


if __name__ == "__main__":
    main()
