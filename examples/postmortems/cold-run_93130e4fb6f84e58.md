# Trips source freshness breach collapsed downstream ride counts

**Symptom:** agg_daily_rides row-count assertion failed: 4 rows observed versus 25..400 expected; previous count 182 (-97.8%).

**Root cause:** trips_raw was 26.02h stale against a 6h SLA. Its 1,284,500 rows and required schema including pickup_ts remained intact. Empty one-hop lineage and confirm_no_upstreams=confirmed establish an intrinsic source ingestion freshness breach with no unhealthy parent.

## Causal path
agg_daily_rides → fct_trips → stg_trips → trips_raw

## Evidence
- Run ID: run_93130e4fb6f84e58.
- Healthy sibling branch excluded: stg_zones and zones_raw each had 265 rows, healthy schema, and freshness within the 168h SLA; zones_raw was confirmed as a source.
- pickup_ts on trips_raw was tagged oncall_root_cause; seven downstream datasets were tagged oncall_impacted; owners were notified.
- Active DataHub incident: urn:li:incident:oncall-b4b3a0fa025b93c7cb83b8799547adc7.

## Blast radius
- CRITICAL: Exec Daily Ops dashboard (3100 usage score)
- CRITICAL: fct_trips dataset (2121 usage score)
- HIGH: Rides by Hour chart (1840 usage score)
- HIGH: agg_daily_rides dataset (1673 usage score)
- HIGH: Revenue Trend chart (1420 usage score)
- HIGH: fct_revenue dataset (1169 usage score)
- HIGH: agg_driver_earnings dataset (1043 usage score)
- MEDIUM: Zone Demand Heatmap chart (960 usage score)
- MEDIUM: Finance Revenue Review dashboard (870 usage score)
- MEDIUM: agg_zone_demand dataset (868 usage score)
- LOW: Driver Ops dashboard (410 usage score)
- LOW: Driver Leaderboard chart (380 usage score)
- LOW: trip_eta_features dataset (364 usage score)
- LOW: stg_trips dataset (91 usage score)
- LOW: oncall_demo_eta_predictor ML model (0 usage score)

## Human action
Restore raw trips ingestion, then rerun stg_trips -> fct_trips -> all downstream aggregates and features. Validate trips_raw freshness and downstream row-count assertions before declaring recovery.

## Prevention
Add a paging freshness monitor at the 6h SLA and an ingestion heartbeat with runbook for trips_raw; add a publish circuit breaker that blocks stg_trips and downstream assets whenever trips_raw breaches its freshness SLA.
