# Hosted deployment (`docker compose`)

One PostgreSQL, one migration job, one API container. The API binds to `127.0.0.1` only:
put a TLS terminator in front of it and forward `X-Forwarded-*`.

## Boot it

```sh
cd harness/deploy
cp .env.example .env        # then fill in every REQUIRED value
docker compose up -d
docker compose ps           # migrate must reach "exited (0)"; backend must reach "healthy"
curl -fsS http://127.0.0.1:8000/api/v1/health | python -m json.tool
```

`/api/v1/health` echoing `"tutor": {"state": "configured"}` is the check that the model
settings took effect. `"state": "unconfigured"` means production was started with values
`config.py` refused to accept at boot and must not be reachable from here — production
refuses to start at all without a provider.

## Why every tutor variable is required

`Settings.from_env()` validates the language-model settings on **every** production boot,
and `migrate` boots production too: `backend/scripts/init_db.py` calls `Settings.from_env()`
before it opens a connection. The migration therefore needs the same four variables as the
API, not a subset.

This file previously defaulted `HARNESS_TUTOR_PROVIDER` to `offline`. That value is rejected
outright by `config.py` — the deterministic rules engine was removed — and the `migrate`
service was given no tutor variables at all. The result was a migration that exited 1 with
`ValueError: Production requires a configured language model`, and because `backend` declares
`depends_on: migrate: condition: service_completed_successfully`, the API never started. The
`offline` default is gone; every tutor variable is now `${VAR:?}`-required, so a missing one
stops `docker compose config` on your machine with the variable's name in the message instead
of failing after PostgreSQL is already running.

## Model options

| Option | Settings | Notes |
| --- | --- | --- |
| Hosted, OpenAI-compatible | `HARNESS_TUTOR_PROVIDER=openai`, `HARNESS_TUTOR_URL=https://…/v1`, `HARNESS_TUTOR_MODEL=…`, `HARNESS_TUTOR_KEY=…` | Production requires **HTTPS** for any remote host. A plain-HTTP remote URL is a boot error, not a warning. |
| Local, bundled | `docker compose --profile ollama up -d`, then `HARNESS_TUTOR_PROVIDER=ollama`, `HARNESS_TUTOR_URL=http://ollama:11434`, `HARNESS_TUTOR_MODEL=<pulled model>` | `config.py` exempts the `ollama` hostname from the HTTPS rule, so a loopback model is legal in production. Pull a model once: `docker compose exec ollama ollama pull qwen2.5:7b`. |

Ollama is profile-gated and is **not** started by a plain `docker compose up`, so a
deployment that talks to a remote provider never pays for a model runtime it does not use.
Start it before the API, or the first tutor turn is what discovers it is missing.

## Required values, and how to get them

| Variable | How |
| --- | --- |
| `HARNESS_POSTGRES_PASSWORD` | Any strong password. It is interpolated into the connection URL, so URL-safe characters only. |
| `HARNESS_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Production rejects anything under 32 characters or with fewer than 12 distinct characters. |
| `HARNESS_ALLOWED_HOSTS` | The public hostname plus `localhost`. A wildcard is refused in production. |
| `HARNESS_TUTOR_*` | See the table above. |

`deploy/.env` is gitignored (`harness/.gitignore` has an unanchored `.env`). Compose reads
`.env` from the compose file's directory, which is why the file lives here and not at the
repository root.

## Operations

**Logs.** `docker compose logs -f backend`.

**Re-running the migration.** `docker compose run --rm migrate`. It is idempotent: `init_db.py`
creates missing tables and columns, stamps `schema_version`, and refuses to migrate a database
whose schema is ahead of its stamp when a rollback snapshot exists, naming the file to restore.

**Upgrading.** Pull, then `docker compose up -d --build`. The migration runs before the API
restarts. Take a database snapshot first if the schema version changes; `init_db.py` writes
its own pre-migration anchor, but that anchor is inside the volume.

**Rolling back.** `docker compose down` (leaves `postgres-data` and `ollama-models` intact),
check out the previous commit, `docker compose up -d --build`. If a schema change has to be
undone, restore the pre-migration snapshot from inside the postgres volume — the application
will not migrate a database backwards.

**Health, then traffic.** The container healthcheck polls `/api/v1/health` every 15 s. The
published port stays on `127.0.0.1`. Behind a proxy, also set `HARNESS_TRUSTED_PROXY_IPS` to
that proxy's address, otherwise rate limiting treats every request as coming from one client.

## What this file does not do

- No TLS. Terminate it in front.
- No backup job. `docker compose exec postgres pg_dump -U harness harness > backup.sql`.
- No email transport. The verification and reset mailer stays inert unless
  `HARNESS_SMTP_HOST` is set on the `backend` service; without it those flows are unavailable
  and the app says so rather than pretending.
