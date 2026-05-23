# Component Diagram

```mermaid
flowchart LR
    app[src.app]
    cli[src.utils.cli]
    config[src.config<br/>env.py + globals.py]
    ingestion_facade[src.ingestion<br/>estate_ingestion.py facade]
    ingestion_pipeline[src.ingestion.pipeline<br/>pagination + workers]
    ingestion_transport[src.ingestion.transport<br/>HTTP + Next.js payloads]
    ingestion_parsing[src.ingestion.parsing<br/>listing/detail mapping]
    storage[src.utils.storage]
    logger[src.utils.logger]
    models[src.models<br/>Pydantic schemas]
    silver[src.etl.silver]
    gold[src.etl.gold]
    public[src.etl.public]
    analytics[src.analytics.market_ranking]
    tests[tests]

    app --> cli
    cli --> config
    cli --> ingestion_facade
    cli --> storage
    cli --> logger

    ingestion_facade --> ingestion_pipeline
    ingestion_facade --> ingestion_parsing
    ingestion_facade --> ingestion_transport

    ingestion_pipeline --> config
    ingestion_pipeline --> models
    ingestion_pipeline --> logger
    ingestion_pipeline --> ingestion_parsing
    ingestion_pipeline --> ingestion_transport

    ingestion_transport --> config
    ingestion_transport --> logger

    ingestion_parsing --> config
    ingestion_parsing --> models
    ingestion_parsing --> logger

    storage --> models
    storage --> config
    storage --> logger

    silver --> storage
    silver --> models
    silver --> config
    silver --> logger

    gold --> models
    gold --> config
    gold --> logger

    public --> models
    public --> config
    public --> logger

    analytics --> config
    analytics --> logger

    tests -. verify .-> cli
    tests -. verify .-> ingestion_facade
    tests -. verify .-> ingestion_pipeline
    tests -. verify .-> ingestion_transport
    tests -. verify .-> ingestion_parsing
    tests -. verify .-> storage
    tests -. verify .-> silver
    tests -. verify .-> gold
    tests -. verify .-> public
    tests -. verify .-> analytics
```

The ingestion package is split into focused modules: `transport` handles HTTP
and embedded Next.js payload extraction, `parsing` converts raw listing/detail
payloads into `Estate` models, and `pipeline` owns pagination, resume behavior,
and threaded streaming. `estate_ingestion.py` remains as a compatibility facade
for existing imports.

The project keeps source-specific ingestion, storage, ETL transformations, and
data models separated so each layer can be tested independently.
