"""Tests for source-neutral search sharding."""

from __future__ import annotations

from src.ingestion.sharding import build_search_shards, default_shard_query_params


def test_price_shards_are_canonical_until_adapter_translation() -> None:
    shards = build_search_shards("price")

    assert shards[0].key == "price-lt-300k"
    assert shards[0].price_from is None
    assert shards[0].price_to == 300000
    assert shards[0].market is None
    assert not hasattr(shards[0], "query_params")


def test_default_shard_query_params_translates_canonical_filters() -> None:
    shard = build_search_shards("market-price")[0]

    assert shard.market == "primary"
    assert default_shard_query_params(shard) == {
        "search[filter_enum_market][0]": "primary",
        "search[filter_float_price:to]": "300000",
    }
