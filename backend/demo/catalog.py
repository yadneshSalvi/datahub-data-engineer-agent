"""Declarative RideFlow demo catalog shared by seed, break, reset, and tests."""

from __future__ import annotations

from dataclasses import dataclass

import datahub.emitter.mce_builder as builder

from oncall_agent.datahub.urns import dataset_urn

DOMAIN_URN = builder.make_domain_urn("oncall_demo_rideflow")
POSTMORTEM_PROPERTY_URN = "urn:li:structuredProperty:oncall.postmortem"
TAG_NAMES = ("oncall_root_cause", "oncall_impacted", "oncall_triaged")


@dataclass(frozen=True, slots=True)
class PersonSpec:
    """Seeded person metadata."""

    username: str
    display_name: str
    title: str
    email: str

    @property
    def urn(self) -> str:
        """Return the corp-user URN."""

        return f"urn:li:corpuser:{self.username}"


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    """A dataset and its healthy baseline metrics."""

    key: str
    columns: tuple[tuple[str, str], ...]
    sla_hours: int
    owner: str
    group: str
    row_count: int
    daily_queries: int
    unique_users: int

    @property
    def name(self) -> str:
        """Return the fully qualified dataset name."""

        return f"oncall_demo.{self.key}"

    @property
    def urn(self) -> str:
        """Return the deterministic dataset URN."""

        return dataset_urn(self.key)


@dataclass(frozen=True, slots=True)
class LineageSpec:
    """One explicit dataset lineage edge."""

    upstream: str
    downstream: str
    columns: dict[str, list[str]]
    transformation: str | None = None


PEOPLE = (
    PersonSpec("maya.chen", "Maya Chen", "Staff Data Engineer", "maya.chen@rideflow.example"),
    PersonSpec("sam.patel", "Sam Patel", "Analytics Engineer", "sam.patel@rideflow.example"),
    PersonSpec("raj.iyer", "Raj Iyer", "Data Engineer, Finance", "raj.iyer@rideflow.example"),
    PersonSpec(
        "nina.alvarez",
        "Nina Alvarez",
        "ML Platform Engineer",
        "nina.alvarez@rideflow.example",
    ),
    PersonSpec("dana.wu", "Dana Wu", "Director, Ops Analytics", "dana.wu@rideflow.example"),
)

GROUPS = ("data-platform", "analytics", "finance", "ml-platform", "exec")

