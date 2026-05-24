# Documentation

This directory contains architecture notes and Mermaid diagrams for the current
source-neutral ingestion and ETL pipeline.

## Contents

- [System Context](system-context.md) - actors, local source config, private
  storage, public exports, and CI.
- [Source Configuration](source-configuration.md) - YAML source definitions,
  adapter registry, property type mapping, and local/private config rules.
- [Data Pipeline](data-pipeline.md) - bronze, silver, gold, public, and
  analytics layers.
- [Component Diagram](component-diagram.md) - Python modules and their
  dependencies.
- [Ingestion Sequence](ingestion-sequence.md) - CLI ingestion, dynamic adapter
  creation, pagination, sharding, and manifests.
- [ETL Sequence](etl-sequence.md) - bronze to silver to gold to public.
- [Data Model Overview](data-model-overview.md) - neutral domain models and
  downstream table groups.
- [Market Ranking CLI](market-ranking.md) - analytical rankings from public
  exports.
- [Ethics and Responsible Collection](ethics.md) - rules for low-impact,
  lawful, non-evasive collection.

GitHub renders Mermaid blocks directly in Markdown files.
