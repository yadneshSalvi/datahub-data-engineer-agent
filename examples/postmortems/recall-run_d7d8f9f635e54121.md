# Stale raw.trips_raw caused agg_daily_rides row-count collapse

**Symptom:** agg_daily_rides row-count assertion failed: 4 rows versus expected 25..400; previous 182, down 97.8%.

**Root cause:** Trips ingestion stopped advancing raw.trips_raw. It was 26.39 hours stale against a 6-hour SLA and has no upstream lineage, making it the first intrinsic unhealthy node.

## Causal path
agg_daily_rides → fct_trips → stg_trips → raw.trips_raw

## Evidence
- Active incident urn:li:incident:56de1e0c-77f6-45d1-a6ad-e9cad29d58b9.
- Recalled incidents run_d4beaf8a4f834584 and run_c47c5d9bd22f40b6 named the same ancestor; current evidence independently confirmed it.
- Downstream facets total 15 entities: 7 datasets, 4 charts, 3 dashboards, and 1 unsupported ML feature; 14 supported assets were ranked and tagged.

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
A human must restore and backfill trips ingestion into raw.trips_raw, verify pickup_ts advances, rerun stg_trips, fct_trips, all downstream marts, and trip_eta_features, then validate source freshness and downstream row-count assertions.

## Prevention
Add a source freshness or heartbeat assertion on raw.trips_raw pickup_ts that alerts before downstream builds, plus an ingestion retry and backfill runbook.