DATASETS = (
    DatasetSpec(
        "raw.trips_raw",
        (
            ("trip_id", "string"),
            ("pickup_ts", "timestamp"),
            ("dropoff_ts", "timestamp"),
            ("pickup_zone_id", "int"),
            ("dropoff_zone_id", "int"),
            ("driver_id", "string"),
            ("fare_amount", "double"),
            ("surge_multiplier", "double"),
        ),
        6,
        "maya.chen",
        "data-platform",
        1_284_500,
        4,
        2,
    ),
    DatasetSpec(
        "raw.drivers_raw",
        (
            ("driver_id", "string"),
            ("driver_name", "string"),
            ("onboarded_at", "timestamp"),
            ("home_zone_id", "int"),
            ("rating", "double"),
        ),
        24,
        "maya.chen",
        "data-platform",
        18_400,
        2,
        1,
    ),
    DatasetSpec(
        "raw.payments_raw",
        (
            ("payment_id", "string"),
            ("trip_id", "string"),
            ("amount", "double"),
            ("tip_amount", "double"),
            ("method", "string"),
            ("paid_at", "timestamp"),
        ),
        6,
        "raj.iyer",
        "data-platform",
        1_261_000,
        3,
        2,
    ),
    DatasetSpec(
        "raw.zones_raw",
        (("zone_id", "int"), ("zone_name", "string"), ("borough", "string")),
        168,
        "raj.iyer",
        "data-platform",
        265,
        1,
        1,
    ),
    DatasetSpec(
        "staging.stg_trips",
        (
            ("trip_id", "string"),
            ("pickup_ts", "timestamp"),
            ("dropoff_ts", "timestamp"),
            ("pickup_zone_id", "int"),
            ("dropoff_zone_id", "int"),
            ("driver_id", "string"),
            ("fare_amount", "double"),
            ("trip_minutes", "double"),
        ),
        6,
        "sam.patel",
        "analytics",
        1_281_900,
        22,
        5,
    ),
    DatasetSpec(
        "staging.stg_drivers",
        (
            ("driver_id", "string"),
            ("driver_name", "string"),
            ("onboarded_at", "timestamp"),
            ("home_zone_id", "int"),
            ("rating", "double"),
        ),
        24,
        "sam.patel",
        "analytics",
        18_400,
        8,
        3,
    ),
    DatasetSpec(
        "staging.stg_payments",
        (
            ("payment_id", "string"),
            ("trip_id", "string"),
            ("amount", "double"),
            ("tip_amount", "double"),
            ("method", "string"),
            ("paid_at", "timestamp"),
        ),
        6,
        "sam.patel",
        "analytics",
        1_258_700,
        14,
        4,
    ),
    DatasetSpec(
        "staging.stg_zones",
        (("zone_id", "int"), ("zone_name", "string"), ("borough", "string")),
        168,
        "sam.patel",
        "analytics",
        265,
        6,
        3,
    ),
    DatasetSpec(
        "marts.fct_trips",
        (
            ("trip_id", "string"),
            ("pickup_ts", "timestamp"),
            ("pickup_zone_id", "int"),
            ("pickup_zone_name", "string"),
            ("dropoff_zone_id", "int"),
            ("driver_id", "string"),
            ("fare_amount", "double"),
            ("trip_minutes", "double"),
        ),
        6,
        "sam.patel",
        "analytics",
        1_281_900,
        312,
        19,
    ),
    DatasetSpec(
        "marts.fct_revenue",
        (
            ("payment_id", "string"),
            ("trip_id", "string"),
            ("pickup_ts", "timestamp"),
            ("gross_amount", "double"),
            ("tip_amount", "double"),
            ("net_amount", "double"),
        ),
        6,
        "raj.iyer",
        "finance",
        1_258_700,
        176,
        12,
    ),
    DatasetSpec(
        "marts.dim_driver",
        (
            ("driver_id", "string"),
            ("driver_name", "string"),
            ("home_zone_id", "int"),
            ("rating", "double"),
            ("tenure_days", "int"),
        ),
        24,
        "sam.patel",
        "analytics",
        18_400,
        94,
        9,
    ),
    DatasetSpec(
        "marts.agg_daily_rides",
        (
            ("day", "date"),
            ("rides", "long"),
            ("avg_fare", "double"),
            ("avg_trip_minutes", "double"),
        ),
        6,
        "sam.patel",
        "analytics",
        182,
        248,
        22,
    ),
    DatasetSpec(
        "marts.agg_zone_demand",
        (
            ("day", "date"),
            ("pickup_zone_id", "int"),
            ("pickup_zone_name", "string"),
            ("rides", "long"),
            ("surge_avg", "double"),
        ),
        6,
        "sam.patel",
        "analytics",
        21_400,
        133,
        11,
    ),
    DatasetSpec(
        "marts.agg_driver_earnings",
        (
            ("day", "date"),
            ("driver_id", "string"),
            ("driver_name", "string"),
            ("trips", "long"),
            ("net_earnings", "double"),
        ),
        24,
        "raj.iyer",
        "finance",
        96_700,
        158,
        14,
    ),
    DatasetSpec(
        "ml.trip_eta_features",
        (
            ("trip_id", "string"),
            ("pickup_zone_id", "int"),
            ("pickup_hour", "int"),
            ("trip_minutes", "double"),
            ("surge_multiplier", "double"),
        ),
        6,
        "nina.alvarez",
        "ml-platform",
        1_281_900,
        61,
        4,
    ),
)

DATASET_BY_KEY = {dataset.key: dataset for dataset in DATASETS}


def _same(*columns: str) -> dict[str, list[str]]:
    return {column: [column] for column in columns}


