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

`ride_id`, `pickup_location_id`, and `dropoff_location_id` are fresh UUIDs per event.
`passenger_id`, `driver_id`, and `vehicle_id` are drawn from fixed pools (500 passengers, 150
drivers, 150 vehicles), so entities recur across rides and the dimensions converge on a stable
set rather than growing in step with the fact table.

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
| `passenger_name`, `passenger_email`, `passenger_phone` | string | Synthetic, stable per `passenger_id` |
| `driver_name`, `driver_phone`, `driver_license` | string | Synthetic, stable per `driver_id` |
| `driver_rating` | double | 4.00–5.00, stable per driver |
| `vehicle_model`, `vehicle_color`, `license_plate` | string | Stable per `vehicle_id`; colour from a fixed six-value list |
| `pickup_address`, `dropoff_address` | string | Newlines flattened to `, `; not aligned to the city |
| `pickup_latitude`, `pickup_longitude` | double | Within ~15 km of the pickup city centre |
| `dropoff_latitude`, `dropoff_longitude` | double | Within ~15 km of the dropoff city centre |

### Measures and timestamps

| Field | Type | Notes |
| --- | --- | --- |
| `distance_miles` | double | 0.5–50 |
| `duration_minutes` | long | 5–120 |
| `booking_timestamp` | timestamp | The moment the event fires; the watermark column |
| `pickup_timestamp` | timestamp | Booking + 1–10 minutes |
| `dropoff_timestamp` | timestamp | Pickup + duration |
| `base_fare` | double | `base_rate` of the ride's vehicle type |
| `distance_fare` | double | `distance_miles × per_mile` of the vehicle type |
| `time_fare` | double | `duration_minutes × per_minute` of the vehicle type |
| `surge_multiplier` | double | 1.0–2.5 |
| `subtotal` | double | `(base + distance + time) × surge` |
| `tip_amount` | double | Weighted toward zero; always 0 for a cancelled ride |
| `total_fare` | double | `subtotal + tip` |
| `rating` | double | 1–5 or null; always null for a cancelled ride |

Fares are priced from the rate card of the ride's own `vehicle_type_id`, so `base_fare` always
equals that type's `base_rate` and the distance and time components use its `per_mile` and
`per_minute`. All three timestamps are typed as timestamps in `rides_schema`, and the timeline is
ordered `booking ≤ pickup ≤ dropoff`.

`ride_status_id` and `cancellation_reason_id` are decided together: a Completed ride always
carries reason id `4` ("not cancelled"), and a Cancelled ride always carries one of ids 1–3.

## Mapping tables

Reference data lives in [Data/](../Data) and is loaded into `uber.bronze.map_*`.

### `map_cities` (10 rows)

`city_id`, `city`, `state`, `region`, `updated_at` — the ten largest US cities, grouped into
Northeast, West, Midwest, South, and Southwest.

The silver OBT selects `updated_at` as `city_updated_at`, which drives SCD Type 2 history on
`dim_location`. Every seeded city shares an `updated_at` of `2024-01-01T00:00:00`, so each city
starts with exactly one version; advancing a city's `updated_at` after changing its attributes is
what opens a new one.

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
| `dim_passenger` | `passenger_id` | 1 | `booking_timestamp` | name, email, phone |
| `dim_driver` | `driver_id` | 1 | `booking_timestamp` | name, rating, phone, licence |
| `dim_vehicle` | `vehicle_id` | 1 | `booking_timestamp` | make, type, model, colour, plate |
| `dim_payment` | `payment_method_id` | 1 | `booking_timestamp` | method, `is_card`, `requires_auth` |
| `dim_booking` | `ride_id` | 1 | `booking_timestamp` | confirmation number, status, addresses, coordinates, booking and dropoff timestamps |
| `dim_location` | `pickup_city_id` | 2 | `city_updated_at` | city, region, state |
| `fact` | composite (see below) | 1 | `booking_timestamp` | measures and rates |

Every SCD Type 1 dimension carries `booking_timestamp` so competing versions of a row are ordered
by when the ride happened.

### `fact`

Grain is one row per ride. The CDC key is the composite
`ride_id, pickup_city_id, payment_method_id, driver_id, passenger_id, vehicle_id`.

Measures: `distance_miles`, `duration_minutes`, `base_fare`, `distance_fare`, `time_fare`,
`surge_multiplier`, `total_fare`, `tip_amount`, `rating`, plus the rate columns `base_rate`,
`per_mile`, and `per_minute` carried through from `map_vehicle_types` and `booking_timestamp`.

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
