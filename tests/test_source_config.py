"""Tests for dynamic source configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.source_config import SourceConfig, load_source_config


def test_load_source_config_reads_enabled_sources_from_yaml(tmp_path: Path) -> None:
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

  - source_id: source_b
    adapter_type: html_listing_site
    enabled: false
    base_url: "https://example-listing-site-2.local"
    search_url_template: "https://example-listing-site-2.local/offers?page={page}"
    rate_limit_seconds: 8
    max_pages_default: 3
    allowed_offer_types:
      - sale
    allowed_property_types:
      - apartment
""",
        encoding="utf-8",
    )

    config = load_source_config(config_path)

    assert [source.source_id for source in config.sources] == ["source_a", "source_b"]
    assert [source.source_id for source in config.enabled_sources()] == ["source_a"]
    assert config.sources[0].rate_limit_seconds == 5
    assert config.sources[0].max_pages_default == 3
    assert config.sources[0].allowed_offer_types == ("sale",)
    assert config.sources[0].allowed_property_types == ("apartment",)
    assert config.sources[0].property_type_mapping == {}


def test_source_config_rejects_duplicate_source_ids() -> None:
    with pytest.raises(ValidationError, match="source_id values must be unique"):
        SourceConfig.model_validate(
            {
                "sources": [
                    _source_payload("source_a"),
                    _source_payload("source_a"),
                ]
            }
        )


def test_source_config_rejects_search_template_without_page() -> None:
    payload = _source_payload("source_a")
    payload["search_url_template"] = "https://example-listing-site.local/search"

    with pytest.raises(ValidationError, match="include a \\{page\\} placeholder"):
        SourceConfig.model_validate({"sources": [payload]})


def test_source_config_rejects_negative_rate_limit() -> None:
    payload = _source_payload("source_a")
    payload["rate_limit_seconds"] = -1

    with pytest.raises(ValidationError):
        SourceConfig.model_validate({"sources": [payload]})


def test_source_config_requires_rate_limit_seconds() -> None:
    payload = _source_payload("source_a")
    payload.pop("rate_limit_seconds")

    with pytest.raises(ValidationError):
        SourceConfig.model_validate({"sources": [payload]})


def test_source_config_applies_safe_defaults() -> None:
    payload = _source_payload("source_a")
    payload.pop("max_pages_default")
    payload.pop("respect_robots_txt", None)

    config = SourceConfig.model_validate({"sources": [payload]})

    assert config.sources[0].max_pages_default == 3
    assert config.sources[0].respect_robots_txt is True


def test_source_config_supports_property_type_mapping() -> None:
    payload = _source_payload("source_a")
    payload["property_type_mapping"] = {
        "apartment": "apartments",
        "house": "houses",
    }

    config = SourceConfig.model_validate({"sources": [payload]})
    source = config.sources[0]

    assert source.source_property_type("apartment") == "apartments"
    assert source.source_property_type("house") == "houses"
    assert source.source_property_type("studio") == "studio"


def test_source_config_rejects_invalid_property_type_mapping() -> None:
    payload = _source_payload("source_a")
    payload["property_type_mapping"] = ["apartment"]

    with pytest.raises(ValidationError, match="property_type_mapping"):
        SourceConfig.model_validate({"sources": [payload]})


def _source_payload(source_id: str) -> dict[str, object]:
    return {
        "source_id": source_id,
        "adapter_type": "embedded_json_listing_site",
        "enabled": True,
        "base_url": "https://example-listing-site.local",
        "search_url_template": "https://example-listing-site.local/search?page={page}",
        "rate_limit_seconds": 5,
        "max_pages_default": 3,
        "allowed_offer_types": ["sale"],
        "allowed_property_types": ["apartment"],
    }
