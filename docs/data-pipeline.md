# Data Pipeline

```mermaid
flowchart TD
    source_config[config/sources*.yaml<br/>source definitions]
    config_types[src.config.types<br/>shared type aliases]
    config_loader[src.config.source_config<br/>Pydantic validation]
    cli[main.py / src.utils.cli]
    ingestion[src.ingestion.estate_ingestion<br/>compatibility facade]
    ingestion_pipeline[src.ingestion.pipeline<br/>pagination + resume]
    ingestion_transport[src.ingestion.transport<br/>listing/detail fetch]
    ingestion_parsing[src.ingestion.parsing<br/>raw observation mapping]
    bronze_storage[src.utils.storage]
    bronze[(data/bronze<br/>JSONL snapshots + manifest)]
    silver_etl[src.etl.silver]
    silver[(data/silver<br/>normalized CSV)]
    gold_etl[src.etl.gold]
    gold[(data/gold<br/>features + aggregates + quality)]
    public_etl[src.etl.public]
    public[(data/public<br/>anonymized CSV + quality)]
    market_ranking[src.analytics.market_ranking<br/>market rankings]
    public_readme[data/public/README.md]

    source_config --> config_loader
    config_loader --> cli
    config_types --> cli
    config_types --> ingestion_pipeline
    config_types --> market_ranking
    cli --> ingestion
    ingestion --> ingestion_pipeline
    ingestion_pipeline --> ingestion_transport
    ingestion_pipeline --> ingestion_parsing
    ingestion_pipeline --> bronze_storage
    bronze_storage --> bronze
    bronze --> silver_etl
    silver_etl --> silver
    silver --> gold_etl
    gold_etl --> gold
    gold --> public_etl
    public_etl --> public
    public --> market_ranking
    public --> public_readme
```

The pipeline follows a layered data engineering pattern:

- `bronze`: raw ingested records and resume metadata.
- `silver`: normalized listing records with validated fields.
- `gold`: model-ready features, geographic aggregates, segment aggregates, and
  quality metrics.
- `public`: anonymized records designed for safe public analysis.
- `analytics`: command-line summaries and rankings derived from public data.

Ingestion is implemented as a small facade plus focused internal modules. The
facade preserves the historical import path, while `pipeline`, `transport`, and
`parsing` keep pagination, network fetching, and source-payload normalization
separate.

Shared type aliases are centralized in `src.config.types`, including ingestion
progress callbacks, search shard strategy names, market-ranking group/sort
options, and generic helper type variables used by ETL modules.
