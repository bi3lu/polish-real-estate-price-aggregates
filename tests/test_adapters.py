"""Tests for neutral source adapters with synthetic fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.config.source_config import SourceDefinition
from src.ingestion.adapters.base import (
    EmbeddedJsonListingSourceAdapter,
    HtmlListingSourceAdapter,
    PaginatedListingSourceAdapter,
)
from src.ingestion.models import CanonicalListing
from src.ingestion.pipeline import ingest_canonical_listings

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "sources"


def test_embedded_json_adapter_parses_and_normalizes_listing_fixture() -> None:
    adapter = EmbeddedJsonListingSourceAdapter(
        config=_source_definition("embedded_json_listing_site"),
        property_types=("mieszkanie",),
        voivodeships=("mazowieckie",),
        max_pages=1,
        fetcher=lambda url: _fixture_text("source_a", "listing_payload.json"),
        processed_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
    )

    listings = ingest_canonical_listings((adapter,))

    assert len(listings) == 1
    assert isinstance(listings[0], CanonicalListing)
    assert listings[0].record_id == "source_a:listing-a-json-001"
    assert listings[0].source_id == "source_a"
    assert listings[0].external_id == "listing-a-json-001"
    assert listings[0].estate_type == "mieszkanie"
    assert listings[0].voivodeship == "mazowieckie"
    assert listings[0].price_pln == 750000
    assert listings[0].price_per_sqm_pln == 15000
    assert listings[0].area_sqm == 50
    assert listings[0].rooms == 3
    assert listings[0].city == "Example City"
    assert listings[0].district == "Example District"
    assert listings[0].location == "Example Street, Example District, Example City"


def test_html_adapter_extracts_embedded_next_data_fixture() -> None:
    adapter = HtmlListingSourceAdapter(
        config=_source_definition("html_listing_site"),
        property_types=("mieszkanie",),
        voivodeships=("mazowieckie",),
        max_pages=1,
        fetcher=lambda url: _fixture_text("source_b", "search_page.html"),
        processed_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
    )

    listings = ingest_canonical_listings((adapter,))

    assert len(listings) == 1
    assert listings[0].record_id == "source_a:listing-b-001"
    assert listings[0].title == "Synthetic HTML Listing"
    assert listings[0].city == "Example Harbor"


def test_paginated_adapter_builds_configured_search_urls() -> None:
    adapter = PaginatedListingSourceAdapter(
        config=_source_definition("paginated_listing_site"),
        property_types=("mieszkanie",),
        voivodeships=("mazowieckie", "pomorskie"),
        max_pages=2,
    )

    assert adapter.build_search_urls() == [
        "https://example-listing-site.local/search"
        "?property=mieszkanie&region=mazowieckie&page=1",
        "https://example-listing-site.local/search"
        "?property=mieszkanie&region=mazowieckie&page=2",
        "https://example-listing-site.local/search"
        "?property=mieszkanie&region=pomorskie&page=1",
        "https://example-listing-site.local/search"
        "?property=mieszkanie&region=pomorskie&page=2",
    ]


def _fixture_text(source_id: str, filename: str) -> str:
    return (FIXTURE_ROOT / source_id / filename).read_text(encoding="utf-8")


def _source_definition(adapter_type: str) -> SourceDefinition:
    return SourceDefinition(
        source_id="source_a",
        adapter_type=adapter_type,
        enabled=True,
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
