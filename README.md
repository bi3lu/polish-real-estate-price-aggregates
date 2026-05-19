# Polish Real Estate Price Aggregates

[![CI](https://github.com/bi3lu/polish-real-estate-price-aggregates/actions/workflows/ci.yml/badge.svg)](https://github.com/bi3lu/polish-real-estate-price-aggregates/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Type Checked](https://img.shields.io/badge/type%20checked-mypy-blue)
![Code Style](https://img.shields.io/badge/code%20style-black-000000)
![Linting](https://img.shields.io/badge/linting-ruff-orange)

Python data pipeline for collecting, normalizing, aggregating, and publishing
analysis-ready Polish residential real estate listing data.

The project reads listing data from one of the popular real estate advertising
services in Poland, stores raw records in a bronze layer, transforms them into a
clean silver dataset, builds gold analytical tables, and exports an anonymized
public dataset suitable for exploratory analysis and machine-learning
experiments.

The repository intentionally does not include source-service branding in the
documentation. To run the ingestion command, provide the appropriate listing and detail
base URLs for the supported service in your local `.env` file.

## Portfolio Highlights

- End-to-end data engineering pipeline with bronze, silver, gold, and public
  data layers.
- Resumable listing ingestion with duplicate detection and page checkpoints.
- Typed Pydantic models and strict static analysis with `mypy`.
- Feature engineering, aggregate tables, and data quality outputs for analytics
  and ML workflows.
- Privacy-aware public dataset export with location generalization, rounded
  targets, attribution, and Git LFS tracking.
- CI coverage for linting, formatting, type checks, and tests.

## What This Project Produces

The pipeline writes data into four layers:

| Layer | Location | Purpose |
| --- | --- | --- |
| Bronze | `data/bronze/` | Raw ingested listing snapshots and resume checkpoints. |
| Silver | `data/silver/` | Flat, normalized listing records with validated types. |
| Gold | `data/gold/` | ML-ready features, geographic aggregates, segment aggregates, and data quality metrics. |
| Public | `data/public/` | Anonymized public CSV exports with sensitive fields removed or generalized. |

The public dataset is documented separately in
[`data/public/README.md`](data/public/README.md).

Architecture and UML-style diagrams are available in [`docs/`](docs/README.md).

## Features

- CLI-based ingestion with configurable estate types, voivodeships, page limits,
  and worker threads.
- Resume support based on existing bronze external ids and page checkpoints.
- Bronze JSONL storage split by voivodeship.
- Bronze-to-silver normalization with Pydantic validation.
- Silver-to-gold feature engineering and aggregate tables.
- Gold-to-public anonymization with location suppression, rounded price targets,
  and bucketed attributes.
- Data quality exports for gold and public layers.
- Type checking and test coverage through `mypy`, `ruff`, `black`, `isort`, and
  `pytest`.

## Requirements

- Python 3.10 or newer.
- `uv` for dependency management.
- Git LFS if you want to version public CSV datasets from `data/public`.

Install `uv` using the official instructions for your operating system, then
install project dependencies with:

```bash
uv sync --dev
```

If you plan to work with public CSV files tracked by Git LFS:

```bash
git lfs install
git lfs pull
```

## Configuration

Create a local `.env` file in the repository root:

```bash
cp .env.example .env
```

Then fill in the source-service URLs:

```dotenv
MAIN_URL="https://example.com/path/to/search/results/"
ESTATE_URL="https://example.com/path/to/listing/details/"
```

`MAIN_URL` should point to the base search/listing-results URL of the supported
Polish real estate advertising service. `ESTATE_URL` should point to the base
listing-detail URL used to normalize relative listing links.

The `.env` file is intentionally ignored by Git. Do not commit credentials,
private URLs, or local configuration.

## Quick Start

Install dependencies:

```bash
uv sync --dev
```

Run a small ingestion job for one estate type and one voivodeship:

```bash
uv run python main.py \
  --estate-type mieszkanie \
  --voivodeship mazowieckie \
  --max-page 2 \
  --workers 1 \
  --pretty
```

Run the full configured ingestion:

```bash
uv run python main.py
```

The command prints a JSON summary containing the output path and number of newly
written records.

## CLI Options

```bash
uv run python main.py --help
```

Common options:

| Option | Description |
| --- | --- |
| `--estate-type`, `-t` | Estate type slug. Can be repeated or passed as comma-separated values. |
| `--voivodeship`, `-v` | Voivodeship slug. Can be repeated or passed as comma-separated values. |
| `--max-page` | Maximum page to process per estate type and voivodeship combination. |
| `--workers`, `--threads` | Number of worker threads used across ingestion targets. |
| `--pretty` | Pretty-print the JSON command output. |

Configured estate types:

- `mieszkanie`
- `dom`
- `kawalerka`

Configured voivodeships are defined in `src/config/globals.py`.

## Running the ETL Pipeline

After a bronze snapshot exists, run the ETL stages in order.

Bronze to silver:

```bash
uv run python -m src.etl.silver
```

Silver to gold:

```bash
uv run python -m src.etl.gold
```

Gold to public:

```bash
uv run python -m src.etl.public
```

Each stage selects the latest input snapshot from the previous layer by default
and writes timestamped CSV outputs to the next layer.

## Repository Layout

```text
.
├── main.py
├── src/
│   ├── config/          # Environment loading and global constants
│   ├── etl/             # Bronze, silver, gold, and public ETL stages
│   ├── models/          # Pydantic models for each data layer
│   ├── ingestion/       # Listing ingestion and parsing logic
│   └── utils/           # CLI, logging, and storage helpers
├── tests/               # Unit tests
├── data/
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   └── public/
└── .github/workflows/   # CI configuration
```

## Development

Run tests:

```bash
uv run pytest
```

Run linting and formatting checks:

```bash
uv run ruff check .
uv run black --check .
uv run isort --check-only .
uv run mypy .
```

Format code locally:

```bash
uv run black .
uv run isort .
```

## Continuous Integration

GitHub Actions CI is split into two jobs:

- `linter`: runs Ruff, Black check, isort check, and mypy.
- `tests`: runs the pytest suite.

The workflow is defined in `.github/workflows/ci.yml`.

## Public Dataset and Git LFS

CSV files under `data/public/*.csv` are configured for Git LFS in
`.gitattributes`:

```text
data/public/*.csv filter=lfs diff=lfs merge=lfs -text
```

If you add new public CSV exports, make sure Git LFS is installed and the files
are staged after the LFS tracking rule is present:

```bash
git lfs install
git add .gitattributes data/public/*.csv
```

## Data Privacy Notes

The public export removes direct listing identifiers, URLs, seller identifiers,
street-level information, raw coordinates, and image URLs. It also suppresses or
generalizes location fields and rounds public price targets.

The current public dataset is not a complete dump of all listings in Poland. It
contains selected voivodeships only and should be treated as a regional sample,
not as an authoritative nationwide market dataset.

Before publishing regenerated public data, review the output schema and sample
rows to ensure no new sensitive or source-identifying fields were introduced.

## Disclaimer

This project is for data engineering, analytics, and educational use. Respect
the terms of the source service, applicable law, and responsible data handling
practices. The generated datasets should not be used as the sole basis for
legal, financial, valuation, or investment decisions.
