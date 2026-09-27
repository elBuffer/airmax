# Data findings

## Evidence status

The repository currently contains **17 engineered regression messages**, not the analysed
55,696-message, four-day capture mentioned in the brief. It proves calculation behavior and the
Gent worked example, but it cannot support national coverage or production source-quality claims.
Those claims remain explicitly open rather than being fabricated.

## Findings

1. **Coverage — not yet established.** The checked-in reference file and fixture cover **1**
   municipality (Gent), versus roughly **565** Belgian municipalities. The fixture reproduces Gent
   PM2.5 at **13.6474010878 µg/m³** from **6 readings**, **6 location IDs**, and **5 physical sites**.
   Brussels, Antwerpen, Charleroi, and Liège have **0 measured evidence in this fixture**. Import the
   full recorded capture and official boundaries before making a sales coverage claim.
2. **Freshness — conditional.** The source analysis observed a burst about every **6 hours**, with
   about **3,481 messages** per burst. “Real-time” can only mean “latest available burst,” not a live
   sensor feed. The map exposes receipt age and marks data stale after **8 hours**.
3. **Time granularity — three hours.** In all **55,696** captured messages, `date.utc` was **0–60
   minutes ahead of SNS publish time** and differed from `date.local` by exactly **2 hours**, so it
   is not treated as a reading time; values within a burst share one generation instant rather than
   a demonstrated measurement instant. A 15-minute or one-hour average would imply unsupported
   precision. The client-defined **3-hour** window and hourly WHO comparisons always use SNS publish
   time. `date.utc` remains only for deduplication, traceability and detection of late data: a value
   more than **5 minutes older** than SNS time is tagged `late_reading` and excluded. Five minutes
   equals one dashboard refresh cycle, tolerating minor clock/transit jitter while catching a
   material backfill pattern never seen in the capture; it is policy, not a provider guarantee.
   The WHO comparison is indicative: one rolling value cannot establish exposure or compliance.
   PM2.5, PM10, NO₂, SO₂ and CO use 24-hour windows; ozone uses its WHO 8-hour period. Comparisons
   require at least 75% represented hourly slots (18/24 or 6/8) and otherwise remain explicitly
   insufficient. The checked-in fixture has only one represented hour and cannot support a WHO
   comparison.
4. **Physical versus logical coverage — material.** The regression example has **6 location IDs**
   but **5 distinct coordinate pairs**, a **20%** logical overstatement relative to physical sites
   (`(6-5)/5`). The wider analysis found **160 shared place names**, but the national overstatement
   percentage cannot be computed without the capture. Show officials both counts, led by distinct
   sites.
5. **Field quality.** The source analysis found `city == location` in **100%** of messages, so city
   cannot define municipalities. `date.utc` and `date.local` conflict by exactly two hours; both are
   semantically untrusted pending provider clarification. Four metadata fields (`isMobile`,
   `isAnalysis`, `entity`, `sensorType`) are retained but excluded. Coordinates plus official
   polygons replace city, while SNS publish time drives partitioning, windowing, freshness and
   dashboard times; raw `date.utc` remains only for validation, late-data detection, traceability
   and the deduplication key.
6. **No history.** The source is a stream with **0 backfilled winter seasons**. Raw retention builds
   history only from deployment onward. A city asking about last winter must be told that OpenAQ
   supplied no backfill and that AirMax cannot recreate it.
7. **Dependence.** AirMax controls **0** source schedules, sensors, fields, or coverage decisions.
   That is both the operational risk and the neutrality argument. Raw retention and visible
   staleness expose rather than conceal that dependence.

## Verdict

**Feasible with conditions.** The architecture and worked calculation are feasible. Commercial use
is conditional on (1) loading official nationwide boundaries, (2) replaying the full recorded
capture to quantify municipal/pollutant coverage and 24-hour runtime, (3) describing
the product as latest-available source data rather than assuming the observed six-hour rhythm,
(4) presenting WHO values as indicative comparisons rather than compliance findings, and (5)
making the absence of historical backfill explicit. Until conditions 1 and 2 are met, the pipeline
is a technical proof, not defensible nationwide sales evidence.
