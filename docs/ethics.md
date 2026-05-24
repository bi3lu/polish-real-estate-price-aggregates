# Ethics and Responsible Collection

This project is intended for data engineering education, analytics, and
non-commercial research. Collection must remain conservative, lawful, and
respectful of source infrastructure.

## Rules

1. Respect source terms of service, robots policy, and applicable law before
   every run.
1. Keep collection low-impact: conservative page limits, low concurrency,
   explicit `rate_limit_seconds`, and bounded retries.
1. Use `enabled: false` for sources that should not be contacted.
1. Treat `403`, `429`, challenge pages, and repeated failures as stop signals
   rather than bypass targets.
1. Do not implement CAPTCHA solving, anti-bot bypass, proxy rotation for
   evasion, fingerprint spoofing, account farming, or similar controls.
1. Prefer transparent identification when requesting public pages where that is
   technically and legally appropriate.
1. Keep real source configuration local in `config/sources.local.yaml`.
1. Keep raw bronze data private. Publish only anonymized public outputs after
   review.

## Publication Boundary

- Raw bronze observations remain local and are ignored by Git.
- Silver and gold local outputs are also ignored by Git by default.
- Public sharing is limited to anonymized outputs under `data/public/`.
- Before publishing regenerated public outputs, re-check schema and sample rows
  for accidental identifiers, URLs, precise locations, seller data, or image
  URLs.

## Operational Guidance

- Start with `--max-page 1` and `--workers 1` when testing a new source config.
- Prefer source-level `max_pages_default` and `rate_limit_seconds` values that
  are more conservative than the CLI defaults.
- Use checkpoints and duplicate detection to avoid repeatedly requesting the
  same pages.
- If a source starts returning unexpected HTML, empty embedded state, or block
  responses, stop and inspect the parser/config instead of increasing pressure.
