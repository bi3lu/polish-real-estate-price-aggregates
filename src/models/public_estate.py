"""Public-facing models for anonymized real estate datasets.

Public models are a separate contract from private/internal canonical records.
They must never expose listing identifiers, source identity, URLs, seller
identity, street-level location, raw coordinates, or image URLs.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

FORBIDDEN_PUBLIC_FIELD_NAMES = frozenset(
    {
        "source",
        "source_id",
        "record_id",
        "external_id",
        "url",
        "title",
        "location",
        "street",
        "district",
        "address",
        "latitude",
        "longitude",
        "seller_name",
        "seller_id",
        "advertiser_type",
        "user_type",
        "first_image_url",
        "image_url",
        "images",
        "raw_payload",
        "attributes",
    }
)


class PublicListingFeature(BaseModel):
    """Privacy-preserving public row derived from private listing features."""

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
    """Observability metric for a public anonymized dataset."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    value: float
    records_count: int
    processed_at: str


def assert_public_schema_safe(model_type: type[BaseModel]) -> None:
    """Assert that a public model does not expose forbidden private fields."""
    forbidden_fields = FORBIDDEN_PUBLIC_FIELD_NAMES & set(model_type.model_fields)

    if forbidden_fields:
        forbidden_text = ", ".join(sorted(forbidden_fields))
        raise ValueError(
            f"Public model {model_type.__name__} exposes forbidden field(s): "
            f"{forbidden_text}"
        )
