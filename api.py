from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from connection import send_to_event_hub, close_producer
from data import generate_uber_ride_confirmation


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Release the shared Event Hub connection on shutdown.
    close_producer()


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


@app.get("/")
def booking_home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/book")
def book_ride(request: Request):
    ride = generate_uber_ride_confirmation()
    sent = send_to_event_hub(ride)

    # Only confirm the booking if the event actually reached the Event Hub.
    return templates.TemplateResponse(
        "confirmation.html",
        {
            "request": request,
            "sent": sent,
            "confirmation_number": ride["confirmation_number"],
        },
        status_code=200 if sent else 502,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
