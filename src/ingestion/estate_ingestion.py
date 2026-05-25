"""Compatibility facade for real estate ingestion utilities."""

from __future__ import annotations

from src.config.types import IngestionProgressCallback
from src.ingestion.models import (
    CanonicalListing,
    RawListingObservation,
    SourceQualityStats,
    SourceRun,
    SourceRunStats,
)
from src.ingestion.parsing import (
    extract_estate_detail,
    extract_listing_items,
    get_estate_info,
)
from src.ingestion.pipeline import (
    ingest_canonical_listings,
    ingest_estates,
    ingest_estates_for,
    iter_canonical_listings,
    iter_estates,
    iter_estates_for,
    iter_estates_threaded,
)
from src.ingestion.sharding import SearchShard, build_search_shards
from src.ingestion.transport import (
    RequestThrottle,
    SourceBlockedError,
    build_listing_url,
    extract_next_data_from_html,
    fetch_next_data_json,
)
from src.utils.logger import get_logger

__all__ = [
    "IngestionProgressCallback",
    "RequestThrottle",
    "SearchShard",
    "SourceBlockedError",
    "build_listing_url",
    "build_search_shards",
    "extract_estate_detail",
    "extract_listing_items",
    "extract_next_data_from_html",
    "fetch_next_data_json",
    "get_estate_info",
    "ingest_canonical_listings",
    "ingest_estates",
    "ingest_estates_for",
    "iter_canonical_listings",
    "iter_estates",
    "iter_estates_for",
    "iter_estates_threaded",
    "CanonicalListing",
    "RawListingObservation",
    "SourceQualityStats",
    "SourceRun",
    "SourceRunStats",
]

logger = get_logger(__name__)


if __name__ == "__main__":
    ingested_estates = ingest_estates()
    logger.info("Ingested %s estates", len(ingested_estates))
