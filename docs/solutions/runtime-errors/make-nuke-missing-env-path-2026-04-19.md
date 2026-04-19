---
title: "make nuke crashes with KeyError: 'SUPABASE_URL' — missed in app/.env refactor"
date: 2026-04-19
category: docs/solutions/runtime-errors/
module: scripts/nuke-data, Makefile
problem_type: runtime_error
component: development_workflow
symptoms:
  - "make nuke fails with KeyError: 'SUPABASE_URL' on os.environ lookup"
  - "scripts/nuke-data.py loads .env from repo root, which does not exist"
  - "Makefile nuke/nuke-keep targets invoke python without sourcing app/.env"
root_cause: config_error
resolution_type: config_change
severity: medium
related_components:
  - tooling
  - database
tags:
  - makefile
  - dotenv
  - env-sourcing
  - supabase
  - dev-script
  - nuke-data
  - app-env
---

# make nuke crashes with KeyError: 'SUPABASE_URL' — missed in app/.env refactor

## Problem

Running `make nuke` (or `make nuke-keep`) in the `nxme.ai` repo crashed before touching the database:

```
.venv/bin/python scripts/nuke-data.py
Traceback (most recent call last):
  File "/Users/vladimirtrifonov/src/ai/nxme.ai/scripts/nuke-data.py", line 25, in <module>
    SUPABASE_URL = os.environ["SUPABASE_URL"]
KeyError: 'SUPABASE_URL'
make: *** [nuke] Error 1
```

The script reached `os.environ["SUPABASE_URL"]` with an empty environment because neither the Makefile target nor `load_dotenv()` pointed at the real env file. The project stores backend env in `app/.env` (not repo-root `.env`), and this target was never updated when that convention was adopted.

## Symptoms

- `make nuke` fails immediately with `KeyError: 'SUPABASE_URL'` at script import time.
- `make nuke-keep` fails with the same `KeyError`, same line.
- `make migrate` and `make worker` work fine on the same checkout — confirming the environment itself is valid and the failure is target-scoped.
- Re-running with `env | grep SUPABASE_URL` shows the variable is unset in the shell Make invoked.

## What Didn't Work

