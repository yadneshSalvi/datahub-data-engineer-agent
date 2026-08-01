# agg_daily_rides volume collapse caused by stale raw.trips_raw feed

**Symptom:** agg_daily_rides row-count assertion failed with 4 rows versus expected 25..400; prior profile was 182 (-97.8%).

**Root cause:** Confirmed source feed was 26.03 hours stale against a 6-hour SLA (20.03 hours over). It had no upstream lineage, satisfying the stop rule. The stalled pickup_ts-bearing feed propagated through stg_trips and fct_trips.

## Causal path
agg_daily_rides → fct_trips → stg_trips → raw.trips_raw

## Evidence
- Alternative branch stg_zones and raw.zones_raw was healthy: 265 rows stable, freshness 33.61/33.63h versus 168h SLA, and schemas healthy.
- raw.zones_raw was confirmed as a source.
- Downstream facets reported 16 entities: 7 datasets, 4 charts, 3 dashboards, 1 ML model, and 1 ML feature.
- Associated DataHub incident: urn:li:incident:e89f90a1-d44f-45ed-9296-b5660088b49e.

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
- MEDIUM: Driver Ops (410 usage score)
- MEDIUM: Driver Leaderboard (380 usage score)
- MEDIUM: trip_eta_features (364 usage score)
- LOW: stg_trips (91 usage score)
- LOW: oncall_demo_eta_predictor (0 usage score)

## Human action
Data Platform must restore raw trips ingestion, verify pickup_ts delivery and watermark/checkpoint state, rerun raw→staging→marts, then rerun assertions and validate row counts before declaring fixed.

## Prevention
Add source-level freshness and minimum-arrival assertions on raw.trips_raw, alert on pickup_ts watermark lag, and gate downstream transforms whenever raw.trips_raw breaches freshness.
