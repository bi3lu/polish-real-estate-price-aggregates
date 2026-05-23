"""Global types for the project."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, TypeVar

#######################################################################################
# Market ranking types:
#######################################################################################

OutputFormat = Literal["table", "json", "csv"]

GroupBy = Literal[
    "voivodeship",
    "city",
    "estate_type",
    "voivodeship_city",
    "voivodeship_estate_type",
]

SortBy = Literal[
    "records_count",
    "median_price_per_sqm_pln",
    "avg_price_per_sqm_pln",
    "median_price_pln",
    "share_with_price_per_sqm",
]

#######################################################################################
# Ingestion pipeline types:
#######################################################################################

SearchShardStrategy = Literal["none", "price", "market-price"]
IngestionProgressCallback = Callable[[str, str, int], None]

#######################################################################################
# Helper type:
#######################################################################################

T = TypeVar("T")
