from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a local SVG coverage badge from coverage.py JSON output."
    )
    parser.add_argument(
        "--input",
        default="coverage.json",
        type=Path,
        help="Path to coverage.py JSON report.",
    )
    parser.add_argument(
        "--output",
        default="assets/coverage.svg",
        type=Path,
        help="Path where the generated SVG badge should be written.",
    )
    args = parser.parse_args()

    coverage_percent = _read_coverage_percent(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_render_badge(coverage_percent), encoding="utf-8")

    return 0


def _read_coverage_percent(path: Path) -> float:
    payload = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise ValueError(f"Coverage JSON root must be an object: {path}")

    totals = payload.get("totals")

    if not isinstance(totals, dict):
        raise ValueError(f"Coverage JSON must contain totals object: {path}")

    percent = totals.get("percent_covered_display")

    if percent is None:
        percent = totals.get("percent_covered")

    if percent is None:
        raise ValueError(f"Coverage JSON must contain percent covered: {path}")

    return float(percent)


def _render_badge(coverage_percent: float) -> str:
    value = f"{coverage_percent:.0f}%"
    color = _badge_color(coverage_percent)
    label_width = 64
    value_width = max(42, 10 * len(value) + 12)
    total_width = label_width + value_width
    value_x = label_width + value_width / 2
    font_family = "Verdana,Geneva,DejaVu Sans,sans-serif"

    return "\n".join(
        [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" '
                f'height="20" role="img" aria-label="coverage: {value}">'
            ),
            f"  <title>coverage: {value}</title>",
            '  <linearGradient id="s" x2="0" y2="100%">',
            '    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>',
            '    <stop offset="1" stop-opacity=".1"/>',
            "  </linearGradient>",
            '  <clipPath id="r">',
            f'    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>',
            "  </clipPath>",
            '  <g clip-path="url(#r)">',
            f'    <rect width="{label_width}" height="20" fill="#555"/>',
            (
                f'    <rect x="{label_width}" width="{value_width}" '
                f'height="20" fill="{color}"/>'
            ),
            f'    <rect width="{total_width}" height="20" fill="url(#s)"/>',
            "  </g>",
            (
                f'  <g fill="#fff" text-anchor="middle" font-family="{font_family}" '
                'text-rendering="geometricPrecision" font-size="110">'
            ),
            (
                '    <text aria-hidden="true" x="320" y="150" fill="#010101" '
                'fill-opacity=".3" transform="scale(.1)" '
                'textLength="540">coverage</text>'
            ),
            (
                '    <text x="320" y="140" transform="scale(.1)" fill="#fff" '
                'textLength="540">coverage</text>'
            ),
            (
                f'    <text aria-hidden="true" x="{value_x * 10:.0f}" y="150" '
                'fill="#010101" fill-opacity=".3" transform="scale(.1)"'
                f">{value}</text>"
            ),
            (
                f'    <text x="{value_x * 10:.0f}" y="140" '
                'transform="scale(.1)" fill="#fff"'
                f">{value}</text>"
            ),
            "  </g>",
            "</svg>",
            "",
        ]
    )


def _badge_color(coverage_percent: float) -> str:
    thresholds: tuple[tuple[float, str], ...] = (
        (95, "#4c1"),
        (90, "#97ca00"),
        (80, "#a4a61d"),
        (70, "#dfb317"),
        (60, "#fe7d37"),
    )

    for threshold, color in thresholds:
        if coverage_percent >= threshold:
            return color

    return "#e05d44"


if __name__ == "__main__":
    raise SystemExit(main())
