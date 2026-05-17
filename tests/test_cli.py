from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from src.config.globals import ESTATE_TYPES, VOIVODESHIPS
from src.models.estate import Estate
from src.utils.cli import parse_cli_args, run_cli


def test_parse_cli_args_defaults_to_all_configured_values() -> None:
    options = parse_cli_args([])

    assert set(options.estate_types) == ESTATE_TYPES
    assert set(options.voivodeships) == VOIVODESHIPS
    assert options.workers == 4


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


def test_parse_cli_args_rejects_unknown_values() -> None:
    with pytest.raises(SystemExit):
        parse_cli_args(["--estate-type", "unknown"])


def test_run_cli_calls_scraper_with_selected_filters_and_prints_json() -> None:
    stdout = StringIO()
    captured_kwargs: dict[str, Any] = {}
    captured_save_kwargs: dict[str, Any] = {}

    def scraper(**kwargs: Any) -> list[Estate]:
        captured_kwargs.update(kwargs)
        return [
            Estate(
                external_id="listing-1",
                title="Pierwsza oferta",
                estate_type="mieszkanie",
                voivodeship="mazowieckie",
            )
        ]

    def saver(estates: list[Estate], **kwargs: Any) -> tuple[Path, int]:
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
        ],
        scraper=scraper,
        saver=saver,
        validator=lambda: None,
        stdout=stdout,
    )

    assert exit_code == 0
    assert captured_kwargs == {
        "estate_types": ("mieszkanie",),
        "voivodeships": ("mazowieckie",),
        "max_page": 2,
        "workers": 4,
    }
    assert captured_save_kwargs["estate_types"] == ("mieszkanie",)
    assert captured_save_kwargs["voivodeships"] == ("mazowieckie",)
    assert captured_save_kwargs["max_page"] == 2
    assert [estate.external_id for estate in captured_save_kwargs["estates"]] == [
        "listing-1"
    ]
    assert json.loads(stdout.getvalue()) == {
        "output_path": "data/bronze/estate_snapshot_test.jsonl",
        "count": 1,
        "estate_types": ["mieszkanie"],
        "voivodeships": ["mazowieckie"],
        "workers": 4,
    }
