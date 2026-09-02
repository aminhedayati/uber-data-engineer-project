# Data Model

## The ride event

`generate_uber_ride_confirmation()` in [data.py](../data.py) produces one denormalised booking
confirmation per call. This is the contract between the producer and the pipeline — the same
43 fields appear in `bulk_rides.json`, in `rides_schema` in [silver.py](../Code_Files/silver.py),
and in `silver_obt`.

### Identifiers

| Field | Type | Notes |
| --- | --- | --- |
| `ride_id` | string | UUID4, grain of the fact table |
| `confirmation_number` | string | Formatted `??#-####-??##` |
| `passenger_id` | string | UUID4 |
| `driver_id` | string | UUID4 |
| `vehicle_id` | string | UUID4 |
| `pickup_location_id` | string | UUID4 |
| `dropoff_location_id` | string | UUID4 |

Because every id is a fresh UUID per event, each ride generates a new passenger, driver, and
vehicle. The dimensions therefore grow roughly in step with the fact table rather than
converging on a stable set of entities.

### Foreign keys into the mapping tables

| Field | Type | Resolves against |
| --- | --- | --- |
| `vehicle_type_id` | long | `map_vehicle_types` |
| `vehicle_make_id` | long | `map_vehicle_makes` |
| `payment_method_id` | long | `map_payment_methods` |
| `ride_status_id` | long | `map_ride_statuses` |
| `pickup_city_id` | long | `map_cities` |
| `dropoff_city_id` | long | `map_cities` (not joined in the OBT) |
| `cancellation_reason_id` | long | `map_cancellation_reasons` |

### Descriptive attributes

| Field | Type | Notes |
| --- | --- | --- |
| `passenger_name`, `passenger_email`, `passenger_phone` | string | Synthetic |
| `driver_name`, `driver_phone`, `driver_license` | string | Synthetic |
| `driver_rating` | double | 4.00–5.00 |
| `vehicle_model`, `vehicle_color`, `license_plate` | string | Colour from a fixed six-value list |
| `pickup_address`, `dropoff_address` | string | Newlines flattened to `, ` |
| `pickup_latitude`, `pickup_longitude` | double | Uniform over the whole globe, unrelated to the city |
| `dropoff_latitude`, `dropoff_longitude` | double | Same |

### Measures and timestamps

| Field | Type | Notes |
| --- | --- | --- |
| `distance_miles` | double | 0.5–50 |
| `duration_minutes` | long | 5–120 |
| `booking_timestamp` | timestamp | 1–10 minutes before pickup; the watermark column |
| `pickup_timestamp` | string | Up to 30 days in the past |
| `dropoff_timestamp` | string | Pickup + duration |
| `base_fare` | double | Flat 2.50 |
| `distance_fare` | double | `distance_miles × 1.75` |
| `time_fare` | double | `duration_minutes × 0.35` |
| `surge_multiplier` | double | 1.0–2.5 |
| `subtotal` | double | `(base + distance + time) × surge` |
| `tip_amount` | double | Weighted toward zero |
| `total_fare` | double | `subtotal + tip` |
| `rating` | double | 1–5, or null |

Note that fares are computed from the flat rates above rather than from the per-type rates in
`map_vehicle_types`, so `base_fare` will not always agree with the `base_rate` of the ride's
`vehicle_type_id`. Only `booking_timestamp` is typed as a timestamp in `rides_schema`; the pickup
and dropoff timestamps stay strings.

## Mapping tables

Reference data lives in [Data/](../Data) and is loaded into `uber.bronze.map_*`.

### `map_cities` (10 rows)

`city_id`, `city`, `state`, `region` — the ten largest US cities, grouped into Northeast, West,
Midwest, South, and Southwest.

The silver OBT also selects `updated_at` from this table as `city_updated_at`, which drives SCD
Type 2 history on `dim_location`. The committed seed file does not yet carry that column — see
[known-issues.md](known-issues.md).

### `map_vehicle_types` (5 rows)

`vehicle_type_id`, `vehicle_type`, `description`, `base_rate`, `per_mile`, `per_minute`.