LINEAGE = (
    LineageSpec(
        "raw.trips_raw",
        "staging.stg_trips",
        {
            **_same(
                "trip_id",
                "pickup_ts",
                "dropoff_ts",
                "pickup_zone_id",
                "dropoff_zone_id",
                "driver_id",
                "fare_amount",
            ),
            "trip_minutes": ["dropoff_ts", "pickup_ts"],
        },
        "SELECT trip_id, pickup_ts, dropoff_ts, pickup_zone_id, dropoff_zone_id, driver_id, "
        "fare_amount, date_diff('minute', pickup_ts, dropoff_ts) AS trip_minutes FROM trips_raw",
    ),
    LineageSpec(
        "raw.drivers_raw",
        "staging.stg_drivers",
        _same("driver_id", "driver_name", "onboarded_at", "home_zone_id", "rating"),
    ),
    LineageSpec(
        "raw.payments_raw",
        "staging.stg_payments",
        _same("payment_id", "trip_id", "amount", "tip_amount", "method", "paid_at"),
    ),
    LineageSpec("raw.zones_raw", "staging.stg_zones", _same("zone_id", "zone_name", "borough")),
    LineageSpec(
        "staging.stg_trips",
        "marts.fct_trips",
        _same(
            "trip_id",
            "pickup_ts",
            "pickup_zone_id",
            "dropoff_zone_id",
            "driver_id",
            "fare_amount",
            "trip_minutes",
        ),
        "SELECT t.trip_id, t.pickup_ts, t.pickup_zone_id, z.zone_name AS pickup_zone_name, "
        "t.dropoff_zone_id, t.driver_id, t.fare_amount, t.trip_minutes FROM stg_trips t "
        "JOIN stg_zones z ON t.pickup_zone_id = z.zone_id",
    ),
    LineageSpec("staging.stg_zones", "marts.fct_trips", {"pickup_zone_name": ["zone_name"]}),
    LineageSpec(
        "staging.stg_payments",
        "marts.fct_revenue",
        {
            "payment_id": ["payment_id"],
            "trip_id": ["trip_id"],
            "gross_amount": ["amount"],
            "tip_amount": ["tip_amount"],
            "net_amount": ["amount", "tip_amount"],
        },
    ),
    LineageSpec("staging.stg_trips", "marts.fct_revenue", {"pickup_ts": ["pickup_ts"]}),
    LineageSpec(
        "staging.stg_drivers",
        "marts.dim_driver",
        {
            **_same("driver_id", "driver_name", "home_zone_id", "rating"),
            "tenure_days": ["onboarded_at"],
        },
    ),
    LineageSpec("staging.stg_zones", "marts.dim_driver", {"home_zone_id": ["zone_id"]}),
    LineageSpec(
        "marts.fct_trips",
        "marts.agg_daily_rides",
        {
            "day": ["pickup_ts"],
            "rides": ["trip_id"],
            "avg_fare": ["fare_amount"],
            "avg_trip_minutes": ["trip_minutes"],
        },
        "SELECT date(pickup_ts) AS day, count(*) AS rides, avg(fare_amount) AS avg_fare, "
        "avg(trip_minutes) AS avg_trip_minutes FROM fct_trips GROUP BY 1",
    ),
    LineageSpec(
        "marts.fct_trips",
        "marts.agg_zone_demand",
        {
            "day": ["pickup_ts"],
            "pickup_zone_id": ["pickup_zone_id"],
            "pickup_zone_name": ["pickup_zone_name"],
            "rides": ["trip_id"],
            "surge_avg": ["fare_amount"],
        },
        "SELECT date(pickup_ts) AS day, pickup_zone_id, pickup_zone_name, count(*) AS rides, "
        "avg(fare_amount) AS surge_avg FROM fct_trips GROUP BY 1, 2, 3",
    ),
    LineageSpec(
        "marts.fct_revenue",
        "marts.agg_driver_earnings",
        {
            "day": ["pickup_ts"],
            "trips": ["trip_id"],
            "net_earnings": ["net_amount"],
        },
    ),
    LineageSpec(
        "marts.dim_driver",
        "marts.agg_driver_earnings",
        _same("driver_id", "driver_name"),
    ),
    LineageSpec(
        "marts.fct_trips",
        "ml.trip_eta_features",
        {
            "trip_id": ["trip_id"],
            "pickup_zone_id": ["pickup_zone_id"],
            "pickup_hour": ["pickup_ts"],
            "trip_minutes": ["trip_minutes"],
            "surge_multiplier": ["fare_amount"],
        },
    ),
)

CHARTS = (
    ("oncall_demo_rides_by_hour", "Rides by Hour", "marts.agg_daily_rides", 1840),
    ("oncall_demo_zone_heatmap", "Zone Demand Heatmap", "marts.agg_zone_demand", 960),
    ("oncall_demo_revenue_trend", "Revenue Trend", "marts.agg_driver_earnings", 1420),
    (
        "oncall_demo_driver_leaderboard",
        "Driver Leaderboard",
        "marts.agg_driver_earnings",
        380,
    ),
)

