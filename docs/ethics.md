# Ethics and Responsible Data Collection

This project is intended for non-commercial research and data engineering
education. Collection must remain conservative, compliant, and respectful of
source infrastructure.

## Rules

1. Respect source terms of service and applicable law before every run.
1. Keep collection low-impact: conservative page limits, low concurrency,
   explicit pacing, and bounded retries.
1. Honor source blocking signals (`403`, `429`, challenge pages) as a stop signal
   rather than a bypass target.
1. Do not implement or use CAPTCHA solving, anti-bot bypass, fingerprint
   spoofing, account farming, proxy rotation for evasion, or similar controls.
1. Prefer transparent identification when requesting public pages, including a
   research/non-commercial `User-Agent` where technically feasible.
1. Treat `respect_robots_txt` as a required configuration decision for each
   source. The current implementation is config-level and policy-driven;
   full runtime robots enforcement can be added per source adapter.
1. Keep raw listing data private. Publish only anonymized outputs after privacy
   checks.

## Data Publication Boundary

- Raw bronze observations remain local and are not published from this
  repository.
- Public sharing is limited to anonymized outputs under `data/public/`.
- Before publishing regenerated outputs, re-check schema and sample rows for
  accidental identifiers.
