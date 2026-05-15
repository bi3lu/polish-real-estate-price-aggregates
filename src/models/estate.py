from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Estate(BaseModel):
    """Snapshot of a real estate listing."""

    model_config = ConfigDict(extra="forbid")

    source: str = "estate_service"
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
    floor: str | None = None
    building_type: str | None = None
    seller_name: str | None = None
    seller_type: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    images: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
