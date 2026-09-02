# Databricks Code Files

The Databricks side of the platform. Add the pipeline sources to a Lakeflow Declarative Pipeline
in the order below; the notebooks are run interactively.

| File | Kind | Layer | Produces |
| --- | --- | --- | --- |
| [ingest.py](ingest.py) | Pipeline | Bronze | `rides_raw` — streaming ingest from Event Hubs |
| [bronze_adls.ipynb](bronze_adls.ipynb) | Notebook | Bronze | `map_*`, `bulk_rides` — batch load from ADLS Gen2 |
| [silver.py](silver.py) | Pipeline | Silver | `stg_rides` — bulk and stream append flows |
| [silver_obt.sql](silver_obt.sql) | Pipeline | Silver | `silver_obt` — enriched one-big-table |
| [silver_obt.ipynb](silver_obt.ipynb) | Notebook | — | Jinja template that generates `silver_obt.sql` |
| [model.py](model.py) | Pipeline | Gold | `dim_*` and `fact` |

Run [bronze_adls.ipynb](bronze_adls.ipynb) once before the first pipeline run to populate the
mapping tables and the historical seed. Its `bulk_rides` cell is guarded so the seed loads only
once — re-running it after the pipeline has consumed the seed would duplicate 2,000 rides.

[silver_obt.sql](silver_obt.sql) is generated, not hand-written. To change the join, edit the
`jinja_config` list in [silver_obt.ipynb](silver_obt.ipynb), re-render, and commit the result.

The pipeline needs a configuration entry named `connection_string` holding the Event Hub
connection string, and a target catalog and schema of `uber` / `bronze`.

Full detail is in [../docs/pipeline.md](../docs/pipeline.md).
