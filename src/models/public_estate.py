from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PublicListingFeature(BaseModel):
    """Privacy-preserving listing row for public ML datasets."""

    model_config = ConfigDict(extra="forbid")

    estate_type: str | None = None
    voivodeship: str | None = None
    city: str | None = None
    geo_lat_grid: float | None = None
    geo_lon_grid: float | None = None
    market: str | None = None
    building_type: str | None = None
    seller_type: str | None = None
    area_bucket: str | None = None
    price_bucket: str | None = None
    rooms_bucket: str | None = None
    building_age_bucket: str | None = None
    floor_bucket: str | None = None
    building_floors_bucket: str | None = None
    terrain_area_bucket: str | None = None
    image_count_bucket: str | None = None
    has_lift: bool = False
    has_balcony: bool = False
    has_garage: bool = False
    has_basement: bool = False
    has_separate_kitchen: bool = False
    has_air_conditioning: bool = False
    has_garden: bool = False
    amenity_count: int = 0
    has_coordinates: bool = False
    is_price_outlier: bool = False
    price_per_sqm_source: str | None = None
    public_target_price_pln: float | None = None
    public_target_price_per_sqm_pln: float | None = None
    public_rent_pln: float | None = None
    processed_at: str


class PublicDataQuality(BaseModel):
    """Observability metrics for a public anonymized dataset."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    value: float
    records_count: int
    processed_at: str
