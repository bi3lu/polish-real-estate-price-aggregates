"""Tests for dynamic source adapter registry."""

from __future__ import annotations

import pytest

from src.config.source_config import SourceDefinition
from src.ingestion.adapters.base import (
    EmbeddedJsonListingSourceAdapter,
    HtmlListingSourceAdapter,
    PaginatedListingSourceAdapter,
)
from src.ingestion.registry import ADAPTER_REGISTRY, build_adapters


def test_adapter_registry_contains_neutral_adapter_types() -> None:
    assert ADAPTER_REGISTRY == {
        "html_listing_site": HtmlListingSourceAdapter,
        "embedded_json_listing_site": EmbeddedJsonListingSourceAdapter,
        "paginated_listing_site": PaginatedListingSourceAdapter,
    }


def test_build_adapters_uses_enabled_source_configs() -> None:
    adapters = build_adapters(
        (
            _source_definition("source_a", "embedded_json_listing_site", True),
            _source_definition("source_b", "html_listing_site", False),
        ),
        property_types=("mieszkanie",),
        voivodeships=("mazowieckie",),
        max_pages=2,
    )

    assert len(adapters) == 1
    assert isinstance(adapters[0], EmbeddedJsonListingSourceAdapter)
    assert adapters[0].source_id == "source_a"
    assert adapters[0].build_search_urls() == [
        "https://example-listing-site.local/search"
        "?property=mieszkanie&region=mazowieckie&page=1",
        "https://example-listing-site.local/search"
        "?property=mieszkanie&region=mazowieckie&page=2",
    ]


def test_build_adapters_fails_clearly_for_unknown_adapter_type() -> None:
    with pytest.raises(ValueError) as exc_info:
        build_adapters(
            (
                _source_definition(
                    "source_unknown",
                    "unknown_listing_site",
                    True,
                ),
            )
        )

    assert str(exc_info.value) == (
        "Unknown adapter_type 'unknown_listing_site' for source_id "
        "'source_unknown'. Registered adapter types: embedded_json_listing_site, "
        "html_listing_site, paginated_listing_site"
    )


def _source_definition(
    source_id: str,
    adapter_type: str,
    enabled: bool,
) -> SourceDefinition:
    return SourceDefinition(
        source_id=source_id,
        adapter_type=adapter_type,
        enabled=enabled,
        base_url="https://example-listing-site.local",
        search_url_template=(
            "https://example-listing-site.local/search"
            "?property={property_type}&region={voivodeship}&page={page}"
        ),
        rate_limit_seconds=0,
        max_pages_default=3,
        allowed_offer_types=("sale",),
        allowed_property_types=("apartment",),
    )
