# The Producer Web Application

The producer is a small FastAPI application that stands in for a real booking system. Its job is
to put well-formed ride events onto the Event Hub, one per booking.

## Files

| File | Role |
| --- | --- |
| [api.py](../api.py) | FastAPI app and routes |
| [connection.py](../connection.py) | Event Hub producer client |
| [data.py](../data.py) | Ride generator and reference mappings |
| [templates/home.html](../templates/home.html) | Landing page with the booking button |
| [templates/confirmation.html](../templates/confirmation.html) | Post-booking confirmation |

## Endpoints

### `GET /`

Renders [home.html](../templates/home.html) — a styled landing page with a **Book a Ride**
button linking to `/book`. No parameters, no side effects.

### `GET /book`

The whole producer path in three steps:

```python
@app.get("/book")
def book_ride(request: Request):
    ride = generate_uber_ride_confirmation()
    result = send_to_event_hub(ride)
    return templates.TemplateResponse("confirmation.html", {"request": request})
```

1. Generate one synthetic ride confirmation.
2. Publish it to the Event Hub.
3. Render [confirmation.html](../templates/confirmation.html).

The booking is a `GET` so the button can be a plain link. Note that `result` is not inspected —
the confirmation page renders whether or not the send succeeded, and failures surface only as a
message on the server console. See [known-issues.md](known-issues.md).

## Event generation

`generate_uber_ride_confirmation()` in [data.py](../data.py) builds a 43-field record combining
Faker-generated identities with randomised measures. It is pure — no I/O, no network — so it can
be called and inspected on its own:

```python
from data import generate_uber_ride_confirmation
import json
print(json.dumps(generate_uber_ride_confirmation(), indent=2))
```

The module also holds the reference mappings (`CITY_MAPPING`, `VEHICLE_TYPE_MAPPING`,
`PAYMENT_METHOD_MAPPING`, `VEHICLE_MAKE_MAPPING`, `RIDE_STATUS_MAPPING`,
`CANCELLATION_REASON_MAPPING`) together with derived lookup lists and name-to-id dicts. These
mirror the JSON files in [Data/](../Data) that are loaded into the bronze layer, so the ids the
producer emits resolve against the mapping tables downstream. **Changing one side requires
changing the other** — the mappings are duplicated, not shared.

Field-by-field detail is in [data-model.md](data-model.md).

## Publishing

`send_to_event_hub()` in [connection.py](../connection.py) does the following per call:

1. Build an `EventHubProducerClient` from `CONNECTION_STRING` and `EVENT_HUBNAME`.
2. Serialise the ride dict to JSON.
3. Create a batch, add the single event, send the batch.
4. Close the producer.
5. Return `"Successfully sent to Event Hub"`, or `False` after printing the exception.

Credentials are loaded from `.env` via `python-dotenv` at import time.

The client is constructed and torn down on every request, which costs a connection handshake per
booking. That is fine at demo volume; a long-lived module-level producer would be the change to
make for sustained throughput. The `batch_size` parameter is accepted but not used — the function
always sends exactly one event.

## Running it directly

[connection.py](../connection.py) has a `__main__` block that generates a ride, pretty-prints it,
and publishes it — the quickest way to verify Event Hub connectivity without a browser:

```bash
python connection.py
```

## Generating load

To seed a stream without clicking, loop over the send function:

```python
from connection import send_to_event_hub
from data import generate_uber_ride_confirmation
import time

for _ in range(100):
    send_to_event_hub(generate_uber_ride_confirmation())
    time.sleep(0.5)
```

Because each call opens its own producer, high rates are better served by hoisting a single
`EventHubProducerClient` out of the loop and adding many events to one batch.
