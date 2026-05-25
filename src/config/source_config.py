"""Source configuration models and loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.config.globals import PROJECT_ROOT

DEFAULT_SOURCE_CONFIG_DIR = PROJECT_ROOT / "config"
EXAMPLE_SOURCE_CONFIG_PATH = DEFAULT_SOURCE_CONFIG_DIR / "sources.example.yaml"
LOCAL_SOURCE_CONFIG_PATH = DEFAULT_SOURCE_CONFIG_DIR / "sources.local.yaml"

AdapterType = str


class SourceDefinition(BaseModel):
    """Configuration for one logical listing source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    adapter_type: AdapterType
    enabled: bool = True
    base_url: str = Field(min_length=1)
    search_url_template: str = Field(min_length=1)
    rate_limit_seconds: float = Field(ge=0)
    max_pages_default: int = Field(default=3, ge=1)
    respect_robots_txt: bool = True
    allowed_offer_types: tuple[str, ...] = Field(default_factory=tuple)
    allowed_property_types: tuple[str, ...] = Field(default_factory=tuple)
    property_type_mapping: dict[str, str] = Field(default_factory=dict)

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("source_id must not be empty")

        if any(character.isspace() for character in normalized):
            raise ValueError("source_id must not contain whitespace")

        return normalized

    @field_validator("adapter_type")
    @classmethod
    def validate_adapter_type(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("adapter_type must not be empty")

        return normalized

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip()
        parsed_url = urlsplit(normalized)

        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("base_url must be an absolute http(s) URL")

        return normalized

    @field_validator("search_url_template")
    @classmethod
    def validate_search_url_template(cls, value: str) -> str:
        normalized = value.strip()
        parsed_url = urlsplit(normalized)

        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("search_url_template must be an absolute http(s) URL")

        if "{page}" not in normalized:
            raise ValueError("search_url_template must include a {page} placeholder")

        return normalized

    @field_validator("allowed_offer_types", "allowed_property_types", mode="before")
    @classmethod
    def normalize_allowed_values(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, list | tuple):
            raise ValueError("allowed values must be a list")

        normalized_values = tuple(
            str(item).strip() for item in value if str(item).strip()
        )

        if not normalized_values:
            raise ValueError("allowed values must not be empty")

        return normalized_values

    @field_validator("property_type_mapping", mode="before")
    @classmethod
    def normalize_property_type_mapping(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}

        if not isinstance(value, dict):
            raise ValueError("property_type_mapping must be an object")

        normalized_mapping: dict[str, str] = {}

        for raw_key, raw_value in value.items():
            key = str(raw_key).strip()
            mapped_value = str(raw_value).strip()

            if not key or not mapped_value:
                raise ValueError(
                    "property_type_mapping keys and values must not be empty"
                )

            normalized_mapping[key] = mapped_value

        return normalized_mapping

    def source_property_type(self, property_type: str) -> str:
        """Return the source-specific property slug for a canonical type."""
        return self.property_type_mapping.get(property_type, property_type)


class SourceConfig(BaseModel):
    """Root source configuration file."""

    model_config = ConfigDict(extra="forbid")

    sources: tuple[SourceDefinition, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_sources(self) -> SourceConfig:
        if not self.sources:
            raise ValueError("sources must contain at least one source")

        source_ids = [source.source_id for source in self.sources]
        duplicate_ids = sorted(
            source_id
            for source_id in set(source_ids)
            if source_ids.count(source_id) > 1
        )

        if duplicate_ids:
            duplicate_ids_text = ", ".join(duplicate_ids)
            raise ValueError(f"source_id values must be unique: {duplicate_ids_text}")

        return self

    def enabled_sources(self) -> tuple[SourceDefinition, ...]:
        """Return sources enabled for ingestion."""
        return tuple(source for source in self.sources if source.enabled)


def default_source_config_path() -> Path:
    """Return the local source config path when present, otherwise the example."""
    if (
        LOCAL_SOURCE_CONFIG_PATH.exists()
        and LOCAL_SOURCE_CONFIG_PATH.stat().st_size > 0
    ):
        return LOCAL_SOURCE_CONFIG_PATH

    return EXAMPLE_SOURCE_CONFIG_PATH


def load_source_config(path: Path | str | None = None) -> SourceConfig:
    """Load and validate source configuration from YAML."""
    config_path = Path(path) if path is not None else default_source_config_path()

    if not config_path.exists():
        raise FileNotFoundError(f"Source config not found: {config_path}")

    payload = _load_yaml_mapping(config_path)
    return SourceConfig.model_validate(payload)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(parsed, dict):
        raise ValueError(f"Source config root must be an object: {path}")

    return parsed
