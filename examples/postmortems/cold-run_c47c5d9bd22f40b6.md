# Stale raw.trips_raw feed caused agg_daily_rides volume collapse

**Symptom:** agg_daily_rides row-count assertion observed 4, expected 25..400; previous row count 182, a 97.8% decrease. Freshness remained healthy at 1.21 hours against a 6-hour SLA, and its four-field schema was intact.

**Root cause:** Source feed stalled at pickup_ts. raw.trips_raw was 26.02 hours stale against a 6-hour SLA, breaching by 20.02 hours. It has no upstreams, so the breach is intrinsic. Its stable 1,284,500-row snapshot shows a stall, not truncation.

## Causal path
agg_daily_rides → fct_trips → stg_trips → raw.trips_raw

## Evidence
- Healthy sibling stg_zones remained at 265 vs 265 rows and 33.61h freshness against a 168h SLA, ruling it out.
- Lineage facets total 15: 7 datasets, 4 charts, 3 dashboards, and 1 ML feature; 14 supported assets are ranked below.
- Active DataHub incident: urn:li:incident:56de1e0c-77f6-45d1-a6ad-e9cad29d58b9.

## Blast radius
- CRITICAL: Exec Daily Ops (3100 usage score)
- CRITICAL: fct_trips (2121 usage score)
- HIGH: Rides by Hour (1840 usage score)
- HIGH: agg_daily_rides (1673 usage score)
- HIGH: Revenue Trend (1420 usage score)
- HIGH: fct_revenue (1169 usage score)
- HIGH: agg_driver_earnings (1043 usage score)
- MEDIUM: Zone Demand Heatmap (960 usage score)
- MEDIUM: Finance Revenue Review (870 usage score)
- MEDIUM: agg_zone_demand (868 usage score)
- LOW: Driver Ops (410 usage score)
- LOW: Driver Leaderboard (380 usage score)
- LOW: trip_eta_features (364 usage score)
- LOW: stg_trips (91 usage score)

## Human action
A human must restore and backfill trips ingestion into raw.trips_raw, validate pickup_ts progression, rerun stg_trips, fct_trips, and all downstream marts/features, then verify freshness and row-count assertions before resolving the incident.

## Prevention
On raw.trips_raw, add a pickup_ts watermark/progression assertion and source-freshness alert, enforce a minimum incremental batch-volume check before publication, and gate dependent jobs whenever its 6-hour SLA is missed.

