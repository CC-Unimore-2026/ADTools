# AD Tools

This repo contains all the tools and scripts needed to run and manage
an Attack and Defence vulnbox.

It contains several tools, some helpers and some tools that were developed
by havce members, tailored to the CyberChallenge.IT A/D CTF.

Many design decisions are made assuming the CCIT network topology,
so these scripts may not work well for every Attack/Defence CTF.

---

## Documentation

| Doc | Description |
|---|---|
| [docs/installation.md](docs/installation.md) | Requirements, team configuration, step-by-step deployment, module reference, and post-deploy services |
| [docs/threesome.md](docs/threesome.md) | Configuring the threesome TCP proxy and writing filter modules to block attacks |

---

## Writing Exploits

`exploit_template.py` is a ready-to-edit sploit skeleton for the farm
(`start_sploit.py` / S4DFarm). Copy it per service and fill in the gaps.

**Contract** (enforced by `start_sploit.py`):
- Executable with a shebang as line 1.
- Takes the victim host/IP as `argv[1]`.
- Prints each captured flag on its own line, flushing immediately
  (`print(flag, flush=True)`), so flags are never lost.

**Edit only two things:**

1. The `CONFIG` block at the top — all parameters live here:

   | Variable | Meaning |
   |---|---|
   | `SERVICE_NAME` | Service name as registered on the gameserver (case-sensitive) |
   | `SERVICE_PORT` | Port the vulnerable service listens on |
   | `FLAG_ID_HOST` / `FLAG_ID_PORT` / `FLAG_ID_PATH` | Gameserver attack-info (flag-id) endpoint |
   | `SKIP_TEAMS` | Team octets to never attack (NOP team, your own team) |
   | `TIMEOUT` | Network timeout (s) for every call |

2. The body of `attack(host, flag_id)` — the actual exploit. Return the
   flag string, or raise/return falsy on failure.

The `get_flag_ids()` parsing is service-specific (it depends on the JSON
shape the attack-info endpoint returns); adjust the marked block if your
service differs.

**Run manually (single target):**

```sh
.venv/bin/python exploit_template.py <vulnbox_ip>
```

**Run against all teams via the farm:**

```sh
.venv/bin/python start_sploit.py \
  --server-url http://127.0.0.1:42069 \
  --server-pass <ctffarm_password> \
  --interpreter .venv/bin/python \
  --pool-size 45 \
  ./exploit_template.py
```

Or use the wrapper: `bash run_exploit.sh ./exploit_template.py`.
