# Known Issues and Limitations

What remains after the current round of fixes. Everything here is either a deliberate simulation
trade-off or a caveat to be aware of when operating the platform — none of it blocks a run.

## Simulation fidelity

### Street addresses do not match the attributed city

Coordinates are generated within roughly 15 km of the centre of the city named by
`pickup_city_id` / `dropoff_city_id`, but `pickup_address` and `dropoff_address` are still
free-standing Faker addresses with unrelated street names, cities, and ZIP codes. The coordinates
are trustworthy; the address strings are decorative.

### The event carries outcome fields at booking time

`booking_timestamp` is the moment the event fires, which is what makes the silver watermark
meaningful. The record still carries `tip_amount`, `rating`, and a `dropoff_timestamp` that lies
in the future — values a real booking confirmation would not yet know. Treat them as the
simulated eventual outcome of the ride rather than as facts known at booking.

Cancelled rides are internally consistent (no tip, no rating) but still carry the fare and the
scheduled pickup and dropoff times.

### `vehicle_model` is a random word

`fake.word().capitalize()` produces models like "Provide" or "Consider". The value is stable per
vehicle now that vehicles come from a fixed pool, but it is not a real model name and does not
correspond to `vehicle_make`.

### The historical seed still invents one entity per ride

The live producer draws from fixed pools of 500 passengers, 150 drivers, and 150 vehicles, so
entities recur. [Data/bulk_rides.json](../Data/bulk_rides.json) predates that change and contains
2,000 rides with 2,000 distinct passengers, drivers, and vehicles. The dimensions will therefore
carry a long tail of single-ride entities from the historical load. Regenerating the seed from the
current generator would resolve it.

### `dropoff_city_id` has no dimension

The OBT joins `map_cities` on `pickup_city_id` only, so `dim_location` describes pickup cities.
`dropoff_city_id` is carried through as a bare id with no city, state, or region attached.

## Streaming behaviour

### The seed's timestamps interact with the watermark

`silver_obt` watermarks on `booking_timestamp` with a three-minute delay, and the bulk seed spans
roughly 30 days. Within the first micro-batch the watermark has not yet advanced, so the seed
passes through; but if live events advance the watermark before the seed is fully consumed, older
seed rows can fall behind it and be dropped from the join.

Load the seed and let it settle **before** starting the live producer. Regenerating the seed with
a narrower time range, or widening the watermark delay for the initial load, are the two ways to
remove the hazard entirely.

### De-duplication state is unbounded

The gold views call `dropDuplicates` on streaming DataFrames without a watermark, so Spark keeps
the set of seen keys indefinitely. State grows with the number of distinct entities. The fixed
producer pools bound this for live data; the historical seed still contributes 2,000 keys per
entity type.

### `failOnDataLoss` is `true`

If events age out of Event Hub retention before the pipeline reads them, ingestion fails rather
than silently skipping. That is the safe default, but a pipeline left stopped past the retention
window will not restart cleanly without intervention.

## Maintenance

### Reference data is defined in two places

The mappings in [data.py](../data.py) (`CITY_MAPPING`, `VEHICLE_TYPE_MAPPING`, and the rest)
mirror the JSON files in [Data/](../Data) that are loaded into the bronze layer. The producer
needs them to emit valid foreign keys; the pipeline needs the JSON to resolve those keys into
attributes. **Changing one side requires changing the other.**

They are not byte-identical by design: [Data/map_cities.json](../Data/map_cities.json) carries an
`updated_at` column that drives SCD Type 2 history on `dim_location`, and `data.py` carries
`CITY_COORDINATES`, which the mapping table does not need. The analytic columns — ids, names,
states, regions — must stay in step.

### `updated_at` is uniform in the seed

Every city in [Data/map_cities.json](../Data/map_cities.json) has the same `updated_at` of
`2024-01-01T00:00:00`, so `dim_location` builds exactly one version per city. The SCD Type 2
machinery is wired correctly but will not produce a second version until a city's row is changed
and its `updated_at` advanced.

### Credentials come from two different places

The producer reads `CONNECTION_STRING` from `.env`; the pipeline reads `connection_string` from
Spark configuration. Both must be maintained, and neither belongs in source control.

### The bulk load must not be re-run

The guard in [bronze_adls.ipynb](../Code_Files/bronze_adls.ipynb) exists because `stg_rides`
streams from `bulk_rides`. Dropping and reloading that table re-emits all 2,000 seed rides into
silver.

### Notebook outputs are committed

[silver_obt.ipynb](../Code_Files/silver_obt.ipynb) carries its execution output, which is the bulk
of the file's size and makes its diffs noisy. Clearing outputs before committing would keep the
history readable.
