# Ingestion Sequence

```mermaid
sequenceDiagram
    actor User
    participant Main as main.py
    participant CLI as src.utils.cli
    participant Config as src.config.source_config
    participant Store as src.utils.storage
    participant Facade as src.ingestion.estate_ingestion
    participant Pipeline as src.ingestion.pipeline
    participant Transport as src.ingestion.transport
    participant Parsing as src.ingestion.parsing
    participant Source as Listing service
    participant Bronze as data/bronze

    User->>Main: uv run python main.py
    Main->>CLI: main(args)
    CLI->>Config: load and validate sources YAML
    CLI->>Store: load existing external ids
    Store-->>CLI: ids by voivodeship
    CLI->>Store: load page checkpoints
    Store-->>CLI: last completed pages
    CLI->>Facade: iter_estates(...)
    Facade->>Pipeline: delegate streaming ingestion

    loop source x estate type x voivodeship x shard x page
        Pipeline->>Transport: fetch listing page
        Transport->>Source: HTTP request
        Source-->>Transport: JSON or embedded Next.js payload
        Transport-->>Pipeline: parsed payload
        Pipeline->>Parsing: extract listing items
        Pipeline->>Transport: fetch listing detail page when available
        Transport->>Source: HTTP request
        Source-->>Transport: detail payload
        Transport-->>Pipeline: parsed detail payload
        Pipeline->>Parsing: map listing/detail payload to RawListingObservation
        Pipeline-->>Facade: raw observations
        Facade-->>CLI: raw observations
    end

    CLI->>Store: stream_estates_to_bronze(...)
    Store->>Bronze: append source-id/run-id JSONL records
    Store->>Bronze: write per-run manifests and checkpoints
    Store-->>CLI: output path and new record count
    CLI-->>User: JSON summary
```

The ingestion flow is resumable. Existing external ids prevent duplicate writes,
and page checkpoints allow later runs to continue from the last completed target.
The public import surface remains `src.ingestion.estate_ingestion`, but the
runtime work is delegated to smaller modules for transport, parsing, and
pagination/thread orchestration.

Pass `--ignore-checkpoints` to force selected targets to start from page 1 while
still deduplicating records already present in bronze storage. This is useful
for periodic refresh runs when new listings may have appeared before the saved
checkpoint.

Resume and refresh runs stop on duplicate-only pages only when explicitly
requested. The default threshold is `0`, which keeps scanning through
duplicate-only pages during backfills; tune it with
`--duplicate-page-stop-threshold` for smaller refresh windows. The pipeline
still stops when the source starts returning an already-seen listing page
signature, which protects against clamped or looping pagination.

Large source searches can be split with `--shard-strategy`. The CLI defaults to
`market-price`, creating independent market and price-range targets with their
own page checkpoints. This makes long regional runs easier to resume after a
403 or interruption and avoids relying on a single broad result set.

The transport layer treats `403` and `429` responses as source throttling. When
that happens it enters a shared cooldown, honors `Retry-After` when present, and
retries the blocked request with exponential backoff and jitter. The cooldown is
shared across worker threads, so one blocked request slows the whole scraper
instead of letting parallel workers keep hammering the source.
