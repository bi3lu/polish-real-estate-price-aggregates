# Project Diagrams

This directory contains Mermaid diagrams describing the main architecture and
runtime flows of the Polish Real Estate Price Aggregates project.

## Diagrams

- [System Context](system-context.md) - high-level actors, source service, local
  pipeline, and public outputs.
- [Data Pipeline](data-pipeline.md) - bronze, silver, gold, and public data
  layers.
- [Component Diagram](component-diagram.md) - main Python packages and their
  dependencies.
- [Ingestion Sequence](ingestion-sequence.md) - command-line ingestion flow with
  resume checkpoints.
- [ETL Sequence](etl-sequence.md) - transformation flow from bronze to public
  datasets.
- [Data Model Overview](data-model-overview.md) - core Pydantic models and
  generated table groups.

GitHub renders Mermaid blocks directly in Markdown files.
