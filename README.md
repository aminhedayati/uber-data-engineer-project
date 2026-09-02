# Uber Real-Time Data Engineering Project

An end-to-end streaming data platform that simulates ride-booking events, publishes them to
Azure Event Hubs, and refines them through a medallion (bronze → silver → gold) architecture on
Azure Databricks, ending in a star schema ready for analytics.

![Project Architecture](architecture.png)

## What this project does

A small FastAPI web application acts as the **producer**: every time a user books a ride, it
generates a realistic ride-confirmation record and publishes it to an Azure Event Hub. On the
**consumer** side, a Databricks Lakeflow Declarative Pipeline reads that stream through the
Event Hubs Kafka endpoint, parses it, enriches it against reference ("mapping") tables loaded
from ADLS Gen2, and materialises dimension and fact tables using change-data-capture flows with
both SCD Type 1 and SCD Type 2 history.

```
FastAPI web app  ──▶  Azure Event Hub  ──▶  Databricks (bronze → silver → gold)  ──▶  Star schema
        │                                              ▲
        └── synthetic ride events                      └── ADLS Gen2 (mapping + bulk seed data)
```

## Repository layout

| Path | Purpose |
| --- | --- |
| [api.py](api.py) | FastAPI application exposing the booking pages |
| [connection.py](connection.py) | Event Hub producer client and send logic |
| [data.py](data.py) | Synthetic ride-event generator and reference mappings |
| [templates/](templates/) | Jinja2 HTML templates for the web app |
| [Data/](Data/) | Seed data — mapping tables and a 2,000-row bulk ride file |
| [Code_Files/](Code_Files/) | Databricks pipeline sources and exploration notebooks |
| [Code_Files/ingest.py](Code_Files/ingest.py) | Bronze — streaming ingest from Event Hubs |
| [Code_Files/bronze_adls.ipynb](Code_Files/bronze_adls.ipynb) | Bronze — batch load of mapping and seed files |
| [Code_Files/silver.py](Code_Files/silver.py) | Silver — JSON parsing and staging table flows |
| [Code_Files/silver_obt.sql](Code_Files/silver_obt.sql) | Silver — the enriched one-big-table |
| [Code_Files/silver_obt.ipynb](Code_Files/silver_obt.ipynb) | Jinja template that generates the OBT SQL |
| [Code_Files/model.py](Code_Files/model.py) | Gold — dimensions and fact table |
| [architecture.png](architecture.png), [Uber_Project.svg](Uber_Project.svg) | Architecture diagram |

## Documentation

| Document | Contents |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | End-to-end data flow and the medallion layers |
| [docs/setup.md](docs/setup.md) | Azure resources, configuration, and how to run everything |
| [docs/web-app.md](docs/web-app.md) | The producer application and its endpoints |
| [docs/data-model.md](docs/data-model.md) | Event schema, mapping tables, and the gold star schema |
| [docs/pipeline.md](docs/pipeline.md) | The Databricks pipeline, flow by flow |
| [docs/known-issues.md](docs/known-issues.md) | Remaining limitations and operational caveats |

## Quick start

```bash
uv sync                       # or: pip install -r requirements.txt
cp .env.example .env          # then fill in your Event Hub values
uv run uvicorn api:app --reload
```

Open <http://localhost:8000> and click **Book a Ride** to publish an event.

Full instructions — including the Azure and Databricks side — are in [docs/setup.md](docs/setup.md).

## Technology

Python 3.12 · FastAPI · Jinja2 · Faker · Azure Event Hubs · Azure Data Lake Storage Gen2 ·
Azure Data Factory · Azure Databricks · Spark Structured Streaming · Delta Lake ·
Lakeflow Declarative Pipelines · Unity Catalog
