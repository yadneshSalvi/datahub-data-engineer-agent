# Stale raw.trips_raw feed caused downstream trip-volume collapse

**Symptom:** agg_zone_demand row-count assertion failed with 90 rows versus expected 500..40,000.

**Root cause:** raw.trips_raw ingestion was 31.01 hours stale against its 6-hour SLA. It is a confirmed source with no upstreams, making the breach intrinsic and satisfying the stop rule.

## Causal path
agg_zone_demand → fct_trips → stg_trips → raw.trips_raw

## Evidence
- Exact causal lineage is raw.trips_raw → stg_trips → fct_trips → agg_zone_demand.
- Prior incident run_f1243c12dea94730 named raw.trips_raw; live verification confirmed it and licensed the recall fast path.
- Blast-radius facets returned 16 entities: 7 datasets, 4 charts, 3 dashboards, 1 ML model, and 1 unsupported ML feature.
- Critical VOLUME incident raised; root and 15 supported impacts tagged; owners notified; no data modified.

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
- LOW: ETA predictor (0 usage score)

## Human action
Restore raw.trips_raw pickup_ts ingestion; rerun stg_trips, fct_trips, and all downstream marts/features; then verify source freshness and every row-count assertion before resolving the incident.

## Prevention
Page on raw.trips_raw source freshness and pickup_ts heartbeat/lag, and block downstream publishes whenever raw.trips_raw exceeds its 6-hour SLA.
