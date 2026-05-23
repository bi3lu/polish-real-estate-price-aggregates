"""Tests for command-line option parsing and CLI orchestration."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from src.config.globals import DEFAULT_SEARCH_SHARD_STRATEGY, ESTATE_TYPES, VOIVODESHIPS
from src.ingestion.models import RawListingObservation
from src.utils.cli import parse_cli_args, run_cli


def test_parse_cli_args_defaults_to_all_configured_values() -> None:
    options = parse_cli_args([])

    assert set(options.estate_types) == ESTATE_TYPES
    assert set(options.voivodeships) == VOIVODESHIPS
    assert options.workers == 4
    assert options.ignore_checkpoints is False
    assert options.duplicate_page_stop_threshold == 0
    assert options.search_shard_strategy == DEFAULT_SEARCH_SHARD_STRATEGY


def test_parse_cli_args_accepts_repeated_and_comma_separated_filters() -> None:
    options = parse_cli_args(
        [
            "--estate-type",
            "mieszkanie,dom",
            "--estate-type",
            "kawalerka",
            "--voivodeship",
            "mazowieckie,pomorskie",
            "--voivodeship",
            "slaskie",
            "--max-page",
            "3",
            "--threads",
            "2",
        ]
    )

    assert options.estate_types == ("mieszkanie", "dom", "kawalerka")
    assert options.voivodeships == ("mazowieckie", "pomorskie", "slaskie")
    assert options.max_page == 3
    assert options.workers == 2


def test_parse_cli_args_accepts_ignore_checkpoints() -> None:
    options = parse_cli_args(
        [
            "--ignore-checkpoints",
            "--duplicate-page-stop-threshold",
            "2",
            "--shard-strategy",
            "price",
        ]
    )

    assert options.ignore_checkpoints is True
    assert options.duplicate_page_stop_threshold == 2
    assert options.search_shard_strategy == "price"


def test_parse_cli_args_rejects_unknown_values() -> None:
    with pytest.raises(SystemExit):
        parse_cli_args(["--estate-type", "unknown"])


def test_run_cli_calls_ingester_with_selected_filters_and_prints_json(
    tmp_path: Path,
) -> None:
    stdout = StringIO()
    captured_kwargs: dict[str, Any] = {}
    captured_save_kwargs: dict[str, Any] = {}
    source_config_path = _write_source_config(tmp_path)

    def ingester(**kwargs: Any) -> list[RawListingObservation]:
        captured_kwargs.update(kwargs)
        return [
            RawListingObservation(
                external_id="listing-1",
                title="Synthetic First Listing",
                estate_type="mieszkanie",
                voivodeship="mazowieckie",
            )
        ]

    def saver(
        estates: list[RawListingObservation],
        **kwargs: Any,
    ) -> tuple[Path, int]:
        estate_list = list(estates)
        captured_save_kwargs.update(kwargs)
        captured_save_kwargs["estates"] = estate_list
        return Path("data/bronze/estate_snapshot_test.jsonl"), len(estate_list)

    exit_code = run_cli(
        [
            "--estate-type",
            "mieszkanie",
            "--voivodeship",
            "mazowieckie",
            "--max-page",
            "2",
            "--source-config",
            str(source_config_path),
        ],
        ingester=ingester,
        saver=saver,
        validator=lambda: None,
        existing_ids_loader=lambda: {},
        page_checkpoints_loader=lambda: {},
        stdout=stdout,
    )

    assert exit_code == 0
    assert captured_kwargs == {
        "estate_types": ("mieszkanie",),
        "voivodeships": ("mazowieckie",),
        "max_page": 2,
        "workers": 4,
        "existing_external_ids_by_voivodeship": {},
        "start_pages_by_target": {},
        "duplicate_page_stop_threshold": 0,
        "search_shard_strategy": "market-price",
        "progress_callback": captured_kwargs["progress_callback"],
        "sources": captured_kwargs["sources"],
    }
    assert [source.source_id for source in captured_kwargs["sources"]] == ["source_a"]
    assert captured_save_kwargs["estate_types"] == ("mieszkanie",)
    assert captured_save_kwargs["voivodeships"] == ("mazowieckie",)
    assert captured_save_kwargs["max_page"] == 2
    assert captured_save_kwargs["page_checkpoints_by_voivodeship"] == {}
    assert captured_save_kwargs["adapter_types_by_source_id"] == {
        "source_a": "embedded_json_listing_site"
    }
    assert [estate.external_id for estate in captured_save_kwargs["estates"]] == [
        "listing-1"
    ]
    assert json.loads(stdout.getvalue()) == {
        "output_path": "data/bronze/estate_snapshot_test.jsonl",
        "count": 1,
        "estate_types": ["mieszkanie"],
        "voivodeships": ["mazowieckie"],
        "workers": 4,
        "ignore_checkpoints": False,
        "duplicate_page_stop_threshold": 0,
        "search_shard_strategy": "market-price",
        "source_ids": ["source_a"],
    }


def test_run_cli_can_ignore_saved_page_checkpoints(tmp_path: Path) -> None:
    captured_kwargs: dict[str, Any] = {}
    source_config_path = _write_source_config(tmp_path)

    def ingester(**kwargs: Any) -> list[RawListingObservation]:
        captured_kwargs.update(kwargs)
        return []

    exit_code = run_cli(
        [
            "--estate-type",
            "mieszkanie",
            "--voivodeship",
            "mazowieckie",
            "--ignore-checkpoints",
            "--source-config",
            str(source_config_path),
        ],
        ingester=ingester,
        saver=lambda estates, **kwargs: (Path("manifest.json"), 0),
        validator=lambda: None,
        existing_ids_loader=lambda: {},
        page_checkpoints_loader=lambda: {
            "mazowieckie": {
                "mieszkanie": 74,
            }
        },
        stdout=StringIO(),
    )

    assert exit_code == 0
    assert captured_kwargs["start_pages_by_target"] == {}
    assert captured_kwargs["duplicate_page_stop_threshold"] == 0
    assert captured_kwargs["search_shard_strategy"] == "market-price"


def _write_source_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(
        """
sources:
  - source_id: source_a
    adapter_type: embedded_json_listing_site
    enabled: true
    base_url: "https://example-listing-site.local"
    search_url_template: "https://example-listing-site.local/search?page={page}"
    rate_limit_seconds: 5
    max_pages_default: 3
    allowed_offer_types:
      - sale
    allowed_property_types:
      - apartment
""",
        encoding="utf-8",
    )
    return config_path
