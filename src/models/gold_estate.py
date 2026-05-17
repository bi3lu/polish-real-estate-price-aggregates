from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GoldListingFeature(BaseModel):
    """Model-ready listing row enriched with analysis-friendly derived features."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    estate_type: str | None = None
    voivodeship: str | None = None
    city: str | None = None
    district: str | None = None
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
    build_year: int | None = None
    seller_type: str | None = None
    has_lift: bool = False
    has_balcony: bool = False
    has_garage: bool = False
    has_basement: bool = False
    has_separate_kitchen: bool = False
    has_air_conditioning: bool = False
    has_garden: bool = False
    image_count: int = 0
    has_coordinates: bool = False
    is_price_outlier: bool = False
    price_per_sqm_source: str | None = None
    total_monthly_cost_pln: float | None = None
    area_bucket: str | None = None
    price_bucket: str | None = None
    rooms_bucket: str | None = None
    building_age_years: int | None = None
    floor_ratio: float | None = None
    amenity_count: int = 0
    geo_precision: str
    ml_target_price_pln: float | None = None
    ml_target_price_per_sqm_pln: float | None = None
    processed_at: str


class GoldGeoAggregate(BaseModel):
    """Geo grain for map layers and local market comparison."""

    model_config = ConfigDict(extra="forbid")

    geo_id: str
    voivodeship: str | None = None
    city: str | None = None
    district: str | None = None
    estate_type: str | None = None
    records_count: int
    priced_records_count: int
    coordinate_records_count: int
    avg_latitude: float | None = None
    avg_longitude: float | None = None
    min_price_pln: float | None = None
    p25_price_pln: float | None = None
    median_price_pln: float | None = None
    avg_price_pln: float | None = None
    p75_price_pln: float | None = None
    max_price_pln: float | None = None
    median_price_per_sqm_pln: float | None = None
    avg_price_per_sqm_pln: float | None = None
    median_area_sqm: float | None = None
    avg_area_sqm: float | None = None
    share_with_coordinates: float
    share_agency: float
    share_private: float
    processed_at: str


class GoldSegmentAggregate(BaseModel):
    """Segment grain for dashboards and analytical slices."""

    model_config = ConfigDict(extra="forbid")

    segment_id: str
    estate_type: str | None = None
    voivodeship: str | None = None
    market: str | None = None
    building_type: str | None = None
    rooms_bucket: str | None = None
    area_bucket: str | None = None
    records_count: int
    priced_records_count: int
    median_price_pln: float | None = None
    avg_price_pln: float | None = None
    median_price_per_sqm_pln: float | None = None
    avg_price_per_sqm_pln: float | None = None
    median_area_sqm: float | None = None
    avg_area_sqm: float | None = None
    median_rent_pln: float | None = None
    share_with_lift: float
    share_with_balcony: float
    share_with_garage: float
    share_with_garden: float
    share_with_air_conditioning: float
    processed_at: str


class GoldDataQuality(BaseModel):
    """Dataset observability row for a single silver-to-gold run."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    value: float
    records_count: int
    processed_at: str
