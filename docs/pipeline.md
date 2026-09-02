# The Databricks Pipeline

All transformation logic is declared with Lakeflow Declarative Pipelines
(`from pyspark import pipelines as dp`). Each table is a decorated function; the runtime builds
the dependency graph, manages checkpoints, and processes incrementally.

Source files, in dependency order:

| File | Layer | Produces |
| --- | --- | --- |
| [ingest.py](../Code_Files/ingest.py) | Bronze | `rides_raw` |
| [bronze_adls.ipynb](../Code_Files/bronze_adls.ipynb) | Bronze | `map_*`, `bulk_rides` |
| [silver.py](../Code_Files/silver.py) | Silver | `stg_rides` |
| [silver_obt.sql](../Code_Files/silver_obt.sql) | Silver | `silver_obt` |
| [model.py](../Code_Files/model.py) | Gold | `dim_*`, `fact` |

## Bronze — streaming ingest

[ingest.py](../Code_Files/ingest.py) reads the Event Hub through its Kafka-compatible endpoint:

```python
KAFKA_OPTIONS = {
  "kafka.bootstrap.servers"  : f"{EH_NAMESPACE}.servicebus.windows.net:9093",
  "subscribe"                : EH_NAME,
  "kafka.sasl.mechanism"     : "PLAIN",
  "kafka.security.protocol"  : "SASL_SSL",
  ...
}
```

Authentication uses the literal username `$ConnectionString` with the connection string as the
password — the standard Event Hubs Kafka pattern. The credential comes from
`spark.conf.get("connection_string")`, supplied as pipeline configuration.

Options worth knowing:

| Option | Value | Effect |
| --- | --- | --- |
| `startingOffsets` | `earliest` | First run reads the full retained history of the hub |
| `maxOffsetsPerTrigger` | `10000` | Caps events per micro-batch, bounding batch size |
| `failOnDataLoss` | `true` | Fails rather than silently skipping events aged out of retention |
| `kafka.request.timeout.ms` | `10000` | Fails fast on connectivity problems |

The `rides_raw` table keeps Kafka's envelope columns and adds `rides`, the binary `value` cast to
a string. Nothing is parsed here — bronze stays faithful to what arrived.

## Bronze — reference and seed load

[bronze_adls.ipynb](../Code_Files/bronze_adls.ipynb) is a notebook rather than a pipeline file
because it is a batch load, not a stream. It reads each mapping file from ADLS Gen2 with pandas,
converts to Spark, and writes Delta with `mode("overwrite")` and `overwriteSchema`, so it is safe
to re-run whenever reference data changes.

The `bulk_rides` load is deliberately different — it is guarded:

```python
if not spark.catalog.tableExists("uber.bronze.bulk_rides"):
    ...
    print("This will not run more than 1 time")
```

`stg_rides` consumes `bulk_rides` as a stream. Overwriting the table would re-emit all 2,000
historical rides, so the guard keeps the seed load genuinely one-time.

## Silver — staging

[silver.py](../Code_Files/silver.py) is where the historical and live paths converge. It creates
an empty streaming table and attaches two append flows to it:

```python
dp.create_streaming_table("stg_rides")

@dp.append_flow(target = "stg_rides")
def rides_bulk():        # historical seed
    ...

@dp.append_flow(target = "stg_rides")
def rides_stream():      # live events
    ...
```

This is the key pattern of the silver layer: one target, several independent sources, each with
its own checkpoint. Backfill and real-time ingestion land in the same table without a union or a
separate merge job, and either flow can be added or replayed without disturbing the other.

- **`rides_bulk`** streams from `bulk_rides` and casts `booking_timestamp`, `pickup_timestamp`,
  and `dropoff_timestamp` to timestamps, since the JSON seed carries them as strings. Both flows
  write to the same target, so their schemas have to agree.
- **`rides_stream`** streams from `rides_raw` and parses the string payload against
  `rides_schema` with `from_json`, then flattens with `select("parsed_rides.*")`.

`rides_schema` is an explicit 43-field `StructType`. Declaring it rather than inferring it keeps
the streaming schema stable across restarts. All three timestamp columns are typed as
`TimestampType`, so none of them needs a downstream cast. Note that `from_json` returns nulls for
a payload that does not match — a producer/schema mismatch shows up as empty columns rather than
an error.

The same schema is duplicated in [silver_obt.ipynb](../Code_Files/silver_obt.ipynb) for
interactive work; the two must be kept in step.

## Silver — the one-big-table

[silver_obt.sql](../Code_Files/silver_obt.sql) enriches the staged stream against all six mapping
tables in a single pass:

```sql
CREATE OR REFRESH STREAMING TABLE silver_obt AS
SELECT ...
FROM STREAM (uber.bronze.stg_rides)
     WATERMARK booking_timestamp DELAY OF INTERVAL 3 MINUTES stg_rides
LEFT JOIN uber.bronze.map_vehicle_makes ...
LEFT JOIN uber.bronze.map_vehicle_types ...
LEFT JOIN uber.bronze.map_ride_statuses ...
LEFT JOIN uber.bronze.map_payment_methods ...
LEFT JOIN uber.bronze.map_cities ...
LEFT JOIN uber.bronze.map_cancellation_reasons ...
```

