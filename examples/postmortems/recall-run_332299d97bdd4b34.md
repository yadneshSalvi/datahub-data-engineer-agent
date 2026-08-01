# Stale trips_raw ingestion caused downstream trip-volume collapse

**Symptom:** agg_zone_demand row-count assertion failed: 90 rows versus expected 500..40,000; previous row count 21,400 (-99.58%).

**Root cause:** trips_raw ingestion stopped advancing: freshness was 31.01h against a 6h SLA, while row count remained 1,284,500 and schema stayed healthy. Zero upstream lineage was returned and confirm_no_upstreams was confirmed, so trips_raw is the first unhealthy asset and satisfies the stop rule.

## Causal path
agg_zone_demand → fct_trips → stg_trips → trips_raw

## Evidence
- Exact lineage: trips_raw -> stg_trips -> fct_trips -> agg_zone_demand.
- Recall fast path identified trips_raw from run_93130e4fb6f84e58; live evidence verified the diagnosis.
- DataHub reported 16 downstream facets: 15 supported assets ranked below and one unsupported MLFeature.

## Blast radius
- CRITICAL: Exec Daily Ops (3100 usage score)
- CRITICAL: fct_trips (2121 usage score)
- CRITICAL: Rides by Hour (1840 usage score)
- HIGH: agg_daily_rides (1673 usage score)
- HIGH: Revenue Trend (1420 usage score)
- HIGH: fct_revenue (1169 usage score)
- HIGH: agg_driver_earnings (1043 usage score)
- MEDIUM: Zone Demand Heatmap (960 usage score)
- MEDIUM: Finance Revenue Review (870 usage score)
- MEDIUM: agg_zone_demand (868 usage score)
- MEDIUM: Driver Ops (410 usage score)
- LOW: Driver Leaderboard (380 usage score)
- LOW: trip_eta_features (364 usage score)
- LOW: stg_trips (91 usage score)
- LOW: oncall_demo_eta_predictor (0 usage score)

## Human action
The on-call data engineer must restore raw trips ingestion, then rerun stg_trips -> fct_trips -> all downstream aggregates and features. Declare recovery only after trips_raw freshness is within 6h and assertions pass on stg_trips, fct_trips, and agg_zone_demand.

## Prevention
Add a 6h freshness alert on trips_raw and a circuit breaker that blocks downstream publication when trips_raw breaches it. Add named catalog owners and runbook links for Rides by Hour, Revenue Trend, Zone Demand Heatmap, and Driver Leaderboard.
