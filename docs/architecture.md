# Architecture

This project implements a real-time medallion architecture. Events are produced by a web
application, buffered in Azure Event Hubs, and progressively refined across three layers of
Delta tables in Databricks.

## End-to-end flow

```
┌─────────────────┐
│  FastAPI app    │  api.py + templates/
│  "Book a Ride"  │  generates one ride confirmation per click
└────────┬────────┘
         │ JSON event (single-event batch)
         ▼
┌─────────────────┐
│ Azure Event Hub │  namespace: uberevents / hub: ubertopic
│  (Kafka-compat) │  retains events for the configured window
└────────┬────────┘
         │ Spark Structured Streaming, Kafka connector
         ▼
┌──────────────────────────────────────────────────────────┐
│                     BRONZE  (raw)                        │
│  rides_raw      ← streaming, event payload cast to string│
│  map_*          ← batch load from ADLS Gen2              │
│  bulk_rides     ← one-time historical seed (2,000 rows)  │
└────────┬─────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────┐
│                     SILVER  (cleansed)                   │
│  stg_rides      ← two append flows: bulk + stream        │
│                   JSON parsed against rides_schema       │
│  silver_obt     ← stg_rides LEFT JOIN 6 mapping tables,  │
│                   watermarked on booking_timestamp       │
└────────┬─────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────┐
│                      GOLD  (modelled)                    │
│  dim_passenger, dim_driver, dim_vehicle,                 │
│  dim_payment, dim_booking      → SCD Type 1              │
│  dim_location                  → SCD Type 2              │
│  fact                          → ride measures           │
└──────────────────────────────────────────────────────────┘
```

## Components

### Producer — FastAPI web application

[api.py](../api.py) serves two pages. The `/book` route calls
`generate_uber_ride_confirmation()` in [data.py](../data.py) to build a single synthetic ride
record, then hands it to `send_to_event_hub()` in [connection.py](../connection.py), which
serialises it to JSON and publishes it as a one-event batch.

Each record is deliberately shaped like a denormalised booking confirmation: it carries natural
keys (`ride_id`, `passenger_id`, `driver_id`, …), foreign keys into the mapping tables
(`vehicle_type_id`, `payment_method_id`, …), descriptive attributes, and numeric measures.

See [web-app.md](web-app.md) for details.

### Transport — Azure Event Hubs

The hub is consumed through its **Kafka-compatible endpoint** rather than the native AMQP SDK,
which lets Spark use its standard `kafka` source. The producer side uses the native
`azure-eventhub` SDK. Authentication on the Spark side is `SASL_SSL` / `PLAIN` with the literal
username `$ConnectionString` and the connection string as the password.

### Reference data — ADLS Gen2

Six mapping files plus a bulk seed file live in an ADLS Gen2 container and are read into bronze
Delta tables. These supply the descriptive attributes the streaming events only reference by id:
cities, vehicle makes, vehicle types (and their fare rates), payment methods, ride statuses, and
cancellation reasons. Local copies are kept in [Data/](../Data) so the reference values are
visible without cloud access.

### Orchestration — Azure Data Factory

ADF coordinates the batch side of the platform: landing the reference files into ADLS Gen2 and
triggering the Databricks initial load. The streaming path runs continuously in Databricks and
does not need per-run orchestration.

### Processing — Databricks Lakeflow Declarative Pipelines

The transformation layers are declared with `from pyspark import pipelines as dp`. Rather than
writing imperative jobs, each table is declared as a function and the runtime resolves the
dependency graph, manages checkpoints, and handles incremental processing.

Two capabilities do most of the work:

- **`dp.append_flow`** lets several sources feed one target table. `stg_rides` receives both the
  historical bulk load and the live stream, so backfill and real-time data converge without a
  separate merge step.
- **`dp.create_auto_cdc_flow`** maintains dimensions from a stream, applying either SCD Type 1
  (overwrite) or SCD Type 2 (versioned rows with `__START_AT` / `__END_AT`).

See [pipeline.md](pipeline.md) for a flow-by-flow walkthrough.

## Design notes

**Why a one-big-table (OBT) in silver?** Joining the stream to all six mapping tables once, into
`silver_obt`, means the gold layer never re-joins. Every dimension and the fact table are simple
projections of that single table, which keeps the streaming graph shallow and avoids repeating
the same joins in seven places.

**Why a watermark?** `silver_obt` declares
`WATERMARK booking_timestamp DELAY OF INTERVAL 3 MINUTES`. Stream-to-table joins need a bound on
how long state is retained; the watermark tells Spark it may discard join state for events older
than three minutes behind the high-water mark, keeping memory bounded.

**Why is the OBT generated from a Jinja template?** The join is wide and repetitive — seven
tables, dozens of columns. [silver_obt.ipynb](../Code_Files/silver_obt.ipynb) keeps the join as a
declarative `jinja_config` list and renders the SQL from it, so adding a mapping table is a
config entry rather than a hand-edited join. The rendered output is committed as
[silver_obt.sql](../Code_Files/silver_obt.sql).

**Why is `dim_location` SCD Type 2?** City attributes such as region can be reorganised over
time, and historical rides should still roll up to the region that was in effect when the ride
happened. The other dimensions carry no such history requirement and use SCD Type 1.
