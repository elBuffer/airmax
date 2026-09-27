# Transformation contract

Product rules and acceptance values live in [`story.txt`](../../story.txt). This file maps that contract to the transformation workflow without repeating the full product brief.

## Code

- Lambda adapter: `src/airmax_transformation/handler.py`
- Refresh and publication: `src/airmax_transformation/application/refresh_air_quality.py`
- Current and WHO orchestration: `src/airmax_transformation/calculations/current.py` and `who.py`
- WHO period mathematics: `src/airmax_transformation/calculations/who_aggregation.py`
- Shared preparation order: `src/airmax_transformation/pipeline.py`
- Validation, windows, deduplication and municipality mapping: `src/airmax_transformation/transformations/`

## Workflow

```text
list candidate raw keys
  → select keys for each due calculation
  → stop when the selected-key digest is unchanged
  → stream records through validation into /tmp/accepted.ndjson
  → anchor the window at newest SNS publish time T
  → filter the exact window and deduplicate
  → map coordinates to municipalities
  → aggregate current or WHO results
  → validate the output contract
  → publish results/latest.json with compare-and-swap
```

Raw records remain unchanged. Every result is recomputed; there are no running counters.

## Input and time

Only dated `raw/` partitions are calculation input; `raw/invalid/` is preserved but excluded. Folder selection includes one boundary hour, then record timestamps apply the exact window.

SNS publish time controls partitions, windows and freshness. `date.utc` is retained for traceability, deduplication and the five-minute late-data guard, but never anchors a window.

| Calculation | Window | Cadence |
|---|---:|---:|
| Current | 3 hours | on changed input, up to every 5 minutes |
| WHO PM2.5, PM10, NO2, SO2 and CO | 24 hours | at most hourly |
| WHO ozone | 8 hours | at most hourly |

## Record preparation

`validation.py` owns all reading acceptance checks. A rejected record is skipped; processing continues with the next record. Accepted readings are streamed to temporary NDJSON, not accumulated as a raw window in memory.

Within the exact window:

1. deduplicate by `locationId + pollutant + raw date.utc`;
2. map coordinates through the packaged municipality boundaries, excluding readings that do not
   map to a municipality.

## Aggregation

Current results average readings per physical site, then average sites equally per municipality, pollutant and unit. They report measurements, location IDs and physical sites.

WHO results average site-hours, then municipality-hours, then represented hours equally. They report measurements, physical sites, observation times and represented hours. Product guideline values, required coverage and permitted wording remain authoritative in `story.txt`.

## Publication

Current and WHO sections have independent input digests and timestamps. WHO sections are reused between due hourly calculations.

Before publication, `calculations/result_validation.py` checks generated time, then the window, then each city row and row uniqueness. A validation error fails the transformation invocation before the S3 write, so `results/latest.json` remains the previous valid result and the website never receives the invalid candidate.

Publication uses the current S3 ETag. After a conflict, the run compares `window.end_t` values:

- stop when the stored source time is equal or later;
- retry only when this run has later source data.

Wall-clock `generated_at` never orders competing results. Equal-source-time input differences are detected by the next selected-key digest.

## Changing this contract

Keep `pipeline.py` readable from top to bottom. Update `story.txt`, this file and `docs/architecture.md`, then run `make pre-commit`.
