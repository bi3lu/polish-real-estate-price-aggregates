# ETL Sequence

```mermaid
sequenceDiagram
    actor User
    participant Silver as src.etl.silver
    participant Gold as src.etl.gold
    participant Public as src.etl.public
    participant Bronze as data/bronze
    participant SilverData as data/silver
    participant GoldData as data/gold
    participant PublicData as data/public

    User->>Silver: uv run python -m src.etl.silver
    Silver->>Bronze: load latest manifest / observations
    Silver->>Silver: validate RawListingObservation
    Silver->>Silver: normalize to CanonicalListing
    Silver->>SilverData: write timestamped CSV snapshot
    Silver->>SilverData: write canonical JSONL partitions

    User->>Gold: uv run python -m src.etl.gold
    Gold->>SilverData: load latest silver CSV
    Gold->>Gold: build listing features
    Gold->>Gold: build geo and segment aggregates
    Gold->>Gold: measure data quality
    Gold->>GoldData: write gold CSV outputs

    User->>Public: uv run python -m src.etl.public
    Public->>GoldData: load latest gold feature table
    Public->>Public: remove direct identifiers
    Public->>Public: suppress / generalize location
    Public->>Public: bucket and round public fields
    Public->>PublicData: write anonymized public CSVs
```

Each ETL stage can be run independently. By default, each stage selects the
latest available input from the previous layer.

Silver is the semantic boundary between source observations and downstream
analytics. It emits `CanonicalListing`, and gold/public logic should remain
source-neutral.
