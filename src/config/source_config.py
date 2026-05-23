"""Source configuration models and loader."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.config.env import PROJECT_ROOT

DEFAULT_SOURCE_CONFIG_DIR = PROJECT_ROOT / "config"
EXAMPLE_SOURCE_CONFIG_PATH = DEFAULT_SOURCE_CONFIG_DIR / "sources.example.yaml"
LOCAL_SOURCE_CONFIG_PATH = DEFAULT_SOURCE_CONFIG_DIR / "sources.local.yaml"

AdapterType = Literal["embedded_json_listing_site", "html_listing_site"]


class SourceDefinition(BaseModel):
    """Configuration for one logical listing source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    adapter_type: AdapterType
    enabled: bool = True
    base_url: str = Field(min_length=1)
    search_url_template: str = Field(min_length=1)
    rate_limit_seconds: float = Field(default=0.0, ge=0)
    max_pages_default: int = Field(default=1, ge=1)
    allowed_offer_types: tuple[str, ...] = Field(default_factory=tuple)
    allowed_property_types: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("source_id must not be empty")

        if any(character.isspace() for character in normalized):
            raise ValueError("source_id must not contain whitespace")

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
    if LOCAL_SOURCE_CONFIG_PATH.exists():
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
    try:
        import yaml  # type: ignore[import-untyped]

    except ModuleNotFoundError:
        parsed = _parse_supported_yaml(path.read_text(encoding="utf-8"))

    else:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(parsed, dict):
        raise ValueError(f"Source config root must be an object: {path}")

    return parsed


def _parse_supported_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by the public source config."""
    result: dict[str, Any] = {}
    current_source: dict[str, Any] | None = None
    current_list_key: str | None = None

    for raw_line in text.splitlines():
        line_without_comment = raw_line.split("#", maxsplit=1)[0].rstrip()

        if not line_without_comment.strip():
            continue

        stripped = line_without_comment.strip()

        if stripped == "sources:":
            result["sources"] = []
            current_source = None
            current_list_key = None
            continue

        if line_without_comment.startswith("  - "):
            if not isinstance(result.get("sources"), list):
                raise ValueError("Only top-level sources lists are supported")

            current_source = {}
            result["sources"].append(current_source)
            current_list_key = None
            key, value = _split_yaml_key_value(line_without_comment.strip()[2:])
            current_source[key] = _parse_yaml_scalar(value)
            continue

        if line_without_comment.startswith("      - "):
            if current_source is None or current_list_key is None:
                raise ValueError("YAML list item is missing a parent key")

            current_source[current_list_key].append(
                _parse_yaml_scalar(line_without_comment.strip()[1:].strip())
            )
            continue

        if current_source is None:
            key, value = _split_yaml_key_value(stripped)
            result[key] = _parse_yaml_scalar(value)
            continue

        key, value = _split_yaml_key_value(stripped)

        if value == "":
            current_source[key] = []
            current_list_key = key
            continue

        current_source[key] = _parse_yaml_scalar(value)
        current_list_key = None

    return result


def _split_yaml_key_value(text: str) -> tuple[str, str]:
    if ":" not in text:
        raise ValueError(f"Expected YAML key-value pair: {text}")

    key, value = text.split(":", maxsplit=1)
    return key.strip(), value.strip()


def _parse_yaml_scalar(value: str) -> Any:
    if value == "":
        return ""

    if value in {"true", "True"}:
        return True

    if value in {"false", "False"}:
        return False

    try:
        return ast.literal_eval(value)

    except (SyntaxError, ValueError):
        pass

    try:
        return int(value)

    except ValueError:
        pass

    try:
        return float(value)

    except ValueError:
        return value