DASHBOARDS = (
    (
        "oncall_demo_exec_daily_ops",
        "Exec Daily Ops",
        ("oncall_demo_rides_by_hour", "oncall_demo_zone_heatmap"),
        3100,
        "dana.wu",
        "exec",
    ),
    (
        "oncall_demo_finance_review",
        "Finance Revenue Review",
        ("oncall_demo_revenue_trend",),
        870,
        "raj.iyer",
        "finance",
    ),
    (
        "oncall_demo_driver_ops",
        "Driver Ops",
        ("oncall_demo_driver_leaderboard",),
        410,
        "nina.alvarez",
        "ml-platform",
    ),
)

ML_MODEL_ID = "oncall_demo_eta_predictor"
ML_MODEL_URN = builder.make_ml_model_urn("mlflow", ML_MODEL_ID, "PROD")
ML_FEATURE_URN = builder.make_ml_feature_urn("oncall_demo_trip_eta_features", "input")

ASSERTIONS = (
    (
        "oncall-fct_trips-rowcount",
        "marts.fct_trips",
        "ROW_COUNT",
        "BETWEEN",
        "50000",
        "2000000",
        None,
    ),
    (
        "oncall-fct_trips-zone-notnull",
        "marts.fct_trips",
        "NULL_COUNT",
        "EQUAL_TO",
        "0",
        None,
        "pickup_zone_id",
    ),
    (
        "oncall-agg_daily_rides-rowcount",
        "marts.agg_daily_rides",
        "ROW_COUNT",
        "BETWEEN",
        "25",
        "400",
        None,
    ),
    (
        "oncall-agg_zone_demand-rowcount",
        "marts.agg_zone_demand",
        "ROW_COUNT",
        "BETWEEN",
        "500",
        "40000",
        None,
    ),
    (
        "oncall-fct_revenue-rowcount",
        "marts.fct_revenue",
        "ROW_COUNT",
        "BETWEEN",
        "40000",
        "2000000",
        None,
    ),
    (
        "oncall-stg_trips-rowcount",
        "staging.stg_trips",
        "ROW_COUNT",
        "BETWEEN",
        "50000",
        "2500000",
        None,
    ),
    (
        "oncall-dim_driver-rowcount",
        "marts.dim_driver",
        "ROW_COUNT",
        "BETWEEN",
        "500",
        "100000",
        None,
    ),
    (
        "oncall-dim_driver-rating-notnull",
        "marts.dim_driver",
        "NULL_COUNT",
        "EQUAL_TO",
        "0",
        None,
        "rating",
    ),
    (
        "oncall-trip_eta_features-rowcount",
        "ml.trip_eta_features",
        "ROW_COUNT",
        "BETWEEN",
        "50000",
        "2000000",
        None,
    ),
)

QUERY_SPECS = (
    (
        "daily-rides",
        "Daily rides rollup",
        "marts.agg_daily_rides",
        "MANUAL",
        "SELECT day, rides, avg_fare, avg_trip_minutes\n"
        "FROM oncall_demo.marts.agg_daily_rides\n"
        "ORDER BY day DESC",
    ),
    (
        "zone-demand",
        "Zone demand by hour",
        "marts.agg_zone_demand",
        "SYSTEM",
        "SELECT day, pickup_zone_name, rides, surge_avg\n"
        "FROM oncall_demo.marts.agg_zone_demand\n"
        "WHERE day >= current_date - interval '7' day",
    ),
    (
        "fct-trips-scan",
        "Trip fact ad-hoc scan",
        "marts.fct_trips",
        "MANUAL",
        "SELECT pickup_ts, pickup_zone_name, fare_amount, trip_minutes\n"
        "FROM oncall_demo.marts.fct_trips\n"
        "WHERE pickup_ts >= current_timestamp - interval '1' hour",
    ),
    (
        "revenue-recon",
        "Revenue reconciliation",
        "marts.fct_revenue",
        "MANUAL",
        "SELECT date(pickup_ts) AS day, sum(gross_amount), sum(net_amount)\n"
        "FROM oncall_demo.marts.fct_revenue\n"
        "GROUP BY 1 ORDER BY 1 DESC",
    ),
    (
        "eta-features",
        "ETA feature extraction",
        "ml.trip_eta_features",
        "SYSTEM",
        "SELECT trip_id, pickup_zone_id, pickup_hour, trip_minutes, surge_multiplier\n"
        "FROM oncall_demo.ml.trip_eta_features",
    ),
)


def chart_urn(name: str) -> str:
    """Return a deterministic Looker chart URN."""

    return builder.make_chart_urn("looker", name)


def dashboard_urn(name: str) -> str:
    """Return a deterministic Looker dashboard URN."""

    return builder.make_dashboard_urn("looker", name)
