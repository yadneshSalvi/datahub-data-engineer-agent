# agg_daily_rides collapse caused by stalled raw trips ingestion

**Symptom:** agg_daily_rides assertion failed: 4 rows observed versus 25..400 expected; previous count 182, down 97.8%. Freshness remained healthy at 1.21h against a 6h SLA.

**Root cause:** The raw trips/pickup_ts ingestion stalled. raw.trips_raw was 26.02h stale against a 6h SLA, while row count remained 1,284,500 and required schema remained present. It has no upstreams, satisfying the root-cause stop rule.

## Causal path
agg_daily_rides → fct_trips → stg_trips → raw.trips_raw

## Evidence
- The failure propagated in causal order: raw.trips_raw → stg_trips → fct_trips → agg_daily_rides.
- Healthy sibling branch excluded: stg_zones remained 265 rows at 33.61h/168h; zones_raw remained 265 rows at 33.62h/168h with healthy schema and no upstreams.
- Downstream facets reported 16 entities: 7 datasets, 4 charts, 3 dashboards, 1 ML model, and 1 unsupported ML feature excluded from metadata actions.
- Agent did not modify data.

## Blast radius
- CRITICAL: Exec Daily Ops (3100 usage score)
- CRITICAL: fct_trips (2121 usage score)
- CRITICAL: Rides by Hour (1840 usage score)
- CRITICAL: agg_daily_rides (1673 usage score)
- HIGH: Revenue Trend (1420 usage score)
- HIGH: fct_revenue (1169 usage score)
- HIGH: agg_driver_earnings (1043 usage score)
- HIGH: Zone Demand Heatmap (960 usage score)
- HIGH: Finance Revenue Review (870 usage score)
- HIGH: agg_zone_demand (868 usage score)
- MEDIUM: Driver Ops (410 usage score)
- MEDIUM: Driver Leaderboard (380 usage score)
- MEDIUM: trip_eta_features (364 usage score)
- LOW: stg_trips (91 usage score)
- LOW: ETA predictor (0 usage score)

## Human action
A data engineer must restore raw.trips_raw pickup_ts ingestion, rerun stg_trips, fct_trips, and all dependent marts/features, then verify freshness and row-count assertions before resolving the incident.

## Prevention
Add freshness and volume alerts plus a pickup_ts ingestion heartbeat on raw.trips_raw; enforce a downstream publication circuit breaker whenever its source watermark is older than 6h.
