# Docker

The repository includes a Dockerfile and Compose setup for running ingestion in
the background. The image contains application code and the public synthetic
example config only. Real source config and local pipeline data are mounted from
the host.

## Files

| File | Purpose |
| --- | --- |
| `Dockerfile` | Builds a Python 3.10 runtime with `uv` and project dependencies. |
| `.dockerignore` | Keeps private config, local data, caches, tests, and docs out of the build context. |
| `docker-compose.yml` | Defines `ingestion` and `ingestion-once` services. |
| `docker/ingestion-loop.sh` | Runs ingestion repeatedly with optional ETL stages. |
| `docker/run-ingestion.sh` | Host-side helper for long-running macOS runs with `caffeinate`. |

## Required Local Files

Create a private source config before running the background service:

```bash
cp config/sources.example.yaml config/sources.local.yaml
```

Then edit `config/sources.local.yaml` with local source definitions.

The Compose services mount:

```text
./config -> /app/config:ro
./data   -> /app/data
```

This keeps source configuration and generated data outside the image.

## Build

```bash
docker compose build
```

## Background Ingestion

Start the loop:

```bash
./docker/run-ingestion.sh start
```

The helper script is the recommended entry point for long-running local runs on
macOS. Plain Compose still works:

```bash
docker compose up -d ingestion
```

On macOS the helper starts Compose in detached mode and keeps a local
`caffeinate` process alive so the host does not suspend Docker when the display
turns off or the machine is locked. The display may still turn off; the
important part is that system sleep is blocked while ingestion is running.

View logs:

```bash
./docker/run-ingestion.sh logs
```

Stop:

```bash
./docker/run-ingestion.sh stop
```

The service has `restart: unless-stopped`, so Docker restarts it after daemon or
host restarts unless you explicitly stop it.

## One-Off Smoke Run

```bash
docker compose run --rm ingestion-once
```

The one-off service uses the same mounted `config/` and `data/` directories but
does not enter the infinite loop.

## Runtime Variables

The loop is controlled by environment variables on the `ingestion` service.

| Variable | Default | Description |
| --- | --- | --- |
| `SOURCE_CONFIG` | `/app/config/sources.local.yaml` | Config path passed to `main.py`. |
| `INGESTION_INTERVAL_SECONDS` | `3600` | Sleep time between loop runs. |
| `INGESTION_FAILURE_INTERVAL_SECONDS` | `300` | Sleep time before retrying after a failed ingestion run. |
| `INGESTION_ON_START` | `true` | Run immediately on container start. Set `false` to wait one interval first. |
| `INGESTION_ARGS` | `--workers 3` in Compose | Extra CLI args appended to `main.py`. |
| `RUN_SILVER_ETL` | `true` | Run `src.etl.silver` after successful ingestion. |
| `RUN_GOLD_ETL` | `false` | Run `src.etl.gold` after successful ingestion. |
| `RUN_PUBLIC_ETL` | `false` | Run `src.etl.public` after successful ingestion. |
| `MAX_FAILURES_BEFORE_EXIT` | `0` | Consecutive ingestion failures before exiting. `0` means keep retrying forever. |

Example:

```bash
INGESTION_INTERVAL_SECONDS=21600 \
INGESTION_ARGS="--estate-type dom --voivodeship opolskie --max-page 2 --workers 1" \
RUN_GOLD_ETL=true \
RUN_PUBLIC_ETL=true \
./docker/run-ingestion.sh start
```

## Host Sleep And Locking

Docker containers cannot keep a macOS host awake from inside the container. If
the host suspends while `urllib` is waiting on a response, the current ingestion
run can fail after wake-up with a transient network error. The container loop
will keep retrying, but the recommended local setup is:

```bash
./docker/run-ingestion.sh start
```

Useful commands:

```bash
./docker/run-ingestion.sh status
./docker/run-ingestion.sh logs
./docker/run-ingestion.sh stop
```

If you do not want the helper to manage `caffeinate`, run:

```bash
DISABLE_KEEP_AWAKE=true ./docker/run-ingestion.sh start
```

## Operational Notes

- Keep `INGESTION_ARGS` conservative for always-on runs.
- Prefer `--workers 1` or another low worker count unless the source explicitly
  tolerates more traffic.
- Use source-level `rate_limit_seconds` and `max_pages_default` in
  `config/sources.local.yaml`.
- Add new sources by editing config and restarting the service:

```bash
docker compose restart ingestion
```

- Raw data remains in mounted `./data`, which is ignored by Git.