Three things to note:

- **`STREAM(...)` on the fact side only.** The mapping tables are read as static snapshots, so
  each arriving ride is enriched against current reference data.
- **The watermark bounds join state.** Without it, Spark would retain streaming state
  indefinitely. Three minutes past the high-water mark of `booking_timestamp` is the retention
  bound.
- **`LEFT JOIN` throughout.** An unmatched reference id yields nulls rather than dropping the
  ride — a lost mapping row must never lose a booking.

Only `pickup_city_id` is joined to `map_cities`; `dropoff_city_id` is carried as a raw id.

### Generating the SQL

The committed SQL is rendered, not hand-written. [silver_obt.ipynb](../Code_Files/silver_obt.ipynb)
holds the join as a `jinja_config` list of dicts — one entry per table, each with `table`,
`select`, `where`, and (for all but the first) `on`:

```python
jinja_config = [
    {"table": "uber.bronze.stg_rides stg_rides", "select": "...", "where": ""},
    {"table": "uber.bronze.map_vehicle_makes map_vehicle_makes",
     "select": "map_vehicle_makes.vehicle_make",
     "where": "",
     "on": "stg_rides.vehicle_make_id = map_vehicle_makes.vehicle_make_id"},
    ...
]
```

A Jinja template walks that list: `loop.first` becomes the `FROM` table and every later entry
becomes a `LEFT JOIN ... ON`, while `loop.last` controls comma placement in the select list and
`AND` placement in an optional `WHERE`. Adding a mapping table is a new config entry rather than
a hand-edited join, which is what keeps a seven-table join maintainable. The rendered output is
committed so the pipeline runs plain SQL — the generous whitespace in the file is template
output, not formatting.

## Gold — dimensions and fact

[model.py](../Code_Files/model.py) follows one shape for every table: a `@dp.view` that projects
and de-duplicates, an empty streaming target, and a CDC flow that maintains it.

```python
@dp.view
def dim_passenger_view():
    df = spark.readStream.table("uber.bronze.silver_obt")
    df = df.select("passenger_id", "passenger_name", "passenger_email",
                   "passenger_phone", "booking_timestamp")
    return df.dropDuplicates(subset=['passenger_id'])

dp.create_streaming_table("dim_passenger")
dp.create_auto_cdc_flow(
  target = "dim_passenger",
  source = "dim_passenger_view",
  keys = ["passenger_id"],
  sequence_by = "booking_timestamp",
  stored_as_scd_type = 1,
)
```

`create_auto_cdc_flow` applies changes by key: `keys` identifies the business entity,
`sequence_by` orders competing versions, and `stored_as_scd_type` chooses overwrite (1) or
history (2).

### SCD Type 1 dimensions

`dim_passenger`, `dim_driver`, `dim_vehicle`, `dim_payment`, and `dim_booking` all use type 1 —
the latest record wins and no history is kept. Each carries `booking_timestamp` and sequences by
it, so when two records share a key the one from the later ride wins. Sequencing by the key itself
would give no ordering at all.

### SCD Type 2 — `dim_location`

`dim_location` keys on `pickup_city_id` and sequences by `city_updated_at`, the `updated_at`
column carried through from `map_cities`. When a city's attributes change, the existing row is
closed and a new version opened, so historical rides continue to roll up to the region that was
in effect at the time. Queries must filter on `__END_AT IS NULL` for current values.

Note that the view de-duplicates on `['pickup_city_id', 'city_updated_at']` — the pair — so each
distinct version survives to be sequenced, rather than collapsing to one row per city.

### `fact`

Projects the measures, the vehicle-type rate columns, and `booking_timestamp`, and applies a
composite key of
`ride_id, pickup_city_id, payment_method_id, driver_id, passenger_id, vehicle_id`, sequenced by
`booking_timestamp`. Unlike the dimension views it does not de-duplicate, relying on the CDC
flow's key handling instead.

## Extending the pipeline

**Adding a mapping table:** upload the file, add it to the `files` list in
[bronze_adls.ipynb](../Code_Files/bronze_adls.ipynb), add a `jinja_config` entry in
[silver_obt.ipynb](../Code_Files/silver_obt.ipynb), re-render, and commit the SQL.

**Adding a dimension:** copy the view/streaming-table/CDC-flow triple in
[model.py](../Code_Files/model.py), pointing at columns that already exist in `silver_obt`.

**Adding a field to the event:** add it in [data.py](../data.py), add it to `rides_schema` in
both [silver.py](../Code_Files/silver.py) and
[silver_obt.ipynb](../Code_Files/silver_obt.ipynb), and add it to the `stg_rides` select in the
`jinja_config`. They must agree or `from_json` will drop it.
