# agg_zone_demand volume collapse caused by stale raw.trips_raw

**Symptom:** Row-count assertion observed 90 versus expected 500..40,000; rows fell 21,400→90 (-99.58%) despite healthy freshness of 1.21h/6h.

**Root cause:** Intrinsic source freshness breach: raw.trips_raw was 31.01h stale against a 6h SLA, with no upstreams. Its unchanged 1,284,500 rows and healthy required schema show ingestion stopped rather than downstream schema failure.

## Causal path
agg_zone_demand → fct_trips → stg_trips → raw.trips_raw

## Evidence
- Exact lineage: raw.trips_raw → stg_trips → fct_trips → agg_zone_demand.
- Recall fast path matched run_34f92ac9c7234f76 on raw.trips_raw; live evidence verified it, so sibling exploration was skipped.
- Critical VOLUME incident urn:li:incident:f72266aa-286e-4f41-b5a8-e1c2c9d56a1b was raised on the symptom.
- Root was tagged oncall_root_cause at pickup_ts; 15 supported downstream assets were tagged oncall_impacted; symptom was tagged oncall_triaged; six root/top-impact owner URNs were notified.
- Sixteen downstream entities were found: 7 datasets, 4 charts, 3 dashboards, 1 ML model, and 1 unsupported ML feature. The typed blast radius includes the 15 supported assets.

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
Data Platform must restore raw trips ingestion, verify pickup_ts delivery and checkpoint/watermark state, rerun raw→staging→marts, rerun assertions, and validate row counts before declaring the incident fixed.

## Prevention
On raw.trips_raw, add a 6h source-freshness alert and checkpoint/watermark monitor, and install a circuit breaker that blocks staging and marts runs when the SLA is missed. Assign catalog owners to Rides by Hour and the other unowned BI charts.
