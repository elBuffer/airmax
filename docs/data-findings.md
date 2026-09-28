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

## IRCEL-CELINE candidate source

An API probe on 28 September 2026 confirmed that IRCEL-CELINE exposes public station timeseries at `https://geo.irceline.be/sos/api/v1` under CC BY 4.0. The six AirMax pollutants were available as 27 CO, 91 NO₂, 38 O₃, 94 PM10, 84 PM2.5 and 45 SO₂ timeseries. CO appears in both µg/m³ and mg/m³, so the feasibility adapter normalizes it to mg/m³.

A replay of 17–18 September contained **7,558 non-null observations from 379 timeseries at 123 physical stations**. All stations mapped to official boundaries, covering **63 municipalities**, of which **12** had at least two stations. Pollutant coverage was 52 municipalities for NO₂, 48 each for PM10 and PM2.5, 34 for O₃, 9 for SO₂ and 7 for CO. Most active station/pollutant series supplied 24 or 25 hourly observations across the inclusive 24-hour capture, versus the six-hour delivery rhythm observed in OpenAQ.

For the large-city examples, IRCEL-CELINE supplied 7 stations in the City of Brussels, 18 in Antwerpen, 6 each in Gent and Charleroi, and 4 in Liège. It added particulate measurements where the OpenAQ capture had none in Antwerpen and broadened Liège beyond CO; Leuven had no mapped IRCEL-CELINE station in this sample.

**Preliminary comparison:** IRCEL-CELINE is better for freshness, timestamp clarity and several important cities, but much worse for nationwide breadth than the OpenAQ capture's 397 municipalities with data and 214 with multiple stations. The samples cover different durations, so this is enough to justify a combined evaluation—not a final source decision. Before combining them, measure publication delay, corrections, station overlap and source disagreement; do not average both feeds by default.

Run `make capture-ircel START=<ISO-8601> END=<ISO-8601>` to capture up to 48 hours, then `make replay-ircel` to run it through the existing transformation and dashboard contract locally. The deployed feed remains OpenAQ.

Sources: [IRCEL-CELINE open data](https://www.irceline.be/en/documentation/open-data), [API](https://geo.irceline.be/sos/api/v1/), and [dataset documentation](https://github.com/irceline/open_data).

## Verdict

**Feasible with conditions.** The architecture and worked calculation are feasible. Commercial use
is conditional on (1) loading official nationwide boundaries, (2) replaying the full recorded
capture to quantify municipal/pollutant coverage and 24-hour runtime, (3) describing
the product as latest-available source data rather than assuming the observed six-hour rhythm,
(4) presenting WHO values as indicative comparisons rather than compliance findings, and (5)
making the absence of historical backfill explicit. Until conditions 1 and 2 are met, the pipeline
is a technical proof, not defensible nationwide sales evidence.
