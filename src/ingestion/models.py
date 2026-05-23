"""Neutral ingestion and canonical listing models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class RawListingObservation(BaseModel):
    """Raw source observation produced by an ingestion adapter."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_id: str = Field(
        default="source_a",
        validation_alias=AliasChoices("source_id", "source"),
    )
    external_id: str
    url: str | None = None
    title: str | None = None
    estate_type: str | None = None
    voivodeship: str | None = None
    price: float | None = None
    price_per_sqm: float | None = None
    area_sqm: float | None = None
    rooms: int | None = None
    location: str | None = None
    city: str | None = None
    district: str | None = None
    street: str | None = None
    market: str | None = None
    floor: int | None = None
    building_type: str | None = None
    seller_name: str | None = None
    seller_type: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    images: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    observed_at: str | None = None

    @property
    def source(self) -> str:
        """Backward-compatible accessor for older call sites."""
        return self.source_id


class CanonicalListing(BaseModel):
    """Flat normalized listing record used by silver and downstream ETL."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    record_id: str
    source_id: str = Field(validation_alias=AliasChoices("source_id", "source"))
    external_id: str
    url: str | None = None
    title: str | None = None
    estate_type: str | None = None
    voivodeship: str | None = None
    city: str | None = None
    district: str | None = None
    street: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    price_pln: float | None = None
    price_per_sqm_pln: float | None = None
    rent_pln: float | None = None
    area_sqm: float | None = None
    terrain_area_sqm: float | None = None
    rooms: int | None = None
    floor: int | None = None
    building_floors_num: int | None = None
    market: str | None = None
    building_type: str | None = None
    building_material: str | None = None
    building_ownership: str | None = None
    build_year: int | None = None
    construction_status: str | None = None
    heating: str | None = None
    windows_type: str | None = None
    energy_certificate: str | None = None
    seller_name: str | None = None
    seller_type: str | None = None
    seller_id: str | None = None
    advertiser_type: str | None = None
    user_type: str | None = None
    has_lift: bool = False
    has_balcony: bool = False
    has_garage: bool = False
    has_basement: bool = False
    has_separate_kitchen: bool = False
    has_air_conditioning: bool = False
    has_garden: bool = False
    security_types: str | None = None
    media_types: str | None = None
    equipment_types: str | None = None
    extras_types: str | None = None
    additional_features: str | None = None
    image_count: int = 0
    first_image_url: str | None = None
    has_price: bool = False
    has_location: bool = False
    has_coordinates: bool = False
    bronze_scraped_at: str | None = None
    processed_at: str

    @property
    def source(self) -> str:
        """Backward-compatible accessor for older call sites."""
        return self.source_id


class SourceRunStats(BaseModel):
    """Operational counters for one ingestion source run."""

    model_config = ConfigDict(extra="forbid")

    pages_requested: int = 0
    records_seen: int = 0
    records_written: int = 0
    duplicates_skipped: int = 0
    errors_count: int = 0


class SourceQualityStats(BaseModel):
    """Quality counters for records emitted by one source run."""

    model_config = ConfigDict(extra="forbid")

    records_count: int = 0
    records_with_price: int = 0
    records_with_location: int = 0
    records_with_coordinates: int = 0


class SourceRun(BaseModel):
    """Metadata for a source ingestion run without exposing a real source name."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    source_id: str
    adapter_type: str
    started_at: datetime
    finished_at: datetime | None = None
    enabled: bool = True
    stats: SourceRunStats = Field(default_factory=SourceRunStats)
    quality: SourceQualityStats = Field(default_factory=SourceQualityStats)
