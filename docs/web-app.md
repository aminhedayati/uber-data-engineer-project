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
    sent = send_to_event_hub(ride)
    return templates.TemplateResponse(
        "confirmation.html",
        {"request": request, "sent": sent,
         "confirmation_number": ride["confirmation_number"]},
        status_code=200 if sent else 502,
    )
```

1. Generate one synthetic ride confirmation.
2. Publish it to the Event Hub.
3. Render [confirmation.html](../templates/confirmation.html), reflecting the outcome.

The booking is a `GET` so the button can be a plain link. The publish result decides what the user
sees: on success the page confirms the booking and shows the confirmation number; on failure it
says the booking could not be recorded and the response carries HTTP 502. The page never claims a
ride was booked when the event did not reach the Event Hub.

## Event generation

`generate_uber_ride_confirmation()` in [data.py](../data.py) builds a 43-field record combining
Faker-generated identities with randomised measures. Passengers, drivers, and vehicles are drawn
from fixed pools built once at import, so the same entities recur across rides. It is pure — no
I/O, no network — so it can be called and inspected on its own:

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

1. Fetch the shared producer via `get_producer()`, creating it on first use.
2. Serialise the ride dict to JSON.
3. Create a batch, add the single event, send the batch.
4. Return `True`, or `False` after logging the exception.

Credentials are loaded from `.env` via `python-dotenv` at import time. If either variable is
missing, `get_producer()` raises a `RuntimeError` naming the fix; `send_to_event_hub()` catches
it, logs it, and returns `False` rather than propagating a 500 to the browser.

The producer holds an open connection to the Event Hub, so it is created once and reused across
requests instead of being rebuilt per booking. On a send failure the client is discarded so the
next attempt starts from a fresh connection. `close_producer()` releases it, and the FastAPI
lifespan handler calls it on shutdown.

## Running it directly

[connection.py](../connection.py) has a `__main__` block that generates a ride, pretty-prints it,
publishes it, and closes the producer — the quickest way to verify Event Hub connectivity without
a browser:

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

The producer is shared across calls, so the loop above reuses one connection. For bulk loads,
adding many events to a single batch before sending is more efficient still.
