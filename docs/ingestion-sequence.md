# Ingestion Sequence

```mermaid
sequenceDiagram
    actor User
    participant Main as main.py
    participant CLI as src.utils.cli
    participant Env as src.config.env
    participant Store as src.utils.storage
    participant Facade as src.ingestion.estate_ingestion
    participant Pipeline as src.ingestion.pipeline
    participant Transport as src.ingestion.transport
    participant Parsing as src.ingestion.parsing
    participant Source as Listing service
    participant Bronze as data/bronze

    User->>Main: uv run python main.py
    Main->>CLI: main(args)
    CLI->>Env: validate MAIN_URL and ESTATE_URL
    CLI->>Store: load existing external ids
    Store-->>CLI: ids by voivodeship
    CLI->>Store: load page checkpoints
    Store-->>CLI: last completed pages
    CLI->>Facade: iter_estates(...)
    Facade->>Pipeline: delegate streaming ingestion

    loop estate type x voivodeship x page
        Pipeline->>Transport: fetch listing page
        Transport->>Source: HTTP request
        Source-->>Transport: JSON or embedded Next.js payload
        Transport-->>Pipeline: parsed payload
        Pipeline->>Parsing: extract listing items
        Pipeline->>Transport: fetch listing detail page when available
        Transport->>Source: HTTP request
        Source-->>Transport: detail payload
        Transport-->>Pipeline: parsed detail payload
        Pipeline->>Parsing: map listing/detail payload to Estate
        Pipeline-->>Facade: Estate records
        Facade-->>CLI: Estate records
    end

    CLI->>Store: stream_estates_to_bronze(...)
    Store->>Bronze: append per-voivodeship JSONL records
    Store->>Bronze: update manifest and checkpoints
    Store-->>CLI: output path and new record count
    CLI-->>User: JSON summary
```

The ingestion flow is resumable. Existing external ids prevent duplicate writes,
and page checkpoints allow later runs to continue from the last completed target.
The public import surface remains `src.ingestion.estate_ingestion`, but the
runtime work is delegated to smaller modules for transport, parsing, and
pagination/thread orchestration.
