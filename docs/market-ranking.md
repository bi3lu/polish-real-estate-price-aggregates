# Market Ranking CLI

The market ranking CLI builds analytical rankings from the public ML feature
dataset. It is designed for quick comparisons of regional markets without
requiring private bronze, silver, or gold data.

```bash
uv run python -m src.analytics.market_ranking
```

By default, the command selects the latest
`data/public/estate_public_ml_features_*.csv` file, groups records by
voivodeship, ranks groups by median public price per square meter, and prints a
terminal table.

The CLI uses only anonymized public fields. It does not require access to raw
bronze records, private silver/gold snapshots, source identifiers, listing URLs,
seller data, street-level locations, or private coordinates.

## Examples

Rank voivodeships by median public price per square meter:

```bash
uv run python -m src.analytics.market_ranking \
  --group-by voivodeship \
  --limit 10
```

Rank city-level markets for apartments only:

```bash
uv run python -m src.analytics.market_ranking \
  --group-by voivodeship_city \
  --estate-type mieszkanie \
  --min-records 50 \
  --limit 20
```

Export a machine-readable ranking:

```bash
uv run python -m src.analytics.market_ranking \
  --group-by voivodeship_estate_type \
  --format json
```

Use an explicit public dataset snapshot:

```bash
uv run python -m src.analytics.market_ranking \
  --input data/public/estate_public_ml_features_20260521T121529135028Z.csv
```

Find lower-price regional markets by reversing the default ranking direction:

```bash
uv run python -m src.analytics.market_ranking \
  --group-by voivodeship \
  --sort-by median_price_per_sqm_pln \
  --ascending
```

Rank segments by listing volume instead of price:

```bash
uv run python -m src.analytics.market_ranking \
  --group-by voivodeship_estate_type \
  --sort-by records_count \
  --format csv
```

## Supported Groups

| Group | Description |
| --- | --- |
| `voivodeship` | One row per voivodeship. |
| `city` | One row per public city label. Suppressed cities are skipped by default. |
| `estate_type` | One row per listing category. |
| `voivodeship_city` | One row per voivodeship and public city label. |
| `voivodeship_estate_type` | One row per voivodeship and listing category. |

City-based groups skip suppressed location labels by default. Pass
`--include-suppressed-location` to include a `suppressed` group.

## CLI Options

| Option | Description |
| --- | --- |
| `--input` | Public ML feature CSV to read. Defaults to the latest public snapshot. |
| `--group-by` | Ranking grain: `voivodeship`, `city`, `estate_type`, `voivodeship_city`, or `voivodeship_estate_type`. |
| `--voivodeship` | Filter by voivodeship. Can be repeated or comma-separated. |
| `--estate-type` | Filter by listing type. Can be repeated or comma-separated. |
| `--min-records` | Minimum group size required in the output. Defaults to `10`. |
| `--limit` | Maximum output rows. Defaults to `20`. |
| `--sort-by` | Ranking metric. Defaults to `median_price_per_sqm_pln`. |
| `--ascending` | Sort from lowest to highest value. |
| `--format` | Output format: `table`, `json`, or `csv`. Defaults to `table`. |
| `--include-suppressed-location` | Include suppressed city labels in city-based groups. |

## Output Metrics

| Metric | Description |
| --- | --- |
| `records_count` | Number of public records in the group. |
| `median_price_per_sqm_pln` | Median public target price per square meter. |
| `avg_price_per_sqm_pln` | Average public target price per square meter. |
| `q25_price_per_sqm_pln` | Lower quartile of public target price per square meter. |
| `q75_price_per_sqm_pln` | Upper quartile of public target price per square meter. |
| `median_price_pln` | Median public total price target. |
| `share_with_price_per_sqm` | Share of rows with a public price-per-sqm target. |
| `share_with_total_price` | Share of rows with a public total price target. |

## Example Output

Example table output for the current public dataset:

| Rank | Group | Records | Median sqm | Avg sqm | Median price | SQM coverage |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | `malopolskie` | 12,261 | 13,500 PLN | 13,378 PLN | 810,000 PLN | 100.00% |
| 2 | `mazowieckie` | 6,213 | 13,100 PLN | 17,057 PLN | 850,000 PLN | 99.97% |
| 3 | `pomorskie` | 8,074 | 10,100 PLN | 11,470 PLN | 800,000 PLN | 100.00% |

JSON and CSV formats expose the same fields with machine-readable column names,
which makes the command suitable for notebooks, dashboards, and lightweight
analysis scripts.
