import json
import logging
import os

from azure.eventhub import EventHubProducerClient, EventData
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# Pulling Data Generator Function
from data import generate_uber_ride_confirmation

logger = logging.getLogger(__name__)

CONNECTION_STRING = os.getenv("CONNECTION_STRING")
EVENT_HUBNAME = os.getenv("EVENT_HUBNAME")

# The producer opens a connection to the Event Hub, so it is created once and
# reused instead of being rebuilt on every send.
_producer = None


def get_producer():
    """Return the shared Event Hub producer, creating it on first use."""
    global _producer

    if not CONNECTION_STRING or not EVENT_HUBNAME:
        raise RuntimeError(
            "CONNECTION_STRING and EVENT_HUBNAME must be set. "
            "Copy .env.example to .env and fill in your Event Hub values."
        )

    if _producer is None:
        _producer = EventHubProducerClient.from_connection_string(
            CONNECTION_STRING,
            eventhub_name=EVENT_HUBNAME
        )

    return _producer


def close_producer():
    """Close the shared producer, if one was opened."""
    global _producer

    if _producer is not None:
        _producer.close()
        _producer = None


def send_to_event_hub(ride_data):
    """Publish one ride record to the Event Hub.

    Returns True when the batch was sent, False otherwise.
    """
    try:
        producer = get_producer()

        event_batch = producer.create_batch()
        event_batch.add(EventData(json.dumps(ride_data)))
        producer.send_batch(event_batch)

        return True

    except Exception as e:
        logger.error("Error sending data to Event Hub: %s", e)
        # Drop the client so the next send starts from a fresh connection.
        try:
            close_producer()
        except Exception:
            _reset_producer()
        return False


def _reset_producer():
    global _producer
    _producer = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=" * 80)
    print("SINGLE RIDE CONFIRMATION")
    print("=" * 80)
    ride = generate_uber_ride_confirmation()
    print(json.dumps(ride, indent=2))

    print("\n" + "=" * 80)
    print("SENDING SINGLE RIDE TO EVENT HUB")
    result = send_to_event_hub(ride)
    print(f"Single ride sent to Event Hub: {result}")

    close_producer()
