# Todos

- [x] **1. Fix CCalendar push ("detected dubious ownership")**
  - `push_services.py` now runs `git config --global --add safe.directory /root/<svc>`
    before any git op in the service dir, so root can operate on repos owned by
    another uid.

- [x] **1a. Easy patch apply to running services, with rollback**
  - New `patch_service.py` (git-based): `apply` commits a patch on the service's
    on-box git repo and rebuilds its docker stack; `rollback` does `git reset --hard`
    (default `HEAD~1`) and rebuilds; `log` shows patch history; `restart` rebuilds.
  - Docs: `docs/installation.md` → "Patching Running Services".

- [x] **2. Remove gen_env, single-source `.env.json`**
  - Deleted `gen_env.py`, `.env`, `.env.example`; added committed `env.json.example`.
  - `deploy_parallel.py::ensure_env()` auto-fills missing secrets into `.env.json`
    (mode 0600) and patches `run_exploit.sh` — runs first on every deploy.
  - Docs updated: `CLAUDE.md`, `docs/installation.md`, `.gitignore`.
