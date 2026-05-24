# Source Configuration

Sources are configured through YAML instead of hardcoded branded classes. The
repository includes only a synthetic example:

```text
config/sources.example.yaml
```

Real local sources belong in:

```text
config/sources.local.yaml
```

The local file is ignored by Git.

## Source Definition

```yaml
sources:
  - source_id: source_a
    adapter_type: embedded_json_listing_site
    enabled: true
    base_url: "https://example-listing-site.local"
    search_url_template: "https://example-listing-site.local/search/{property_type}/{voivodeship}?page={page}"
    rate_limit_seconds: 5
    max_pages_default: 3
    respect_robots_txt: true
    allowed_offer_types:
      - sale
    allowed_property_types:
      - mieszkanie
      - dom
    property_type_mapping:
      mieszkanie: apartments
      dom: houses
```

| Field | Description |
| --- | --- |
| `source_id` | Opaque source identifier used in manifests, records, and storage paths. |
| `adapter_type` | Neutral adapter key resolved through `ADAPTER_REGISTRY`. |
| `enabled` | Allows local enabling/disabling without code changes. |
| `base_url` | Base URL used to normalize relative listing URLs. |
| `search_url_template` | Template used for listing pages. Must include `{page}`. |
| `rate_limit_seconds` | Per-source request pacing. |
| `max_pages_default` | Per-source page cap. |
| `respect_robots_txt` | Policy flag documenting expected source handling. |
| `allowed_offer_types` | Offer categories accepted by this source config. |
| `allowed_property_types` | Canonical property types that this source should receive. |
| `property_type_mapping` | Optional canonical-to-source URL slug mapping. |

Supported template placeholders:

| Placeholder | Value |
| --- | --- |
| `{page}` | Page number. |
| `{property_type}` | Source-specific property type after mapping. |
| `{estate_type}` | Alias for mapped `{property_type}`. |
| `{canonical_property_type}` | Original canonical property type from CLI/config. |
| `{canonical_estate_type}` | Alias for canonical property type. |
| `{voivodeship}` | Voivodeship slug. |
| `{source_id}` | Neutral source id. |

## Adapter Registry

`src/ingestion/registry.py` maps neutral adapter keys to reusable adapter
classes:

```python
ADAPTER_REGISTRY = {
    "html_listing_site": HtmlListingSourceAdapter,
    "embedded_json_listing_site": EmbeddedJsonListingSourceAdapter,
    "paginated_listing_site": PaginatedListingSourceAdapter,
}
```

Adding a new source of an existing technical type should only require a YAML
entry. Unknown `adapter_type` values fail clearly during adapter construction.

## Property Type Mapping

The project keeps canonical estate types in records and checkpoints, for
example `mieszkanie` and `dom`. A source can require different URL slugs. Use
`property_type_mapping` for that:

```yaml
allowed_property_types:
  - mieszkanie
  - dom
property_type_mapping:
  mieszkanie: apartments
  dom: houses
```

The pipeline filters targets per source using `allowed_property_types`, then
uses the mapped value only when formatting the source URL.

## Adapter Behavior

The current reusable adapters parse:

- direct JSON object payloads,
- HTML with `__NEXT_DATA__`,
- HTML with `window.__PRERENDERED_STATE__`,
- listing item paths such as `searchAds.items`, `data.results`, and
  `listing.listing.ads`.

`html_listing_site` sources use listing pages as the record source and do not
fetch detail pages by default, because some HTML detail pages expose only shell
or category state and no stable detail object.

## CI and Tests

CI uses synthetic/example config only. Tests use synthetic fixtures under:

```text
tests/fixtures/sources/
```

Fixtures must remain offline and must not contain real source HTML, real source
URLs, real listing descriptions, or source brands.