| Type | Description | Base | Per mile | Per minute |
| --- | --- | --- | --- | --- |
| UberX | Standard | 2.50 | 1.75 | 0.35 |
| UberXL | Extra Large | 3.50 | 2.25 | 0.45 |
| UberPOOL | Shared Ride | 2.00 | 1.50 | 0.30 |
| Uber Comfort | Comfortable | 3.00 | 2.00 | 0.40 |
| Uber Black | Premium | 5.00 | 3.50 | 0.60 |

### `map_payment_methods` (4 rows)

`payment_method_id`, `payment_method`, `is_card`, `requires_auth` — Credit Card, Debit Card,
Digital Wallet, Cash. The two card methods require authorisation.

### `map_vehicle_makes` (7 rows)

`vehicle_make_id`, `vehicle_make` — Toyota, Honda, Ford, Chevrolet, Nissan, BMW, Mercedes.

### `map_ride_statuses` (2 rows)

`ride_status_id`, `ride_status`, `is_completed` — Completed and Cancelled.

### `map_cancellation_reasons` (4 rows)

`cancellation_reason_id`, `cancellation_reason` — Driver cancelled, Passenger cancelled, No show,
and id `4` with a null reason representing a ride that was not cancelled.

### `bulk_rides.json`

2,000 pre-generated ride records with the same 43 fields, used as the historical seed so the
platform has depth before any live events arrive.

## Gold star schema

Every gold table is a projection of `silver_obt`, maintained by `dp.create_auto_cdc_flow`.

```
                    ┌──────────────────┐
                    │  dim_passenger   │ SCD1
                    └────────┬─────────┘
┌───────────────┐            │            ┌──────────────┐
│  dim_driver   │ SCD1 ──────┤       ─────│ dim_vehicle  │ SCD1
└───────────────┘            │            └──────────────┘
                    ┌────────▼─────────┐
                    │      fact        │
                    └────────┬─────────┘
┌───────────────┐            │            ┌──────────────┐
│  dim_payment  │ SCD1 ──────┤       ─────│ dim_booking  │ SCD1
└───────────────┘            │            └──────────────┘
                    ┌────────▼─────────┐
                    │   dim_location   │ SCD2
                    └──────────────────┘
```

| Table | Business key | SCD | Sequenced by | Columns |
| --- | --- | --- | --- | --- |
| `dim_passenger` | `passenger_id` | 1 | `passenger_id` | name, email, phone |
| `dim_driver` | `driver_id` | 1 | `driver_id` | name, rating, phone, licence |
| `dim_vehicle` | `vehicle_id` | 1 | `vehicle_id` | make, type, model, colour, plate |
| `dim_payment` | `payment_method_id` | 1 | `payment_method_id` | method, `is_card`, `requires_auth` |
| `dim_booking` | `ride_id` | 1 | `ride_id` | confirmation number, status, addresses, coordinates, booking and dropoff timestamps |
| `dim_location` | `pickup_city_id` | 2 | `city_updated_at` | city, region, state |
| `fact` | composite (see below) | 1 | `ride_id` | measures and rates |

### `fact`

Grain is one row per ride. The CDC key is the composite
`ride_id, pickup_city_id, payment_method_id, driver_id, passenger_id, vehicle_id`.

Measures: `distance_miles`, `duration_minutes`, `base_fare`, `distance_fare`, `time_fare`,
`surge_multiplier`, `total_fare`, `tip_amount`, `rating`, plus the rate columns `base_rate`,
`per_mile`, and `per_minute` carried through from `map_vehicle_types`.

### Querying the SCD2 dimension

`dim_location` is versioned, so a join must either pick the current version or match on the
validity window. For current values:

```sql
SELECT f.ride_id, f.total_fare, d.region
FROM uber.bronze.fact f
LEFT JOIN uber.bronze.dim_location d
  ON f.pickup_city_id = d.pickup_city_id
 AND d.`__END_AT` IS NULL;
```

`__START_AT` and `__END_AT` are maintained by the CDC flow; the open (current) row has a null
`__END_AT`.
