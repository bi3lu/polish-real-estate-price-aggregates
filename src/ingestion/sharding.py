"""Canonical search sharding strategies for ingestion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.config.types import SearchShardStrategy


@dataclass(frozen=True)
class SearchShard:
    """Source-neutral search shard.

    The shard stores canonical filters only. Adapters translate these filters
    into source-specific query parameters.
    """

    key: str
    price_from: int | None = None
    price_to: int | None = None
    market: str | None = None

    @property
    def is_base(self) -> bool:
        return self.price_from is None and self.price_to is None and self.market is None


_BASE_SEARCH_SHARD = SearchShard(key="base")
_PRICE_SHARDS: tuple[SearchShard, ...] = (
    SearchShard(key="price-lt-300k", price_to=300_000),
    SearchShard(key="price-300k-400k", price_from=300_000, price_to=400_000),
    SearchShard(key="price-400k-500k", price_from=400_000, price_to=500_000),
    SearchShard(key="price-500k-600k", price_from=500_000, price_to=600_000),
    SearchShard(key="price-600k-750k", price_from=600_000, price_to=750_000),
    SearchShard(key="price-750k-1000k", price_from=750_000, price_to=1_000_000),
    SearchShard(key="price-1000k-1500k", price_from=1_000_000, price_to=1_500_000),
    SearchShard(key="price-gte-1500k", price_from=1_500_000),
)
_MARKET_SHARDS: tuple[tuple[str, str], ...] = (
    ("market-primary", "primary"),
    ("market-secondary", "secondary"),
)


def build_search_shards(strategy: SearchShardStrategy | str) -> tuple[SearchShard, ...]:
    """Build source-neutral search shards for large result sets."""
    if strategy == "none":
        return (_BASE_SEARCH_SHARD,)

    if strategy == "price":
        return _PRICE_SHARDS

    if strategy == "market-price":
        return tuple(
            SearchShard(
                key=f"{market_key}__{price_shard.key}",
                price_from=price_shard.price_from,
                price_to=price_shard.price_to,
                market=market_value,
            )
            for market_key, market_value in _MARKET_SHARDS
            for price_shard in _PRICE_SHARDS
        )

    raise ValueError(
        "Unsupported search shard strategy: "
        f"{strategy}. Allowed values: none, price, market-price"
    )


def default_shard_query_params(shard: SearchShard) -> Mapping[str, str]:
    """Translate a canonical shard using the generic listing query convention."""
    query_params: dict[str, str] = {}

    if shard.market is not None:
        query_params["search[filter_enum_market][0]"] = shard.market

    if shard.price_from is not None:
        query_params["search[filter_float_price:from]"] = str(shard.price_from)

    if shard.price_to is not None:
        query_params["search[filter_float_price:to]"] = str(shard.price_to)

    return query_params
