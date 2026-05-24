# Component Diagram

```mermaid
flowchart LR
    app[src.app]
    cli[src.utils.cli]
    source_config[src.config.source_config<br/>YAML loading + Pydantic validation]
    globals[src.config.globals<br/>project constants]
    types[src.config.types<br/>shared aliases]

    registry[src.ingestion.registry<br/>adapter registry]
    adapters[src.ingestion.adapters.base<br/>SourceAdapter protocol<br/>neutral adapters]
    sharding[src.ingestion.sharding<br/>canonical SearchShard]
    pipeline[src.ingestion.pipeline<br/>pagination + sharding + workers]
    transport[src.ingestion.transport<br/>HTTP + embedded JSON extraction]
    parsing[src.ingestion.parsing<br/>payload to raw observation]
    ingestion_models[src.ingestion.models<br/>RawListingObservation<br/>CanonicalListing<br/>SourceRun]
    facade[src.ingestion.estate_ingestion<br/>compatibility facade]

    storage[src.utils.storage<br/>bronze manifests + partitions]
    silver[src.etl.silver<br/>CanonicalListing normalization]
    gold[src.etl.gold]
    public[src.etl.public]
    analytics[src.analytics.market_ranking]
    tests[tests<br/>synthetic offline fixtures]

    app --> cli
    cli --> source_config
    cli --> registry
    cli --> storage
    cli --> facade

    source_config --> globals
    registry --> adapters
    registry --> source_config

    facade --> pipeline
    pipeline --> sharding
    pipeline --> transport
    pipeline --> parsing
    pipeline --> ingestion_models
    pipeline --> types
    pipeline --> adapters
    adapters --> transport
    adapters --> sharding
    adapters --> parsing
    adapters --> ingestion_models
    parsing --> ingestion_models

    storage --> ingestion_models
    silver --> storage
    silver --> ingestion_models
    gold --> ingestion_models
    public --> ingestion_models
    analytics --> globals

    tests -. verify .-> source_config
    tests -. verify .-> registry
    tests -. verify .-> adapters
    tests -. verify .-> pipeline
    tests -. verify .-> transport
    tests -. verify .-> parsing
    tests -. verify .-> storage
    tests -. verify .-> silver
    tests -. verify .-> gold
    tests -. verify .-> public
```

The ingestion layer is source-neutral. `registry.py` builds adapters from YAML
config, `adapters/base.py` provides reusable technical adapters, and
`pipeline.py` handles orchestration without knowing a real source brand.

Downstream private ETL consumes `CanonicalListing` records produced from neutral
`RawListingObservation` inputs. Public exports use a separate public schema.
