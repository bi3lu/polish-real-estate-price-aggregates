# Ingestion Sequence

```mermaid
sequenceDiagram
    actor User
    participant Main as main.py
    participant CLI as src.utils.cli
    participant Config as src.config.source_config
    participant Registry as src.ingestion.registry
    participant Adapter as SourceAdapter
    participant Sharding as src.ingestion.sharding
    participant Pipeline as src.ingestion.pipeline
    participant Transport as src.ingestion.transport
    participant Parsing as src.ingestion.parsing
    participant Storage as src.utils.storage
    participant Bronze as data/bronze
    participant Source as Configured source

    User->>Main: uv run python main.py
    Main->>CLI: main(args)
    CLI->>Config: load sources YAML
    Config-->>CLI: validated SourceConfig
    CLI->>Registry: build_adapters(config)
    Registry-->>CLI: enabled neutral adapters
    CLI->>Storage: load existing ids and checkpoints
    Storage-->>CLI: resume metadata
    CLI->>Pipeline: iter_estates(..., sources=adapters)
    Pipeline->>Sharding: build canonical SearchShard values

    loop source x property type x voivodeship x shard x page
        Pipeline->>Adapter: source metadata and config
        Pipeline->>Adapter: translate canonical shard to query params
        Pipeline->>Transport: fetch listing URL
        Transport->>Source: HTTP request with pacing
        Source-->>Transport: JSON or HTML with embedded state
        Transport-->>Pipeline: parsed mapping
        Pipeline->>Parsing: extract listing items
        Pipeline->>Parsing: get RawListingObservation
        Parsing-->>Pipeline: neutral raw observation
        Pipeline-->>CLI: stream observation
    end

    CLI->>Storage: stream_estates_to_bronze(...)
    Storage->>Bronze: write source_id/run_id observations
    Storage->>Bronze: write per-run manifest
    Storage->>Bronze: update root manifest and checkpoints
    Storage-->>CLI: manifest path and count
    CLI-->>User: JSON summary
```

## Resume Behavior

Ingestion is resumable:

- existing bronze ids prevent duplicate writes,
- page checkpoints track the last completed page per target,
- `--ignore-checkpoints` restarts selected targets from page 1 while still
  deduplicating existing records,
- repeated listing page signatures stop looping pagination,
- `--duplicate-page-stop-threshold` can stop refresh runs after repeated
  duplicate-only pages.

## Sharding

`--shard-strategy` can split broad searches into independent targets:

- `none`
- `price`
- `market-price`

Each shard has its own checkpoint key, which makes long collection runs easier
to resume.

Shard definitions are canonical. They carry values such as `price_to=300000` or
`market=primary`; adapter code translates them to source-specific URL query
parameters.

## Source-Specific Behavior Without Brand Classes

The pipeline receives `SourceAdapter` instances built from config. It uses
`source_id`, `adapter_type`, rate limits, page caps, and property type mappings,
but it does not need to know the real source name.

`html_listing_site` sources are parsed from listing pages and skip detail-page
enrichment by default when detail pages do not expose a stable embedded detail
object.
