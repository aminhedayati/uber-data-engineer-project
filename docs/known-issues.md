# Known Issues and Rough Edges

Observations from reading the code as it currently stands. Nothing here blocks the local producer
from running; several items do matter before the gold layer works end to end.

## Blocking

### `map_cities` has no `updated_at` column

[silver_obt.sql](../Code_Files/silver_obt.sql) selects `map_cities.updated_at as city_updated_at`,
and `dim_location` in [model.py](../Code_Files/model.py) uses that column as its SCD Type 2
`sequence_by`. The committed [Data/map_cities.json](../Data/map_cities.json) has only `city_id`,
`city`, `state`, and `region`.

As shipped, the OBT will fail to resolve the column. Add an `updated_at` timestamp to each city
record before loading the mapping table.

## Correctness

### Ride status and cancellation reason are drawn independently

In [data.py](../data.py), `cancellation_reason_id` is set from a 10% `is_cancelled` roll while
`ride_status` is drawn separately from `['Completed', 'Completed', 'Cancelled']`. The two never
consult each other, so events can be `Completed` with a real cancellation reason, or `Cancelled`
with reason id `4` (meaning "not cancelled"). Any analysis joining status to cancellation reason
will see contradictions.

### Fares ignore the vehicle type's rate card

`generate_uber_ride_confirmation()` computes every fare from flat constants (`base_fare = 2.50`,
`per_mile_rate = 1.75`, `per_minute_rate = 0.35`) regardless of the `vehicle_type_id` it assigns.
`map_vehicle_types` carries a distinct rate card per type, and `fact` surfaces both, so
`base_fare` will frequently disagree with `base_rate` for the same row.

### Coordinates are unrelated to the city

Latitudes and longitudes are drawn uniformly over the entire globe while `pickup_city_id` names a
US city. Any geospatial use of these columns is meaningless.

### Every ride invents new entities

`passenger_id`, `driver_id`, and `vehicle_id` are fresh UUID4s per event, so no passenger or
driver ever recurs. The dimensions grow at roughly the rate of the fact table and the SCD Type 1
overwrite logic is never actually exercised.

### Send failures are invisible to the user

[api.py](../api.py) assigns `result = send_to_event_hub(ride)` and then ignores it. When the send
fails, `send_to_event_hub` prints to the server console and returns `False`, but `/book` still
renders the confirmation page. The user is told the ride was booked when nothing was published.

## Consistency

### `files_array.json` does not match the actual files

[files_array.json](../files_array.json) at the repository root lists `map_rides` and `map_types`,
neither of which exists in [Data/](../Data): the real mapping file is `map_vehicle_types`, and
there is no `map_rides` file at all. The authoritative list is the inline `files` list in
[bronze_adls.ipynb](../Code_Files/bronze_adls.ipynb), which names all six correctly. Nothing in
the codebase reads the root file.

### `dim_passenger_view` reads an unqualified table name

Every other view in [model.py](../Code_Files/model.py) reads `uber.bronze.silver_obt`;
`dim_passenger_view` reads bare `silver_obt`. It resolves correctly only when the pipeline's
default catalog and schema are set as expected.

### `dim_location_view` is decorated `@dp.table`

All sibling views use `@dp.view`. Declaring it as a table materialises an extra intermediate
dataset that nothing else reads.

### `fact_view` reads its source twice

```python
df = spark.readStream.table("uber.bronze.silver_obt")
df = spark.readStream.table("uber.bronze.silver_obt")
```

The first assignment is immediately overwritten — harmless, but the duplicate line should go.

### SCD Type 1 dimensions sequence by their own key

`sequence_by = "passenger_id"` on a flow keyed by `passenger_id` provides no meaningful ordering
between competing versions of the same row. An event timestamp such as `booking_timestamp` would
order them properly if these attributes ever did change.

### Timestamp typing is mixed

In `rides_schema`, `booking_timestamp` is a `TimestampType` while `pickup_timestamp` and
`dropoff_timestamp` are `StringType`. Only the first is usable for time-based operations without
a cast — which is why it is the watermark column.

### `Los Angelas` is misspelled

[Data/map_cities.json](../Data/map_cities.json) spells city 2 `Los Angelas`;
[data.py](../data.py) spells it `Los Angeles`. Only the id crosses the wire so no join breaks,
but the mapping table is what surfaces in reports.

## Packaging and tooling

### `requirements.txt` is UTF-16 encoded

[requirements.txt](../requirements.txt) was written by a PowerShell redirect and is UTF-16 with a
BOM. Some pip versions fail to parse it. Prefer `uv sync`, or `pip install .` to use the
dependency list in [pyproject.toml](../pyproject.toml).

### `pyproject.toml` metadata is a placeholder

The project is named `event-tutorial` with the default description "Add your description here".

### Dependency lists disagree

[requirements.txt](../requirements.txt) includes packages absent from
[pyproject.toml](../pyproject.toml) (`httpx`, `email-validator`, `fastapi-cli`, `dnspython` and
others). `pyproject.toml` plus [uv.lock](../uv.lock) is the more reliable of the two.

### Unused imports

[connection.py](../connection.py) imports `random`, `uuid`, `datetime`, `timedelta`, `Faker`, and
`logging` without using any of them. [data.py](../data.py) imports the Event Hub SDK, `logging`,
and `load_dotenv` but performs no I/O.

### `Code_Files/readme.md` is empty

The file contains nothing but two blank lines.

## Operational notes

### The bulk load must not be re-run

The guard in [bronze_adls.ipynb](../Code_Files/bronze_adls.ipynb) exists because `stg_rides`
streams from `bulk_rides`. Dropping and reloading that table re-emits all 2,000 seed rides into
silver.

### `failOnDataLoss` is `true`

If events age out of Event Hub retention before the pipeline reads them, ingestion fails rather
than skipping. That is the safe default, but a pipeline left stopped past the retention window
will not restart cleanly without intervention.

### Credentials come from two different places

The producer reads `CONNECTION_STRING` from `.env`; the pipeline reads `connection_string` from
Spark configuration. Both must be maintained, and neither belongs in source control.
