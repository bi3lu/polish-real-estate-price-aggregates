"""Source adapter registry and factory helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from src.config.source_config import SourceConfig, SourceDefinition
from src.ingestion.adapters.base import (
    EmbeddedJsonListingSourceAdapter,
    HtmlListingSourceAdapter,
    PaginatedListingSourceAdapter,
    SourceAdapter,
    TextFetcher,
)

AdapterClass = type[PaginatedListingSourceAdapter]

ADAPTER_REGISTRY: dict[str, AdapterClass] = {
    "html_listing_site": HtmlListingSourceAdapter,
    "embedded_json_listing_site": EmbeddedJsonListingSourceAdapter,
    "paginated_listing_site": PaginatedListingSourceAdapter,
}


def build_adapters(
    configs: SourceConfig | Iterable[SourceDefinition],
    *,
    property_types: Iterable[str] | None = None,
    voivodeships: Iterable[str] | None = None,
    max_pages: int | None = None,
    fetcher: TextFetcher | None = None,
    detail_fetcher: TextFetcher | None = None,
    query_params: Mapping[str, str] | None = None,
    processed_at: datetime | None = None,
) -> tuple[SourceAdapter, ...]:
    """Build enabled adapters from validated source configuration."""
    source_configs = _resolve_source_configs(configs)
    adapters: list[SourceAdapter] = []

    for source_config in source_configs:
        adapter_class = ADAPTER_REGISTRY.get(source_config.adapter_type)

        if adapter_class is None:
            registered_types = ", ".join(sorted(ADAPTER_REGISTRY))
            raise ValueError(
                f"Unknown adapter_type '{source_config.adapter_type}' for "
                f"source_id '{source_config.source_id}'. Registered adapter "
                f"types: {registered_types}"
            )

        adapters.append(
            adapter_class(
                config=source_config,
                property_types=tuple(property_types or ()),
                voivodeships=tuple(voivodeships or ()),
                max_pages=max_pages,
                fetcher=fetcher,
                detail_fetcher=detail_fetcher,
                query_params=query_params,
                processed_at=processed_at,
            )
        )

    return tuple(adapters)


def _resolve_source_configs(
    configs: SourceConfig | Iterable[SourceDefinition],
) -> tuple[SourceDefinition, ...]:
    if isinstance(configs, SourceConfig):
        return configs.enabled_sources()

    return tuple(config for config in configs if config.enabled)
