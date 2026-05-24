"""Neutral source adapters for listing ingestion."""

from src.ingestion.adapters.base import (
    EmbeddedJsonListingSourceAdapter,
    HtmlListingSourceAdapter,
    PaginatedListingSourceAdapter,
    SourceAdapter,
)

__all__ = [
    "EmbeddedJsonListingSourceAdapter",
    "HtmlListingSourceAdapter",
    "PaginatedListingSourceAdapter",
    "SourceAdapter",
]
