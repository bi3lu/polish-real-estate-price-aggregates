from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.models.estate import Estate
from src.utils.storage import save_estates_to_bronze


def test_save_estates_to_bronze_writes_snapshot_json(tmp_path: Path) -> None:
    output_path = save_estates_to_bronze(
        [
            Estate(
                external_id="listing-1",
                title="Pierwsza oferta",
                estate_type="mieszkanie",
                voivodeship="mazowieckie",
            )
        ],
        estate_types=("mieszkanie",),
        voivodeships=("mazowieckie",),
        max_page=2,
        output_dir=tmp_path,
        scraped_at=datetime(2026, 5, 15, 12, 30, 45, tzinfo=timezone.utc),
    )

    assert output_path == tmp_path / "estate_snapshot_20260515T123045000000Z.json"

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["scraped_at"] == "2026-05-15T12:30:45+00:00"
    assert payload["estate_types"] == ["mieszkanie"]
    assert payload["voivodeships"] == ["mazowieckie"]
    assert payload["max_page"] == 2
    assert payload["count"] == 1
    assert payload["data"][0]["external_id"] == "listing-1"
