# ADR-0004: Count each physical station once

**Status:** accepted

## Context

The feed publishes 1 000 location IDs at 817 physical sites (unique coordinate pairs). 160 sites
carry two or more IDs (183 extra IDs). Measured on the 4-day capture (13–17 Sep 2026):

- Every ID at a shared site has the same name and identical coordinates, and no ID ever changes
  coordinates.
- Within one delivery, each ID sends one value per pollutant, so a site with several IDs sends
  several values for the same pollutant in the same delivery. When they were measured is unknown.
  In the latest delivery, 359 of 3 097 site–pollutant pairs had 2 to 4 values.
- The feed cannot tell whether these are two instruments on one site or one station published
  twice. `sensorType` is unreliable (story.txt §5.2), and `date.utc` is SNS publish time plus an
  evenly spread 0–60 minutes, so neither can separate or rank the values.

Example (Gent, PM2.5, delivery of 17 Sep 04:13 UTC): five physical sites; Sint-Amandsberg carries
IDs 9148 and 2844, which reported 13.4 and 5.5 µg/m³ in the same delivery.

The 3-hour average divided the sum of all readings by the number of readings, so a site with three
IDs counted three times. The WHO-period calculation already averaged per site first.

## Decision

Treat location IDs at identical coordinates as co-located instruments of one station. For the
3-hour result, average the readings at each physical site first, then average the site values of
the municipality equally. `measurement_count`, `location_count` and `distinct_sites` are unchanged
and still reported.

## Basis

Official monitoring networks record co-located instruments separately but never count a station
more than once:

- US EPA designates one primary monitor per site; the site value comes from the primary, and
  co-located monitors fill in only when it has no value. When several co-located values are
  available, their average is used as the site's value.
  [40 CFR Part 50 Appendix N §3.0(d)](https://www.law.cornell.edu/cfr/text/40/appendix-N_to_part_50)
- The second instrument serves quality control: co-located pairs measure precision, with a PM2.5
  goal of a 10% coefficient of variation.
  [40 CFR Part 58 Appendix A](https://www.law.cornell.edu/cfr/text/40/appendix-A_to_part_58),
  [EPA: Use of collocated PM2.5 data](https://www.epa.gov/sites/default/files/2015-09/documents/25colo_0.pdf)
- EPA discourages merging instruments under one identifier because each has its own precision and
  bias. [EPA AQS technical note on POCs](https://www.epa.gov/aqs/aqs-tech-note-poc-6-28-13)
- European e-reporting groups sampling points under one station series.
  [EEA Air Quality e-Reporting](https://www.eea.europa.eu/en/datahub/datahubitem-view/3b390c9c-f321-490a-b25a-ae93b2ed80c1)
- OpenAQ allows several sensors per location and passes duplicate locations on as received.
  [OpenAQ sensors](https://docs.openaq.org/resources/sensors),
  [openaq/project-universal-stationID #12](https://github.com/openaq/project-universal-stationID/issues/12)

The feed names no primary instrument, so the Appendix N fallback applies: average the co-located
values into one station value.

## Consequences

On the latest 3-hour window, 205 of 1 873 municipality–pollutant values change; the median change
is 7%, 90% change by less than 19%, and the largest is 32% (Hamont-Achel PM10: 19.7 → 26.0). Gent
PM2.5 moves from 13.6 to 14.5 µg/m³.

## Different values at one site

Values from the same site in one delivery often differ widely. The feed cannot show whether they were
measured at the same time, so the difference is not proof that the instruments contradict each other:

- Across the capture, 5 744 site–pollutant–delivery groups hold two or more values. Their spread
  (maximum minus minimum) is a median 69% of their mean; a quarter exceed 121%.
- For PM2.5, 490 of 960 groups (51%) fail the screening EPA researchers applied to paired low-cost
  PM2.5 channels, which discards pairs that differ by more than 5 µg/m³ **and** 61%.
  [Barkjohn et al., AMT 2021](https://amt.copernicus.org/articles/14/4617/2021/) That rule was set
  for simultaneous 24-hour averages of one low-cost sensor's two channels; it is used here only as a
  scale.

Handling:

1. **Average, do not drop.** Nothing in the feed shows which value is right. Dropping differing
   pairs would remove about half of the multi-ID PM2.5 data and hide the problem. The average is the
   documented fallback, not proof that the value is right.
2. **Keep every raw value.** The raw archive keeps all readings unchanged, so the rule can be
   replayed if a primary instrument is identified later.
3. **Not implemented yet:** report per result how many stations have differing values, so
   the dashboard can show it next to the value.
4. **Open with the provider:** ask OpenAQ whether shared-coordinate IDs are separate instruments,
   and check a sample against IRCEL-CELINE (see `docs/presentation/questions.txt`).
