# Data Model Overview

```mermaid
classDiagram
    class RawListingObservation {
        source_id: str
        external_id: str
        url: str?
        title: str?
        estate_type: str?
        voivodeship: str?
        price: float?
        price_per_sqm: float?
        area_sqm: float?
        rooms: int?
        location: str?
        attributes: dict
    }

    class CanonicalListing {
        record_id: str
        source_id: str
        external_id: str
        price_pln: float?
        price_per_sqm_pln: float?
        area_sqm: float?
        normalized_location: str?
        image_count: int
        quality_flags: bool
        processed_at: str
    }

    class SourceRun {
        run_id: str
        source_id: str
        adapter_type: str
        started_at: datetime
        finished_at: datetime?
        stats: SourceRunStats
        quality: SourceQualityStats
    }

    class SourceRunStats {
        pages_requested: int
        records_seen: int
        records_written: int
        duplicates_skipped: int
        errors_count: int
    }

    class SourceQualityStats {
        records_count: int
        records_with_price: int
        records_with_location: int
        records_with_coordinates: int
    }

    class GoldListingFeature {
        record_id: str
        bucketed_features: str?
        amenity_flags: bool
        geo_precision: str
        ml_targets: float?
    }

    class PublicListingFeature {
        public_location: str?
        bucketed_attributes: str?
        rounded_targets: float?
        no_direct_identifiers: bool
    }

    RawListingObservation --> CanonicalListing : normalize in silver
    SourceRun --> SourceRunStats
    SourceRun --> SourceQualityStats
    CanonicalListing --> GoldListingFeature : feature engineering
    GoldListingFeature --> PublicListingFeature : anonymize
```

Domain ingestion models live in `src/ingestion/models.py` and use neutral names.
They do not contain source-branded model names. Every record carries
`source_id`, but that id can be opaque and does not need to reveal the real
source.

`CanonicalListing` is private/internal. It can contain listing-level fields such
as URL, title, street, seller metadata, precise coordinates, and image-derived
fields because those are useful for private quality control and feature
engineering.

Public exports are a separate contract. They must never expose listing-level
identifiers, source identity, URL/title fields, seller identifiers, street-level
location, raw coordinates, image URLs, or raw source attributes.
