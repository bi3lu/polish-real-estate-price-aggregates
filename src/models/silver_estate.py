"""Normalized silver-layer data models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SilverEstate(BaseModel):
    """Flat normalized listing record stored in the silver CSV layer."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    source: str
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
