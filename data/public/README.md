# Public Anonymized Polish Real Estate Dataset

This directory contains the public, anonymized output of the real estate data
pipeline. The dataset is intended for exploratory analysis, dashboards,
benchmarking, and machine-learning experiments around Polish residential real
estate listings.

The files in this directory are generated from the internal gold-layer dataset
by `src/etl/public.py`. The public export intentionally removes direct listing
identifiers and sensitive source fields, then generalizes selected numerical and
location attributes before publication.

## Current Files

| File | Description |
| --- | --- |
| `estate_public_ml_features_20260519T071853818654Z.csv` | Public listing-level feature table for analysis and ML experiments. |
| `estate_public_data_quality_20260519T071853818654Z.csv` | Dataset-level quality and coverage metrics for the same export run. |

The timestamp in each filename is the UTC processing timestamp of the export.

## Coverage

This is not a full-country dump of all Polish real estate listings. The current
snapshot contains 23,719 public records from selected voivodeships only:

| Voivodeship | Records |
| --- | ---: |
| `malopolskie` | 12,355 |
| `dolnoslaskie` | 5,943 |
| `mazowieckie` | 3,362 |
| `opolskie` | 2,059 |

The dataset includes three listing categories: `mieszkanie`, `dom`, and
`kawalerka`. It should therefore be treated as a sampled regional dataset, not
as a representative census of the Polish housing market.

## Privacy and Anonymization

The public dataset is designed to reduce re-identification risk before sharing:

- Direct listing identifiers are removed.
- Listing URLs are removed.
- Street names, districts, seller names, seller ids, advertiser ids, image URLs,
  and raw descriptions are not included.
- Exact latitude and longitude are not published.
- City is published only for groups with at least 10 records sharing the same
  voivodeship, city, and estate type.
- If city is suppressed, a rounded coordinate grid may be published only when
  the grid group also contains at least 10 records.
- Rounded grid coordinates use one decimal place, which is intentionally less
  precise than raw coordinates.
- Price targets are rounded: total price to PLN 10,000, price per sqm to PLN
  100, and rent to PLN 50.
- Continuous physical attributes are mostly bucketed rather than published as
  exact values.

This export is suitable for public analytical use in its current form, but it is
still derived from real listing data. Do not join it with external datasets in a
way that attempts to identify individual properties, sellers, or source
listings. If the dataset is regenerated with new fields, run a fresh privacy
review before publishing.

## Listing Feature Schema

| Column | Description |
| --- | --- |
| `estate_type` | Listing type, for example `mieszkanie`, `dom`, or `kawalerka`. |
| `voivodeship` | Polish voivodeship slug. |
| `city` | City name when the city privacy group meets the minimum group size; otherwise empty. |
| `geo_lat_grid` | Rounded latitude grid when city is hidden and the grid group is large enough. |
| `geo_lon_grid` | Rounded longitude grid when city is hidden and the grid group is large enough. |
| `market` | Primary or secondary market indicator when available. |
| `building_type` | Generalized building type. |
| `seller_type` | Generalized seller type, such as agency or private. |
| `area_bucket` | Bucketed usable area. |
| `price_bucket` | Bucketed total listing price. |
| `rooms_bucket` | Bucketed room count. |
| `building_age_bucket` | Bucketed building age. |
| `floor_bucket` | Bucketed listing floor. |
| `building_floors_bucket` | Bucketed number of floors in the building. |
| `terrain_area_bucket` | Bucketed land area for houses when available. |
| `image_count_bucket` | Bucketed number of listing images. |
| `has_lift` | Whether the listing indicates an elevator. |
| `has_balcony` | Whether the listing indicates a balcony. |
| `has_garage` | Whether the listing indicates a garage. |
| `has_basement` | Whether the listing indicates a basement. |
| `has_separate_kitchen` | Whether the listing indicates a separate kitchen. |
| `has_air_conditioning` | Whether the listing indicates air conditioning. |
| `has_garden` | Whether the listing indicates a garden. |
| `amenity_count` | Count of selected boolean amenities present in the row. |
| `has_coordinates` | Whether a public coordinate grid is available for the row. |
| `is_price_outlier` | Flag inherited from the gold layer for unusually low or high prices. |
| `price_per_sqm_source` | Whether price per sqm comes from the source listing or was derived. |
| `public_target_price_pln` | Rounded public total price target in PLN. |
| `public_target_price_per_sqm_pln` | Rounded public price per sqm target in PLN. |
| `public_rent_pln` | Rounded public rent value in PLN when available. |
| `processed_at` | UTC timestamp of the public export run. |

## Data Quality File

The data quality CSV summarizes the export run. The current snapshot reports:

| Metric | Value |
| --- | ---: |
| `source_records_count` | 23,719 |
| `public_records_count` | 23,719 |
| `min_group_size` | 10 |
| `share_with_public_city` | 0.7557 |
| `share_with_public_geo_grid` | 0.1326 |
| `share_with_public_price_target` | 0.9933 |
| `distinct_public_cities_count` | 201 |

## Recommended Use

Good uses include:

- regional price exploration,
- feature engineering experiments,
- tabular ML baselines,
- data quality monitoring,
- dashboard prototypes,
- educational analysis of real estate market data.

Avoid using this dataset for:

- identifying individual listings or sellers,
- operational investment decisions without additional validation,
- claims about the entire Polish real estate market,
- legal, financial, or valuation decisions requiring authoritative data.

## Reproducibility

The public files are generated by the gold-to-public ETL stage:

```bash
uv run python -m src.etl.public
```

CSV files under `data/public/*.csv` are tracked with Git LFS, as configured in
the repository `.gitattributes` file.
