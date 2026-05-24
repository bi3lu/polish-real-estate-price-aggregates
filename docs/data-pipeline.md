# Data Pipeline

```mermaid
flowchart TD
    example_config[config/sources.example.yaml<br/>synthetic public example]
    local_config[config/sources.local.yaml<br/>private local config]
    config_loader[src.config.source_config]
    registry[src.ingestion.registry]
    adapters[src.ingestion.adapters<br/>neutral SourceAdapter implementations]
    pipeline[src.ingestion.pipeline]
    transport[src.ingestion.transport]
    parsing[src.ingestion.parsing]
    raw_model[RawListingObservation]
    bronze_storage[src.utils.storage]
    bronze[(data/bronze<br/>source_id/run_id partitions<br/>manifest.json)]
    silver_etl[src.etl.silver]
    canonical[CanonicalListing]
    silver[(data/silver<br/>CSV snapshots<br/>canonical JSONL partitions)]
    gold_etl[src.etl.gold]
    gold[(data/gold<br/>features + aggregates + quality)]
    public_etl[src.etl.public]
    public[(data/public<br/>anonymized CSV exports)]
    ranking[src.analytics.market_ranking]

    example_config --> config_loader
    local_config --> config_loader
    config_loader --> registry
    registry --> adapters
    adapters --> pipeline
    pipeline --> transport
    pipeline --> parsing
    parsing --> raw_model
    raw_model --> bronze_storage
    bronze_storage --> bronze
    bronze --> silver_etl
    silver_etl --> canonical
    canonical --> silver
    silver --> gold_etl
    gold_etl --> gold
    gold --> public_etl
    public_etl --> public
    public --> ranking
```

Layer responsibilities:

- `bronze`: private raw observations partitioned by neutral `source_id` and
  per-source `run_id`, with manifests and resume checkpoint metadata.
- `silver`: normalized `CanonicalListing` records. The layer writes canonical
  JSONL partitions by `source_id` and month, plus CSV snapshots used by existing
  downstream ETL.
- `gold`: model-ready listing features, geographic aggregates, segment
  aggregates, and quality metrics.
- `public`: privacy-filtered CSV exports with direct identifiers removed.
- `analytics`: public-data ranking utilities that require no private data.

The repository ignores local bronze, silver, gold, and demo outputs.
