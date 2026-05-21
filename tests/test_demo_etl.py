from __future__ import annotations

import csv
from pathlib import Path

from src.etl.demo import build_demo_estates, run_demo_pipeline


def test_run_demo_pipeline_writes_all_layers(tmp_path: Path) -> None:
    output_paths = run_demo_pipeline(base_dir=tmp_path)

    assert output_paths.bronze.exists()
    assert output_paths.silver.exists()
    assert output_paths.gold.ml_features.exists()
    assert output_paths.gold.geo_aggregates.exists()
    assert output_paths.gold.segment_aggregates.exists()
    assert output_paths.gold.data_quality.exists()
    assert output_paths.public.ml_features.exists()
    assert output_paths.public.data_quality.exists()

    with output_paths.public.ml_features.open(encoding="utf-8", newline="") as file:
        public_rows = list(csv.DictReader(file))

    assert len(public_rows) == len(build_demo_estates())
    assert "external_id" not in public_rows[0]
    assert "url" not in public_rows[0]
    assert "seller_name" not in public_rows[0]
