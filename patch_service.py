#!/usr/bin/env python3
"""Apply patches to running vulnbox services, with git-based rollback.

Every service directory under /root on the vulnbox is a git repo (created by
push_services.py). This tool uses that git history as the patch/rollback
mechanism:

  - apply    -> apply a unified diff (or stage all current changes), commit it
                on top of the snapshot, then rebuild the service's docker stack.
  - rollback -> `git reset --hard` to a previous commit (default: the state
                before the last patch), then rebuild.
  - log      -> show the patch history (commits on the service repo).

Because every applied patch is its own commit, rolling back is just moving the
ref — no manual backups. Run from the repo root with the venv interpreter:

    .venv/bin/python patch_service.py apply    <service> <patch.diff> [-m msg]
    .venv/bin/python patch_service.py rollback <service> [--to <git-ref>]
    .venv/bin/python patch_service.py log      <service> [-n 20]
    .venv/bin/python patch_service.py restart  <service>

Connection (hostname `vulnbox`, root_password) is read from .env.json, exactly
like push_services.py.
"""

import argparse
import os
import subprocess
import sys

from push_services import VULNBOX_HOST, load_env, run_ssh

# Best-effort container rebuild: prefer the v2 plugin, fall back to the v1
# binary. Run from the service root, where the compose file is expected.
RESTART_SNIPPET = (
    "if docker compose version >/dev/null 2>&1; then DC='docker compose'; "
    "else DC='docker-compose'; fi; "
    "$DC up -d --build"
)


def password() -> str:
    pw = load_env().get("root_password")
    if not pw:
        sys.exit("[ERROR] root_password missing in .env.json.")
    return pw


def safe_dir(service: str) -> str:
    """Mark the service repo as a safe directory (avoids dubious-ownership)."""
    return f"git config --global --add safe.directory /root/{service!r}"


def scp_to(pw: str, local: str, remote: str) -> subprocess.CompletedProcess:
    cmd = [
        "sshpass", "-p", pw, "scp",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        local, f"root@{VULNBOX_HOST}:{remote}",
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def require_repo(pw: str, service: str) -> None:
    res = run_ssh(pw, f"{safe_dir(service)}; test -d /root/{service!r}/.git")
    if res.returncode != 0:
        sys.exit(
            f"[ERROR] /root/{service} is not a git repo on the vulnbox. "
            "Run push_services.py first (it snapshots each service into git)."
        )


def restart(pw: str, service: str) -> int:
    print(f"[INFO] Rebuilding docker stack for {service}...")
    res = run_ssh(pw, f"cd /root/{service!r} && {RESTART_SNIPPET}")
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        print(f"[ERROR] restart failed for {service}:\n{res.stderr.strip()}")
    else:
        print(f"[OK] {service} stack rebuilt.")
    return res.returncode


def cmd_apply(args) -> int:
    pw = password()
    require_repo(pw, args.service)

    git_apply = ""
    if args.patch:
        if not os.path.isfile(args.patch):
            sys.exit(f"[ERROR] patch file not found: {args.patch}")
        remote_patch = f"/tmp/{os.path.basename(args.patch)}"
        res = scp_to(pw, args.patch, remote_patch)
        if res.returncode != 0:
            sys.exit(f"[ERROR] failed to copy patch to vulnbox:\n{res.stderr.strip()}")
        # --check first so a bad patch aborts before any commit.
        git_apply = (
            f"git apply --check {remote_patch!r} && "
            f"git apply {remote_patch!r} && "
        )

    msg = args.message or ("apply " + (os.path.basename(args.patch) if args.patch else "live changes"))
    remote_cmd = (
        f"{safe_dir(args.service)} && "
        f"cd /root/{args.service!r} && "
        f"{git_apply}"
        "git add -A && "
        f"git -c user.email=ctf@vulnbox -c user.name=ctf commit -q -m {msg!r} && "
        "git --no-pager log --oneline -1"
    )
    res = run_ssh(pw, remote_cmd)
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        out = (res.stdout + res.stderr).strip()
        if "nothing to commit" in out:
            print(f"[INFO] No changes to apply for {args.service}.")
            return 0
        print(f"[ERROR] apply failed for {args.service}:\n{out}")
        return res.returncode

    print(f"[OK] patch committed on {args.service}.")
    return 0 if args.no_restart else restart(pw, args.service)


def cmd_rollback(args) -> int:
    pw = password()
    require_repo(pw, args.service)
    target = args.to
    res = run_ssh(
        pw,
        f"{safe_dir(args.service)} && cd /root/{args.service!r} && "
        f"git reset --hard {target!r} && git --no-pager log --oneline -1",
    )
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        print(f"[ERROR] rollback failed for {args.service}:\n{res.stderr.strip()}")
        return res.returncode
    print(f"[OK] {args.service} reset to {target}.")
    return 0 if args.no_restart else restart(pw, args.service)


def cmd_log(args) -> int:
    pw = password()
    require_repo(pw, args.service)
    res = run_ssh(
        pw,
        f"{safe_dir(args.service)} && cd /root/{args.service!r} && "
        f"git --no-pager log --oneline -n {int(args.n)}",
    )
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        print(f"[ERROR] log failed for {args.service}:\n{res.stderr.strip()}")
    return res.returncode


def cmd_restart(args) -> int:
    return restart(password(), args.service)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_apply = sub.add_parser("apply", help="apply a patch (or stage live changes) and rebuild")
    p_apply.add_argument("service")
    p_apply.add_argument("patch", nargs="?", help="unified diff to apply; omit to just commit current on-box changes")
    p_apply.add_argument("-m", "--message", help="commit message")
    p_apply.add_argument("--no-restart", action="store_true", help="don't rebuild the docker stack")
    p_apply.set_defaults(func=cmd_apply)

    p_rb = sub.add_parser("rollback", help="git reset the service to a previous commit and rebuild")
    p_rb.add_argument("service")
    p_rb.add_argument("--to", default="HEAD~1", help="git ref to reset to (default: HEAD~1 = before last patch)")
    p_rb.add_argument("--no-restart", action="store_true", help="don't rebuild the docker stack")
    p_rb.set_defaults(func=cmd_rollback)

    p_log = sub.add_parser("log", help="show the patch history of a service")
    p_log.add_argument("service")
    p_log.add_argument("-n", default=20, help="number of commits to show")
    p_log.set_defaults(func=cmd_log)

    p_rs = sub.add_parser("restart", help="rebuild the service's docker stack")
    p_rs.add_argument("service")
    p_rs.set_defaults(func=cmd_restart)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
