"""Neutral source adapter interfaces and reusable listing-site adapters."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, cast

from src.config.source_config import SourceDefinition
from src.etl.silver import normalize_estate
from src.ingestion.models import CanonicalListing, RawListingObservation
from src.ingestion.parsing import (
    enrich_listing_item,
    extract_listing_items,
    get_estate_info,
)
from src.ingestion.transport import (
    build_listing_url,
    extract_next_data_from_html,
    extract_prerendered_state_from_html,
)

TextFetcher = Callable[[str], str]


class SourceAdapter(Protocol):
    """Common contract implemented by all listing source adapters."""

    @property
    def source_id(self) -> str: ...

    def build_search_urls(self) -> list[str]: ...

    def fetch(self, url: str) -> str: ...

    def parse(self, payload: str) -> list[RawListingObservation]: ...

    def normalize(
        self,
        observations: list[RawListingObservation],
    ) -> list[CanonicalListing]: ...


@dataclass(frozen=True)
class _SearchContext:
    property_type: str | None
    voivodeship: str | None


@dataclass
class PaginatedListingSourceAdapter:
    """Generic paginated listing-site adapter."""

    config: SourceDefinition
    property_types: tuple[str, ...] = ()
    voivodeships: tuple[str, ...] = ()
    max_pages: int | None = None
    fetcher: TextFetcher | None = None
    detail_fetcher: TextFetcher | None = None
    query_params: Mapping[str, str] | None = None
    processed_at: datetime | None = None
    _context_by_url: dict[str, _SearchContext] = field(
        init=False,
        default_factory=dict,
    )
    _active_context: _SearchContext | None = field(init=False, default=None)

    @property
    def source_id(self) -> str:
        return self.config.source_id

    def build_search_urls(self) -> list[str]:
        """Build all configured search URLs and remember their target context."""
        urls: list[str] = []
        self._context_by_url = {}
        max_page = self.max_pages or self.config.max_pages_default
        property_types = self.property_types or self.config.allowed_property_types
        selected_property_types = property_types or ("",)
        selected_voivodeships = self.voivodeships or ("",)

        for property_type in selected_property_types:
            normalized_property_type = property_type or None

            for voivodeship in selected_voivodeships:
                normalized_voivodeship = voivodeship or None

                for page in range(1, max_page + 1):
                    url = build_listing_url(
                        normalized_property_type or "",
                        normalized_voivodeship or "",
                        page=page,
                        query_params=self.query_params,
                        source=self.config,
                    )
                    urls.append(url)
                    self._context_by_url[url] = _SearchContext(
                        property_type=normalized_property_type,
                        voivodeship=normalized_voivodeship,
                    )

        return urls

    def fetch(self, url: str) -> str:
        """Fetch one URL as text."""
        self._active_context = self._context_by_url.get(url)

        if self.fetcher is not None:
            return self.fetcher(url)

        return _fetch_url_text(url)

    def parse(self, payload: str) -> list[RawListingObservation]:
        """Parse a listing payload into raw source observations."""
        payload_json = _payload_to_mapping(payload)
        listing_items = extract_listing_items(payload_json)
        observations: list[RawListingObservation] = []

        for listing_item in listing_items:
            enriched_item = enrich_listing_item(
                listing_item,
                detail_fetcher=(
                    self._fetch_detail_payload
                    if self.detail_fetcher is not None
                    else None
                ),
                detail_base_url=self.config.base_url,
            )
            observation = get_estate_info(
                enriched_item,
                estate_type=(
                    self._active_context.property_type
                    if self._active_context is not None
                    else None
                ),
                voivodeship=(
                    self._active_context.voivodeship
                    if self._active_context is not None
                    else None
                ),
                source_id=self.source_id,
                detail_base_url=self.config.base_url,
            )

            if observation is not None:
                observations.append(observation)

        return observations

    def normalize(
        self,
        observations: list[RawListingObservation],
    ) -> list[CanonicalListing]:
        """Normalize raw observations into canonical listing rows."""
        canonical_listings: list[CanonicalListing] = []

        for observation in observations:
            canonical_listing = normalize_estate(
                observation,
                processed_at=self.processed_at,
            )

            if canonical_listing is not None:
                canonical_listings.append(canonical_listing)

        return canonical_listings

    def _fetch_detail_payload(self, url: str) -> Mapping[str, Any]:
        if self.detail_fetcher is None:
            raise RuntimeError("detail fetcher is disabled")

        return _payload_to_mapping(self.detail_fetcher(url))


class HtmlListingSourceAdapter(PaginatedListingSourceAdapter):
    """Listing adapter for HTML pages with embedded listing data."""


class EmbeddedJsonListingSourceAdapter(PaginatedListingSourceAdapter):
    """Listing adapter for pages or endpoints exposing embedded JSON data."""


def _fetch_url_text(url: str) -> str:
    request = urllib.request.Request(url)

    with urllib.request.urlopen(request) as response:
        response_body = cast(bytes, response.read())
        return response_body.decode("utf-8", errors="replace")


def _payload_to_mapping(payload: str) -> Mapping[str, Any]:
    stripped_payload = payload.lstrip()

    if stripped_payload.startswith("{"):
        parsed_payload = json.loads(stripped_payload)

        if not isinstance(parsed_payload, dict):
            raise ValueError("JSON payload root must be an object")

        return cast(dict[str, Any], parsed_payload)

    try:
        return extract_next_data_from_html(payload)

    except ValueError as exc:
        if "Could not find __NEXT_DATA__" not in str(exc):
            raise

    return extract_prerendered_state_from_html(payload)
