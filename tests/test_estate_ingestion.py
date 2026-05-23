"""Tests for listing ingestion, parsing, and resume behavior."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlsplit

from src.config.source_config import SourceDefinition
from src.config.env import normalize_url
from src.config.globals import ESTATE_URL, MAIN_URL
from src.ingestion.estate_ingestion import (
    build_listing_url,
    build_search_shards,
    extract_listing_items,
    extract_next_data_from_html,
    get_estate_info,
    ingest_estates_for,
    iter_estates,
)


def test_normalize_url() -> None:
    assert normalize_url("  https://example.invalid/results/") == (
        "https://example.invalid/results/"
    )


def test_build_listing_url_uses_estate_type_voivodeship_and_page() -> None:
    assert build_listing_url("mieszkanie", "mazowieckie", page=2) == (
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=2"
    )


def test_build_listing_url_accepts_search_query_params() -> None:
    url = build_listing_url(
        "mieszkanie",
        "mazowieckie",
        page=2,
        query_params={
            "search[filter_float_price:from]": "300000",
            "search[filter_float_price:to]": "400000",
        },
    )

    query = parse_qs(urlsplit(url).query)

    assert query["viewType"] == ["listing"]
    assert query["page"] == ["2"]
    assert query["search[filter_float_price:from]"] == ["300000"]
    assert query["search[filter_float_price:to]"] == ["400000"]


def test_iter_estates_uses_enabled_configured_sources() -> None:
    requested_urls: list[str] = []

    def fetcher(url: str) -> Mapping[str, Any]:
        requested_urls.append(url)
        return {
            "searchAds": {
                "items": [
                    {
                        "id": "listing-1",
                        "title": "Configured source offer",
                    }
                ]
            }
        }

    source_a = SourceDefinition(
        source_id="source_a",
        adapter_type="embedded_json_listing_site",
        enabled=True,
        base_url="https://example-listing-site.local",
        search_url_template=(
            "https://example-listing-site.local/search"
            "?property={property_type}&region={voivodeship}&page={page}"
        ),
        rate_limit_seconds=0,
        max_pages_default=3,
        allowed_offer_types=("sale",),
        allowed_property_types=("apartment",),
    )
    source_b = SourceDefinition(
        source_id="source_b",
        adapter_type="html_listing_site",
        enabled=False,
        base_url="https://example-listing-site-2.local",
        search_url_template="https://example-listing-site-2.local/offers?page={page}",
        rate_limit_seconds=0,
        max_pages_default=3,
        allowed_offer_types=("sale",),
        allowed_property_types=("apartment",),
    )

    estates = list(
        iter_estates(
            estate_types=("mieszkanie",),
            voivodeships=("mazowieckie",),
            max_page=1,
            fetcher=fetcher,
            detail_fetcher=None,
            sources=(source_a, source_b),
        )
    )

    assert requested_urls == [
        "https://example-listing-site.local/search"
        "?property=mieszkanie&region=mazowieckie&page=1"
    ]
    assert len(estates) == 1
    assert estates[0].source_id == "source_a"


def test_extract_next_data_from_html_parses_next_script() -> None:
    html = """
    <html>
      <script id="__NEXT_DATA__" type="application/json">
        {"props": {"pageProps": {"data": {"searchAds": {"items": [{"id": 1}]}}}}}
      </script>
    </html>
    """

    next_data_json = extract_next_data_from_html(html)

    assert extract_listing_items(next_data_json) == [{"id": 1}]


def test_extract_listing_items_supports_next_data_json_variant() -> None:
    next_data_json = {
        "pageProps": {
            "data": {
                "searchAds": {
                    "items": [
                        {"id": "first"},
                        {"id": "second"},
                    ]
                }
            }
        }
    }

    assert extract_listing_items(next_data_json) == [
        {"id": "first"},
        {"id": "second"},
    ]


def test_extract_listing_items_supports_nested_query_cache_shape() -> None:
    next_data_json = {
        "props": {
            "pageProps": {
                "dehydratedState": {
                    "queries": [
                        {
                            "state": {
                                "data": {
                                    "searchAds": {
                                        "items": [
                                            {
                                                "id": "first",
                                                "title": "Oferta z cache",
                                            },
                                            {
                                                "id": "second",
                                                "href": "[lang]/ad/oferta-ID4abc",
                                            },
                                        ]
                                    }
                                }
                            }
                        }
                    ]
                }
            }
        }
    }

    assert extract_listing_items(next_data_json) == [
        {"id": "first", "title": "Oferta z cache"},
        {"id": "second", "href": "[lang]/ad/oferta-ID4abc"},
    ]


def test_get_estate_info_maps_wide_listing_snapshot() -> None:
    image_one_url = f"{ESTATE_URL.rstrip('/')}/image-one.jpg"
    image_two_url = f"{ESTATE_URL.rstrip('/')}/image-two.jpg"

    estate = get_estate_info(
        {
            "id": "ABC123",
            "title": "Jasne mieszkanie z balkonem",
            "slug": "jasne-mieszkanie-z-balkonem-IDABC123",
            "totalPrice": {"value": "750 000 zł"},
            "pricePerSquareMeter": "15 000 zł/m²",
            "areaInSquareMeters": 50,
            "characteristics": [
                {"key": "rooms_num", "value": "THREE"},
                {"key": "market", "value": "SECONDARY"},
                {"key": "floor", "value": "2"},
                {"key": "buildingType", "value": "BLOCK"},
            ],
            "location": {
                "address": {
                    "city": "Warszawa",
                    "district": "Mokotów",
                    "street": "Puławska",
                },
                "coordinates": {
                    "latitude": 52.189,
                    "longitude": 21.012,
                },
            },
            "advertiserName": "Biuro Testowe",
            "advertiserType": "AGENCY",
            "images": [
                {"url": image_one_url},
                {"medium": image_two_url},
            ],
        },
        estate_type="mieszkanie",
        voivodeship="mazowieckie",
    )

    assert estate is not None
    assert estate.external_id == "ABC123"
    assert estate.url == (
        f"{ESTATE_URL.rstrip('/')}/jasne-mieszkanie-z-balkonem-IDABC123"
    )
    assert estate.price == 750000
    assert estate.price_per_sqm == 15000
    assert estate.area_sqm == 50
    assert estate.rooms == 3
    assert estate.city == "Warszawa"
    assert estate.district == "Mokotów"
    assert estate.street == "Puławska"
    assert estate.market == "SECONDARY"
    assert estate.floor == 2
    assert estate.building_type == "BLOCK"
    assert estate.seller_name == "Biuro Testowe"
    assert estate.seller_type == "AGENCY"
    assert estate.latitude == 52.189
    assert estate.longitude == 21.012
    assert estate.images == [
        image_one_url,
        image_two_url,
    ]


def test_get_estate_info_maps_nested_location_objects() -> None:
    estate = get_estate_info(
        {
            "id": 68001411,
            "title": "2 pokoje",
            "href": "[lang]/ad/2-pokoje-ID4BkgX",
            "totalPrice": {"value": 700000, "currency": "PLN"},
            "pricePerSquareMeter": {"value": 15419, "currency": "PLN"},
            "areaInSquareMeters": 45.4,
            "roomsNumber": "TWO",
            "floorNumber": "FIRST",
            "location": {
                "address": {
                    "street": {"name": "Żytnia", "number": ""},
                    "city": {"name": "Warszawa"},
                    "province": {"name": "mazowieckie"},
                },
                "reverseGeocoding": {
                    "locations": [
                        {
                            "id": "mazowieckie",
                            "fullName": "mazowieckie",
                            "name": "mazowieckie",
                            "locationLevel": "voivodeship",
                        },
                        {
                            "id": "mazowieckie/warszawa",
                            "fullName": "Warszawa, mazowieckie",
                            "name": "Warszawa",
                            "locationLevel": "city_or_village",
                        },
                        {
                            "id": "mazowieckie/warszawa/wola",
                            "fullName": "Wola, Warszawa, mazowieckie",
                            "name": "Wola",
                            "locationLevel": "district",
                        },
                    ]
                },
            },
        },
        estate_type="mieszkanie",
        voivodeship="mazowieckie",
    )

    assert estate is not None
    assert estate.city == "Warszawa"
    assert estate.district == "Wola"
    assert estate.street == "Żytnia"
    assert estate.location == "Żytnia, Wola, Warszawa"
    assert estate.price == 700000
    assert estate.price_per_sqm == 15419
    assert estate.area_sqm == 45.4
    assert estate.rooms == 2
    assert estate.floor == 1


def test_ingest_estates_for_stops_after_empty_page() -> None:
    requested_urls: list[str] = []
    responses: list[dict[str, Any]] = [
        {
            "props": {
                "pageProps": {
                    "data": {
                        "searchAds": {
                            "items": [
                                {
                                    "id": "first",
                                    "title": "Pierwsza oferta",
                                }
                            ]
                        }
                    }
                }
            }
        },
        {"props": {"pageProps": {"data": {"searchAds": {"items": []}}}}},
    ]

    def fetcher(url: str) -> Mapping[str, Any]:
        requested_urls.append(url)
        return responses.pop(0)

    estates = ingest_estates_for(
        "mieszkanie",
        "mazowieckie",
        max_page=5,
        fetcher=fetcher,
        detail_fetcher=None,
    )

    assert [estate.external_id for estate in estates] == ["first"]
    assert requested_urls == [
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=1",
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=2",
    ]


def test_ingest_estates_for_stops_after_duplicate_page() -> None:
    requested_urls: list[str] = []
    responses: list[dict[str, Any]] = [
        {
            "props": {
                "pageProps": {
                    "data": {
                        "searchAds": {
                            "items": [
                                {
                                    "id": "repeated",
                                    "title": "Pierwsza oferta",
                                }
                            ]
                        }
                    }
                }
            }
        },
        {
            "props": {
                "pageProps": {
                    "data": {
                        "searchAds": {
                            "items": [
                                {
                                    "id": "repeated",
                                    "title": "Ta sama oferta",
                                }
                            ]
                        }
                    }
                }
            }
        },
        {
            "props": {
                "pageProps": {
                    "data": {
                        "searchAds": {
                            "items": [
                                {
                                    "id": "should-not-be-fetched",
                                    "title": "Kolejna oferta",
                                }
                            ]
                        }
                    }
                }
            }
        },
    ]

    def fetcher(url: str) -> Mapping[str, Any]:
        requested_urls.append(url)
        return responses.pop(0)

    estates = ingest_estates_for(
        "mieszkanie",
        "mazowieckie",
        max_page=5,
        fetcher=fetcher,
        detail_fetcher=None,
    )

    assert [estate.external_id for estate in estates] == ["repeated"]
    assert requested_urls == [
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=1",
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=2",
    ]


def test_ingest_estates_for_resume_continues_past_duplicate_pages() -> None:
    requested_urls: list[str] = []

    def fetcher(url: str) -> Mapping[str, Any]:
        requested_urls.append(url)

        if "page=1" in url:
            listing_id = "already-seen-1"

        elif "page=2" in url:
            listing_id = "already-seen-2"

        elif "page=3" in url:
            listing_id = "new-listing"

        else:
            return {"props": {"pageProps": {"data": {"searchAds": {"items": []}}}}}

        return {
            "props": {
                "pageProps": {
                    "data": {
                        "searchAds": {
                            "items": [
                                {
                                    "id": listing_id,
                                    "title": f"Oferta {listing_id}",
                                }
                            ]
                        }
                    }
                }
            }
        }

    estates = ingest_estates_for(
        "mieszkanie",
        "mazowieckie",
        max_page=3,
        fetcher=fetcher,
        detail_fetcher=None,
        existing_external_ids={"already-seen-1", "already-seen-2"},
    )

    assert [estate.external_id for estate in estates] == ["new-listing"]
    assert requested_urls == [
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=1",
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=2",
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=3",
    ]


def test_ingest_estates_for_resume_stops_after_duplicate_page_threshold() -> None:
    requested_urls: list[str] = []

    def fetcher(url: str) -> Mapping[str, Any]:
        requested_urls.append(url)
        listing_id = f"already-seen-{len(requested_urls)}"

        return {
            "props": {
                "pageProps": {
                    "data": {
                        "searchAds": {
                            "items": [
                                {
                                    "id": listing_id,
                                    "title": "Stara oferta",
                                }
                            ]
                        }
                    }
                }
            }
        }

    estates = ingest_estates_for(
        "mieszkanie",
        "mazowieckie",
        max_page=10,
        fetcher=fetcher,
        detail_fetcher=None,
        existing_external_ids={"already-seen-1", "already-seen-2"},
        duplicate_page_stop_threshold=2,
    )

    assert estates == []
    assert requested_urls == [
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=1",
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=2",
    ]


def test_ingest_estates_for_resumes_from_start_page_and_reports_progress() -> None:
    requested_urls: list[str] = []
    completed_pages: list[tuple[str, str, int]] = []

    def fetcher(url: str) -> Mapping[str, Any]:
        requested_urls.append(url)

        if "page=8" in url:
            return {"props": {"pageProps": {"data": {"searchAds": {"items": []}}}}}

        return {
            "props": {
                "pageProps": {
                    "data": {
                        "searchAds": {
                            "items": [
                                {
                                    "id": "new-listing",
                                    "title": "Nowa oferta",
                                }
                            ]
                        }
                    }
                }
            }
        }

    estates = ingest_estates_for(
        "mieszkanie",
        "mazowieckie",
        max_page=8,
        fetcher=fetcher,
        detail_fetcher=None,
        start_page=7,
        progress_callback=lambda estate_type, voivodeship, page: completed_pages.append(
            (estate_type, voivodeship, page)
        ),
    )

    assert [estate.external_id for estate in estates] == ["new-listing"]
    assert requested_urls == [
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=7",
        f"{MAIN_URL.rstrip('/')}/mieszkanie/mazowieckie?viewType=listing&page=8",
    ]
    assert completed_pages == [
        ("mieszkanie", "mazowieckie", 7),
        ("mieszkanie", "mazowieckie", 8),
    ]


def test_iter_estates_uses_price_shards_and_shard_checkpoints() -> None:
    requested_queries: list[dict[str, list[str]]] = []
    completed_pages: list[tuple[str, str, int]] = []

    def fetcher(url: str) -> Mapping[str, Any]:
        query = parse_qs(urlsplit(url).query)
        requested_queries.append(query)
        listing_id = "|".join(
            f"{key}={','.join(value)}"
            for key, value in sorted(query.items())
            if key.startswith("search[")
        )

        return {
            "props": {
                "pageProps": {
                    "data": {
                        "searchAds": {
                            "items": [
                                {
                                    "id": listing_id,
                                    "title": f"Oferta {listing_id}",
                                }
                            ]
                        }
                    }
                }
            }
        }

    def record_progress(estate_type: str, voivodeship: str, page: int) -> None:
        completed_pages.append((estate_type, voivodeship, page))

    estates = list(
        iter_estates(
            estate_types=("mieszkanie",),
            voivodeships=("mazowieckie",),
            max_page=1,
            workers=1,
            fetcher=fetcher,
            detail_fetcher=None,
            search_shard_strategy="price",
            progress_callback=record_progress,
        )
    )

    price_shards = build_search_shards("price")
    expected_target_keys = [
        f"mieszkanie__{price_shard.key}" for price_shard in price_shards
    ]

    assert len(estates) == len(price_shards)
    assert len(requested_queries) == len(price_shards)
    assert requested_queries[0]["search[filter_float_price:to]"] == ["300000"]
    assert completed_pages == [
        (target_key, "mazowieckie", 1) for target_key in expected_target_keys
    ]


def test_iter_estates_supports_worker_threads() -> None:
    def fetcher(url: str) -> Mapping[str, Any]:
        if "page=2" in url:
            return {"props": {"pageProps": {"data": {"searchAds": {"items": []}}}}}

        if "mazowieckie" in url:
            listing_id = "mazowieckie-listing"
            voivodeship = "mazowieckie"
        else:
            listing_id = "pomorskie-listing"
            voivodeship = "pomorskie"

        return {
            "props": {
                "pageProps": {
                    "data": {
                        "searchAds": {
                            "items": [
                                {
                                    "id": listing_id,
                                    "title": f"Oferta {voivodeship}",
                                }
                            ]
                        }
                    }
                }
            }
        }

    estates = list(
        iter_estates(
            estate_types=("mieszkanie",),
            voivodeships=("mazowieckie", "pomorskie"),
            max_page=2,
            workers=2,
            fetcher=fetcher,
            detail_fetcher=None,
        )
    )

    assert sorted((estate.voivodeship, estate.external_id) for estate in estates) == [
        ("mazowieckie", "mazowieckie-listing"),
        ("pomorskie", "pomorskie-listing"),
    ]


def test_iter_estates_skips_existing_external_ids_before_detail_fetch() -> None:
    detail_urls: list[str] = []

    def fetcher(url: str) -> Mapping[str, Any]:
        if "page=2" in url:
            return {"props": {"pageProps": {"data": {"searchAds": {"items": []}}}}}

        return {
            "props": {
                "pageProps": {
                    "data": {
                        "searchAds": {
                            "items": [
                                {
                                    "id": "already-seen",
                                    "title": "Stara oferta",
                                    "href": "[lang]/ad/stara-oferta-ID4old",
                                },
                                {
                                    "id": "new-listing",
                                    "title": "Nowa oferta",
                                    "href": "[lang]/ad/nowa-oferta-ID4new",
                                },
                            ]
                        }
                    }
                }
            }
        }

    def detail_fetcher(url: str) -> Mapping[str, Any]:
        detail_urls.append(url)
        return {
            "props": {
                "pageProps": {
                    "ad": {
                        "id": "new-listing",
                        "title": "Nowa oferta",
                    }
                }
            }
        }

    estates = list(
        iter_estates(
            estate_types=("mieszkanie",),
            voivodeships=("mazowieckie",),
            max_page=2,
            workers=1,
            fetcher=fetcher,
            detail_fetcher=detail_fetcher,
            existing_external_ids_by_voivodeship={
                "mazowieckie": {"already-seen"},
            },
        )
    )

    assert [estate.external_id for estate in estates] == ["new-listing"]
    assert detail_urls == [f"{ESTATE_URL.rstrip('/')}/nowa-oferta-ID4new"]


def test_ingest_estates_for_enriches_listing_with_detail_page() -> None:
    requested_detail_urls: list[str] = []
    listing_response = {
        "props": {
            "pageProps": {
                "data": {
                    "searchAds": {
                        "items": [
                            {
                                "id": "67792619",
                                "title": "Pięknie położony dom",
                                "href": "[lang]/ad/pieknie-polozony-dom-ID4ArXl",
                                "totalPrice": {"value": 2600000},
                            }
                        ]
                    }
                }
            }
        }
    }

    def fetcher(url: str) -> Mapping[str, Any]:
        return listing_response if "page=1" in url else {}

    def detail_fetcher(url: str) -> Mapping[str, Any]:
        requested_detail_urls.append(url)
        return {
            "props": {
                "pageProps": {
                    "ad": {
                        "id": 67792619,
                        "slug": "pieknie-polozony-dom-ID4ArXl",
                        "market": "SECONDARY",
                        "advertType": "AGENCY",
                        "target": {
                            "Building_type": ["detached"],
                        },
                        "location": {
                            "coordinates": {
                                "latitude": 52.5200528,
                                "longitude": 21.075463,
                            },
                            "address": {
                                "city": {"name": "Serock"},
                                "street": None,
                                "district": None,
                            },
                        },
                        "agency": {
                            "name": "Magiczny Dom",
                            "type": "agency",
                        },
                    }
                }
            }
        }

    estates = ingest_estates_for(
        "dom",
        "mazowieckie",
        max_page=1,
        fetcher=fetcher,
        detail_fetcher=detail_fetcher,
    )

    assert requested_detail_urls == [
        f"{ESTATE_URL.rstrip('/')}/pieknie-polozony-dom-ID4ArXl"
    ]
    assert len(estates) == 1
    assert estates[0].city == "Serock"
    assert estates[0].location == "Serock"
    assert estates[0].market == "SECONDARY"
    assert estates[0].building_type == "detached"
    assert estates[0].seller_name == "Magiczny Dom"
    assert estates[0].seller_type == "agency"
    assert estates[0].latitude == 52.5200528
    assert estates[0].longitude == 21.075463


def test_ingest_estates_for_normalizes_prefixed_detail_url() -> None:
    requested_detail_urls: list[str] = []
    listing_response = {
        "props": {
            "pageProps": {
                "data": {
                    "searchAds": {
                        "items": [
                            {
                                "id": "listing-1",
                                "title": "Oferta",
                                "href": ("[lang]/ad/hpr/" "4pokojw-w-promocji-ID4Bmyv"),
                            }
                        ]
                    }
                }
            }
        }
    }

    def fetcher(url: str) -> Mapping[str, Any]:
        return listing_response

    def detail_fetcher(url: str) -> Mapping[str, Any]:
        requested_detail_urls.append(url)
        return {}

    estates = ingest_estates_for(
        "mieszkanie",
        "mazowieckie",
        max_page=1,
        fetcher=fetcher,
        detail_fetcher=detail_fetcher,
    )

    assert requested_detail_urls == [
        f"{ESTATE_URL.rstrip('/')}/4pokojw-w-promocji-ID4Bmyv"
    ]
    assert estates[0].url == f"{ESTATE_URL.rstrip('/')}/4pokojw-w-promocji-ID4Bmyv"
