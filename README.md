# Polish Real Estate Price Aggregates

[![CI](https://github.com/bi3lu/polish-real-estate-price-aggregates/actions/workflows/ci.yml/badge.svg)](https://github.com/bi3lu/polish-real-estate-price-aggregates/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Type Checked](https://img.shields.io/badge/type%20checked-mypy-blue)
![Code Style](https://img.shields.io/badge/code%20style-black-000000)
![Linting](https://img.shields.io/badge/linting-ruff-orange)
[![Coverage](assets/coverage.svg)](assets/coverage.svg)

Python data pipeline for collecting, normalizing, aggregating, and publishing
analysis-ready Polish residential real estate listing data.

The project is source-neutral by design. Runtime sources are configured in YAML,
identified by opaque `source_id` values, and handled through neutral adapter
types such as `embedded_json_listing_site` and `html_listing_site`. Domain
models and downstream ETL operate on `RawListingObservation` and
`CanonicalListing`, not on source-branded schemas.

Raw collection output is local-only and ignored by Git. Public sharing is
limited to anonymized exports in `data/public/`.

## Highlights

- Config-driven ingestion for multiple sources without hardcoded branded classes.
- Neutral adapter registry and reusable source adapters.
- Bronze storage partitioned by `source_id` and per-source `run_id`.
- Per-run manifests with ingestion counters and source metadata.
- Silver canonical JSONL partitions plus legacy CSV snapshots for downstream
  compatibility.
- Gold analytical features, aggregates, and data quality tables.
- Public anonymized exports and a market-ranking CLI.
- Offline synthetic tests with no real HTML fixtures, real source URLs, or live
  requests in CI.
- Strict static checks with `ruff`, `black`, `isort`, `mypy`, and `pytest`.

## Pipeline Outputs

| Layer | Location | Purpose |
| --- | --- | --- |
| Bronze | `data/bronze/<source_id>/<run_id>/` | Local raw observations and per-run manifests. |
| Silver | `data/silver/` | Normalized `CanonicalListing` records and canonical JSONL partitions. |
| Gold | `data/gold/` | ML-ready features, aggregates, and quality metrics. |
| Public | `data/public/` | Anonymized CSV exports suitable for analysis and examples. |

Bronze, silver, gold, and demo directories are ignored by Git. The repository
contains only synthetic source configuration and synthetic test fixtures.

## Requirements

- Python 3.10 or newer.
- `uv` for dependency management.
- Git LFS if you want to work with tracked public CSV exports.

Install dependencies:

```bash
uv sync --dev
```

Optional Git LFS setup:

```bash
git lfs install
git lfs pull
```

## Source Configuration

The public repository contains only:

```text
config/sources.example.yaml
```

For local ingestion, create a private config:

```bash
cp config/sources.example.yaml config/sources.local.yaml
```

`config/sources.local.yaml` is ignored by Git. Do not commit real source URLs,
credentials, raw output, or private collection settings.

Each source supports:

| Field | Description |
| --- | --- |
| `source_id` | Opaque local identifier used in storage and records. It does not need to reveal the real source name. |
| `adapter_type` | Neutral adapter type. Supported values are registered in `src/ingestion/registry.py`. |
| `enabled` | Enables or disables the source without code changes. |
| `base_url` | Base URL used for detail URL normalization. |
| `search_url_template` | Search URL template. Must include `{page}` and can use `{property_type}`, `{voivodeship}`, `{source_id}`, `{canonical_property_type}`. |
| `rate_limit_seconds` | Per-source pacing between HTTP requests. |
| `max_pages_default` | Per-source page cap. The CLI cap and hard project cap still apply. |
| `respect_robots_txt` | Policy flag documenting the expected collection posture. |
| `allowed_offer_types` | Allowed offer categories for the source config. |
| `allowed_property_types` | Canonical property types this source should receive, such as `mieszkanie` or `dom`. |
| `property_type_mapping` | Optional mapping from canonical project types to source-specific URL slugs. |

Example:

```yaml
sources:
  - source_id: source_a
    adapter_type: embedded_json_listing_site
    enabled: true
    base_url: "https://example-listing-site.local"
    search_url_template: "https://example-listing-site.local/search/{property_type}/{voivodeship}?page={page}"
    rate_limit_seconds: 5
    max_pages_default: 3
    respect_robots_txt: true
    allowed_offer_types:
      - sale
    allowed_property_types:
      - mieszkanie
      - dom
    property_type_mapping:
      mieszkanie: apartments
      dom: houses
```

The pipeline keeps canonical values in records, checkpoints, and ETL. The
mapping is used only when building source URLs.

More detail: [docs/source-configuration.md](docs/source-configuration.md).

## Running Ingestion

Run one small target:

```bash
uv run python main.py \
  --estate-type mieszkanie \
  --voivodeship mazowieckie \
  --max-page 1 \
  --workers 1 \
  --pretty
```

Run all enabled local sources with default filters:

```bash
uv run python main.py
```

Useful options:

| Option | Description |
| --- | --- |
| `--estate-type`, `-t` | Canonical estate type. Can be repeated or comma-separated. |
| `--voivodeship`, `-v` | Voivodeship slug. Can be repeated or comma-separated. |
| `--max-page` | Requested page cap per target. Also limited by source config and the project hard cap. |
| `--workers`, `--threads` | Number of worker threads across ingestion targets. |
| `--ignore-checkpoints` | Start selected targets from page 1 while still deduplicating existing bronze ids. |
| `--duplicate-page-stop-threshold` | Stop after N consecutive duplicate-only pages. `0` disables this stop. |
| `--shard-strategy` | `none`, `price`, or `market-price`. Defaults to `market-price`. |
| `--source-config` | Explicit YAML config path. Defaults to local config when present, otherwise the example. |
| `--pretty` | Pretty-print the JSON command output. |

The command prints a JSON summary containing the manifest path, record count,
selected filters, and enabled `source_id` values.

## Docker

The project includes a Docker image and Compose setup for long-running
background ingestion. The image does not contain private source config or local
pipeline data. Compose mounts:

```text
./config -> /app/config:ro
./data   -> /app/data
```

Create `config/sources.local.yaml` first, then build and start the ingestion
loop:

```bash
docker compose build
docker compose up -d ingestion
```

Follow logs:

```bash
docker compose logs -f ingestion
```

Stop the background loop:

```bash
docker compose down
```

By default, the loop runs immediately and then every hour with:

```text
INGESTION_ARGS="--max-page 1 --workers 1"
RUN_SILVER_ETL=true
RUN_GOLD_ETL=false
RUN_PUBLIC_ETL=false
```

Override runtime settings without editing source code:

```bash
INGESTION_INTERVAL_SECONDS=21600 \
INGESTION_ARGS="--estate-type dom --voivodeship opolskie --max-page 2 --workers 1" \
RUN_GOLD_ETL=true \
docker compose up -d ingestion
```

Run a one-off containerized smoke ingestion:

```bash
docker compose run --rm ingestion-once
```

More detail: [docs/docker.md](docs/docker.md).

## Storage Layout

Current bronze layout:

```text
data/
  bronze/
    manifest.json
    source_a/
      2026-05-23T10-30-00Z/
        manifest.json
        observations.jsonl
```

Each source run manifest contains fields such as:

```json
{
  "source_id": "source_a",
  "run_id": "2026-05-23T10-30-00Z",
  "adapter_type": "embedded_json_listing_site",
  "started_at": "2026-05-23T10:30:00Z",
  "finished_at": "2026-05-23T10:35:00Z",
  "pages_requested": 3,
  "pages_succeeded": 3,
  "records_raw": 142,
  "records_canonical": 137,
  "parser_errors": 0
}
```

Current silver canonical layout:

```text
data/
  silver/
    canonical_listings/
      source_id=source_a/
        month=2026-05/
          listings.jsonl
```

Gold and public layers are written as timestamped CSV outputs under
`data/gold/` and `data/public/`.

## ETL

Run stages after bronze data exists:

```bash
uv run python -m src.etl.silver
uv run python -m src.etl.gold
uv run python -m src.etl.public
```

Silver loads bronze observations and writes normalized `CanonicalListing`
records. Gold reads silver outputs and builds feature tables, geographic
aggregates, segment aggregates, and quality metrics. Public ETL reads gold
features and suppresses direct identifiers, street-level data, raw coordinates,
URLs, image URLs, and seller identifiers.

## Offline Demo

The demo pipeline runs without contacting any configured source:

```bash
uv run python -m src.etl.demo
```

It writes deterministic fixture-based outputs under:

```text
data/demo/bronze/
data/demo/silver/
data/demo/gold/
data/demo/public/
```

Use this path to review the ETL flow in a fresh checkout without private config
or network access.

## Market Ranking CLI

After a public dataset exists:

```bash
uv run python -m src.analytics.market_ranking
```

Examples:

```bash
uv run python -m src.analytics.market_ranking \
  --group-by voivodeship \
  --limit 10

uv run python -m src.analytics.market_ranking \
  --group-by voivodeship_city \
  --estate-type mieszkanie \
  --min-records 50 \
  --format json
```

More examples: [docs/market-ranking.md](docs/market-ranking.md).

## Architecture

```text
main.py
  -> src.utils.cli
      -> src.config.source_config
      -> src.ingestion.registry
      -> src.ingestion.adapters.base
      -> src.ingestion.pipeline
      -> src.utils.storage

src.etl.silver -> src.etl.gold -> src.etl.public
```

Key modules:

| Module | Role |
| --- | --- |
| `src/config/source_config.py` | Pydantic validation and YAML loading for source configs. |
| `src/ingestion/models.py` | Neutral ingestion models: `RawListingObservation`, `CanonicalListing`, source run stats. |
| `src/ingestion/adapters/base.py` | `SourceAdapter` protocol and reusable neutral adapter classes. |
| `src/ingestion/registry.py` | Adapter registry and dynamic adapter construction from config. |
| `src/ingestion/transport.py` | HTTP fetching, throttling, embedded JSON extraction, retry and cooldown logic. |
| `src/ingestion/parsing.py` | Payload-to-observation extraction. |
| `src/ingestion/pipeline.py` | Pagination, source filtering, sharding, resume logic, threading. |
| `src/utils/storage.py` | Bronze manifests, source/run partitioning, checkpoints. |
| `src/etl/silver.py` | Raw observations to `CanonicalListing`. |
| `src/etl/gold.py` | Feature and aggregate generation. |
| `src/etl/public.py` | Privacy-aware public export. |

Diagrams live in [docs/](docs/README.md).

## Testing

Run all tests:

```bash
uv run pytest
```

Run static checks:

```bash
uv run ruff check .
uv run black --check .
uv run isort --check-only .
uv run mypy src tests
```

Format locally:

```bash
uv run black .
uv run isort .
```

Test policy:

- Tests are offline.
- Source fixtures live under `tests/fixtures/sources/`.
- Fixtures are synthetic and must not contain real source HTML, real listing
  descriptions, real source URLs, or source brands.
- CI uses only example/synthetic config and does not perform live requests.

## Repository Layout

```text
.
├── config/
│   └── sources.example.yaml
├── docs/
├── main.py
├── src/
│   ├── analytics/
│   ├── config/
│   ├── etl/
│   ├── ingestion/
│   │   ├── adapters/
│   │   ├── models.py
│   │   ├── parsing.py
│   │   ├── pipeline.py
│   │   ├── registry.py
│   │   └── transport.py
│   ├── models/
│   └── utils/
├── tests/
│   └── fixtures/sources/
└── data/
    └── public/
```

## Responsible Collection

This project is for data engineering, analytics, and educational use. Keep
collection conservative:

- Respect source terms, robots policy, and applicable law.
- Use low page limits, low worker counts, and explicit rate limits.
- Treat `403`, `429`, challenge pages, and repeated failures as stop signals.
- Do not add CAPTCHA solving, anti-bot bypass, proxy rotation for evasion,
  fingerprint spoofing, account farming, or similar controls.
- Keep raw data private and publish only anonymized public outputs after review.

More detail: [docs/ethics.md](docs/ethics.md).

## Public Dataset

The public export removes direct listing identifiers, URLs, seller identifiers,
street-level information, raw coordinates, and image URLs. It also suppresses or
generalizes location fields and rounds public price targets.

The current public dataset is a sample produced by configured runs, not an
official market registry or a complete national dataset. Analytical outputs are
useful for exploration, quality monitoring, dashboards, and ML baselines, but
should not be treated as legal, financial, valuation, or investment advice.

Public dataset metadata is documented in
[data/public/README.md](data/public/README.md).
