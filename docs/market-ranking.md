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

The ranking uses public anonymized fields only. It does not read source
identifiers, URLs, street-level location, seller data, or private coordinates.
