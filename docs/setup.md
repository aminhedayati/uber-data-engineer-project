# Setup and Operations

This guide covers the local producer application first, then the Azure and Databricks side.

## Prerequisites

- Python 3.12 (pinned in [.python-version](../.python-version))
- An Azure subscription with permission to create Event Hubs, storage, and Databricks resources
- Optionally [uv](https://docs.astral.sh/uv/) for dependency management (a
  [uv.lock](../uv.lock) is committed)

## 1. Local producer application

### Install dependencies

With uv (recommended — installs the exact locked versions):

```bash
uv sync
```

With pip:

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

[requirements.txt](../requirements.txt) is a flat freeze of the whole environment;
[pyproject.toml](../pyproject.toml) plus [uv.lock](../uv.lock) is the authoritative dependency
set.

### Configure

Copy the example file and fill in the values from your Event Hub namespace:

```bash
cp .env.example .env
```

| Variable | Description |
| --- | --- |
| `CONNECTION_STRING` | Event Hub **namespace** connection string, including `SharedAccessKey` |
| `EVENT_HUBNAME` | Name of the event hub (the topic), e.g. `ubertopic` |

The connection string is read at import time by [connection.py](../connection.py) via
`python-dotenv`. `.env` is git-ignored — never commit real credentials.

### Run

```bash
uv run uvicorn api:app --reload
```

or directly, which serves on `0.0.0.0:8000`:

```bash
python api.py
```

Then open <http://localhost:8000> and click **Book a Ride**. Each click publishes one event.

### Send an event without the web app

[connection.py](../connection.py) has a `__main__` block that generates a ride, prints it, and
publishes it — useful for verifying connectivity:

```bash
python connection.py
```

## 2. Azure resources

### Event Hubs

1. Create an Event Hubs **namespace** (the pipeline code assumes `uberevents`).
2. Create an **event hub** inside it (the code assumes `ubertopic`).
3. Create a shared access policy with **Send** rights for the producer and **Listen** rights for
   Databricks, and copy its connection string.

The namespace must be Standard tier or above — the Kafka endpoint used by Databricks is not
available on Basic.

If you use different names, update `EH_NAMESPACE` and `EH_NAME` in
[Code_Files/ingest.py](../Code_Files/ingest.py) to match.

### ADLS Gen2

Create a storage account with hierarchical namespace enabled, and a `raw` container with an
`ingestion/` folder. Upload the contents of [Data/](../Data):

- `map_cities.json`
- `map_cancellation_reasons.json`
- `map_payment_methods.json`
- `map_ride_statuses.json`
- `map_vehicle_makes.json`
- `map_vehicle_types.json`
- `bulk_rides.json`

### Azure Data Factory

ADF handles the batch movement into ADLS Gen2 and triggers the Databricks initial load. The
streaming path does not depend on it.

## 3. Databricks

### Unity Catalog

The code writes to the `uber` catalog and `bronze` schema — tables are addressed as
`uber.bronze.<table>`. Create these before the first run:

```sql
CREATE CATALOG IF NOT EXISTS uber;
CREATE SCHEMA IF NOT EXISTS uber.bronze;
```

### Load the reference and seed data

Run [Code_Files/bronze_adls.ipynb](../Code_Files/bronze_adls.ipynb). It reads each mapping file
from ADLS Gen2 and writes it to `uber.bronze.<name>` as Delta. Replace the `<your-token>`
placeholder in the notebook URLs with a valid SAS token, or switch the notebook to a mounted
path or credential passthrough.

The mapping load uses `mode("overwrite")` and is safe to re-run. The `bulk_rides` cell is guarded
by a `spark.catalog.tableExists` check so the historical seed is loaded only once — re-running it
after the pipeline has consumed the seed would otherwise duplicate 2,000 rides.

### Create the pipeline

Create a Lakeflow Declarative Pipeline with these source files, in this order:

1. [Code_Files/ingest.py](../Code_Files/ingest.py) — bronze streaming ingest
2. [Code_Files/silver.py](../Code_Files/silver.py) — staging table and append flows
3. [Code_Files/silver_obt.sql](../Code_Files/silver_obt.sql) — enriched one-big-table
4. [Code_Files/model.py](../Code_Files/model.py) — gold dimensions and fact

Set the pipeline's target catalog to `uber` and target schema to `bronze`.

### Pipeline configuration

`ingest.py` reads the Event Hub credential from Spark configuration, not from the environment:

```python
EH_CONN_STR = spark.conf.get("connection_string")
```

Add a pipeline configuration entry with key `connection_string` and the Event Hub connection
string as its value. Prefer a Databricks secret reference over a literal value.

### Run

Start the pipeline in **continuous** mode for live streaming, or **triggered** mode to process
whatever has accumulated and stop. On the first run `startingOffsets` is `earliest`, so the
pipeline reads the full retained history of the hub.

Let the historical seed finish flowing through to `silver_obt` **before** starting the live
producer. `silver_obt` watermarks on `booking_timestamp`, and the seed spans about 30 days; if
live events advance the watermark while the seed is still being consumed, older seed rows can
fall behind it and be dropped from the join. See [known-issues.md](known-issues.md).

## Verification

After the pipeline settles, check each layer:

```sql
SELECT count(*) FROM uber.bronze.rides_raw;    -- raw events arriving
SELECT count(*) FROM uber.bronze.stg_rides;    -- bulk + stream combined
SELECT count(*) FROM uber.bronze.silver_obt;   -- enriched
SELECT count(*) FROM uber.bronze.fact;         -- modelled

-- current-version join against the SCD2 location dimension
SELECT fact.ride_id, fact.base_fare, dim.region
FROM uber.bronze.fact AS fact
LEFT JOIN uber.bronze.dim_location AS dim
  ON fact.pickup_city_id = dim.pickup_city_id
 AND dim.`__END_AT` IS NULL;
```

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Browser shows **Booking Failed** with HTTP 502 | The event did not reach the Event Hub. Check the server log — a missing `CONNECTION_STRING` or `EVENT_HUBNAME` is reported explicitly |
| Kafka connector times out in Databricks | Namespace is Basic tier, port 9093 is blocked, or `connection_string` is not set in the pipeline config |
| `rides_raw` fills but `stg_rides` stays empty | Event JSON does not match `rides_schema`; `from_json` yields nulls on mismatch rather than failing |
| Seed rides missing from `silver_obt` | The watermark advanced past them; load the seed before starting the live producer |
| Pipeline restarts reprocess everything | Checkpoint state was reset; a full refresh re-reads from `earliest` |