- **Exporting the var in the current shell before running make.** Works one-off, but does not address the real bug and hides it from anyone else running `make nuke` on a fresh clone.
- **Adding a fallback like `os.environ.get("SUPABASE_URL", "")`.** Violates the project's "no env fallbacks — fail fast if missing" rule (`feedback_no_env_fallbacks.md`). The script's `KeyError` is actually the correct behavior; the bug is that env wasn't sourced, not that the script is too strict.
- **Assuming PR #160 (`19edd10 fix(make): migrate target now sources app/.env`) covered every python target.** It patched `migrate` and `worker` but did not sweep `nuke` / `nuke-keep` or `scripts/nuke-data.py`'s `load_dotenv()` path. The bug is a missed-surface regression from that refactor.
- **Assuming commit `bcc7299` (#163 `fix(scripts): update nuke-data.py for renamed tables`) fixed nuke-data.py.** That commit touched the same file on the same day (2026-04-18) for table renames (`glow_up_jobs` → `jobs`, `analyses` → `glowup_analyses`, added `uploads` FK order) but did not fix the `load_dotenv` path — it's a sibling regression vector in the same file, not an earlier attempt at this fix. (session history)

## Solution

Two coordinated changes — one in the Makefile, one in the script — so the target works both when invoked via `make` and if ever executed directly.

**`scripts/nuke-data.py:24`** — point `load_dotenv` at the actual env file location:

```python
# Before
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# After
load_dotenv(Path(__file__).resolve().parent.parent / "app" / ".env")
```

**`Makefile:32-36`** — source `app/.env` into the process environment before invoking the script, and declare `app/.env` as an order-only dep so `make` fails cleanly if the file is missing:

```makefile
# Before
nuke:
	.venv/bin/python scripts/nuke-data.py

nuke-keep:
	.venv/bin/python scripts/nuke-data.py --keep-demo

# After
nuke: app/.env
	@set -a && . ./app/.env && set +a && .venv/bin/python scripts/nuke-data.py

nuke-keep: app/.env
	@set -a && . ./app/.env && set +a && .venv/bin/python scripts/nuke-data.py --keep-demo
```

This mirrors the pattern already used by `migrate` and `worker` at `Makefile:39-44` — which in turn mirrors what `up` and `worker` had before PR #160 (session history).

No `.env.example` change required — no new env var was introduced; the fix is purely about sourcing the existing file from the correct path.

Verified: after the change, both targets load `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `DATABASE_URL` cleanly from `app/.env` and the script proceeds past the previous crash point.

## Why This Works

- **`set -a && . ./app/.env && set +a`** auto-exports every variable defined in `app/.env` into the subshell, so `os.environ[...]` lookups succeed. `set +a` limits the auto-export to just the sourcing block so it doesn't leak to subsequent recipe lines.
- **`app/.env` as a prerequisite** turns "env file missing" into a clear `make` error (`No rule to make target 'app/.env'`) instead of a downstream `KeyError` from Python — same class of fail-fast the project wants, but surfaced at the right layer.
- **`load_dotenv()` pointing at `app/.env`** gives defense-in-depth: if a developer runs `.venv/bin/python scripts/nuke-data.py` directly (bypassing `make`), the script still finds its env instead of producing the same confusing `KeyError`.
- **No fallbacks added** — the script still raises immediately if `SUPABASE_URL` is genuinely absent from `app/.env`, preserving the project's "fail fast on missing env" invariant.

## Prevention

1. **Sweep all Makefile targets when changing env-sourcing conventions.** When a refactor (like PR #160) switches where env lives, the change is not done until every target that invokes `.venv/bin/python`, `node`, `npx`, `alembic`, `arq`, etc. has been audited. A one-line grep before opening the PR catches this:
   ```bash
   grep -nE '^\t.*(\.venv/bin/python|node |npx |alembic|arq)' Makefile
   ```
   Every hit that doesn't already source `app/.env` is a latent bug. This is the second instance of the same missed-surface pattern (session history); a simple grep in the PR checklist would have caught both.

2. **Add a CI guardrail: assert every python-invoking Makefile target sources `app/.env`.** A small shell test wired into `make lint` or a pre-commit hook:
   ```bash
   # Fail if any python-invoking target skips env sourcing.
   awk '/^[a-zA-Z_-]+:/{t=$0} /\.venv\/bin\/python/{print t, $0}' Makefile \
     | grep -v 'app/\.env' && exit 1 || exit 0
   ```
   This makes "half-applied env refactor" impossible to ship.

3. **When touching `scripts/*.py`, mirror the Makefile's env contract.** Every script that can be run standalone should `load_dotenv(... / "app" / ".env")` pointing at the same file `make` sources. Treat "Makefile sources env" and "script self-loads env" as a paired invariant, not alternatives — one catches `make`-path users, the other catches direct-invocation users.

4. **Treat "dev-only tooling" as first-class in migration sweeps.** `make nuke` is pre-launch dev tooling (per `feedback_pre_launch_destructive_ok.md`), so it's easy to skip during a hurried refactor. But dev tooling that breaks is exactly what slows the team down the most — include every target, not just the "production" ones, in any env-layout PR checklist.

## Related Issues

- PR #160 — `fix(make): migrate target now sources app/.env` (commit `19edd10`). Predecessor: established the `set -a && . ./app/.env && set +a` pattern for `migrate` and `worker` but missed `nuke`/`nuke-keep`.
- PR #163 — `fix(scripts): update nuke-data.py for renamed tables` (commit `bcc7299`). Sibling: touched `scripts/nuke-data.py` on the same day for table renames but missed the `load_dotenv` path bug.
- Convention origin: commits `7d60cad` (`feat: Google OAuth login, env refactor, custom tab bar`) and `3415632` (`chore: consolidate pending working-tree changes`) established `app/.env` as the canonical backend env location. (session history)
