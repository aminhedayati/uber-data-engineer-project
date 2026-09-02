import random
import uuid
from datetime import datetime, timedelta

from faker import Faker

fake = Faker()


VEHICLE_TYPE_MAPPING = [
    {'vehicle_type_id': 1, 'vehicle_type': 'UberX', 'description': 'Standard', 'base_rate': 2.50, 'per_mile': 1.75, 'per_minute': 0.35},
    {'vehicle_type_id': 2, 'vehicle_type': 'UberXL', 'description': 'Extra Large', 'base_rate': 3.50, 'per_mile': 2.25, 'per_minute': 0.45},
    {'vehicle_type_id': 3, 'vehicle_type': 'UberPOOL', 'description': 'Shared Ride', 'base_rate': 2.00, 'per_mile': 1.50, 'per_minute': 0.30},
    {'vehicle_type_id': 4, 'vehicle_type': 'Uber Comfort', 'description': 'Comfortable', 'base_rate': 3.00, 'per_mile': 2.00, 'per_minute': 0.40},
    {'vehicle_type_id': 5, 'vehicle_type': 'Uber Black', 'description': 'Premium', 'base_rate': 5.00, 'per_mile': 3.50, 'per_minute': 0.60}
]

PAYMENT_METHOD_MAPPING = [
    {'payment_method_id': 1, 'payment_method': 'Credit Card', 'is_card': True, 'requires_auth': True},
    {'payment_method_id': 2, 'payment_method': 'Debit Card', 'is_card': True, 'requires_auth': True},
    {'payment_method_id': 3, 'payment_method': 'Digital Wallet', 'is_card': False, 'requires_auth': False},
    {'payment_method_id': 4, 'payment_method': 'Cash', 'is_card': False, 'requires_auth': False}
]

RIDE_STATUS_MAPPING = [
    {'ride_status_id': 1, 'ride_status': 'Completed', 'is_completed': True},
    {'ride_status_id': 2, 'ride_status': 'Cancelled', 'is_completed': False}
]

VEHICLE_MAKE_MAPPING = [
    {'vehicle_make_id': 1, 'vehicle_make': 'Toyota'},
    {'vehicle_make_id': 2, 'vehicle_make': 'Honda'},
    {'vehicle_make_id': 3, 'vehicle_make': 'Ford'},
    {'vehicle_make_id': 4, 'vehicle_make': 'Chevrolet'},
    {'vehicle_make_id': 5, 'vehicle_make': 'Nissan'},
    {'vehicle_make_id': 6, 'vehicle_make': 'BMW'},
    {'vehicle_make_id': 7, 'vehicle_make': 'Mercedes'}
]

VEHICLE_MAKES_LIST = [m['vehicle_make'] for m in VEHICLE_MAKE_MAPPING]
VEHICLE_MAKE_ID_MAP = {m['vehicle_make']: m['vehicle_make_id'] for m in VEHICLE_MAKE_MAPPING}

VEHICLE_TYPES_LIST = [t['vehicle_type'] for t in VEHICLE_TYPE_MAPPING]
VEHICLE_TYPE_ID_MAP = {t['vehicle_type']: t['vehicle_type_id'] for t in VEHICLE_TYPE_MAPPING}
# Rate card keyed by id, so fares can be priced from the ride's actual vehicle type.
VEHICLE_TYPE_BY_ID = {t['vehicle_type_id']: t for t in VEHICLE_TYPE_MAPPING}

PAYMENT_METHODS_LIST = [p['payment_method'] for p in PAYMENT_METHOD_MAPPING]
PAYMENT_METHOD_ID_MAP = {p['payment_method']: p['payment_method_id'] for p in PAYMENT_METHOD_MAPPING}

RIDE_STATUSES_LIST = [s['ride_status'] for s in RIDE_STATUS_MAPPING]
RIDE_STATUS_ID_MAP = {s['ride_status']: s['ride_status_id'] for s in RIDE_STATUS_MAPPING}

CITY_MAPPING = [
    {'city_id': 1, 'city': 'New York', 'state': 'NY', 'region': 'Northeast'},
    {'city_id': 2, 'city': 'Los Angeles', 'state': 'CA', 'region': 'West'},
    {'city_id': 3, 'city': 'Chicago', 'state': 'IL', 'region': 'Midwest'},
    {'city_id': 4, 'city': 'Houston', 'state': 'TX', 'region': 'South'},
    {'city_id': 5, 'city': 'Phoenix', 'state': 'AZ', 'region': 'Southwest'},
    {'city_id': 6, 'city': 'Philadelphia', 'state': 'PA', 'region': 'Northeast'},
    {'city_id': 7, 'city': 'San Antonio', 'state': 'TX', 'region': 'South'},
    {'city_id': 8, 'city': 'San Diego', 'state': 'CA', 'region': 'West'},
    {'city_id': 9, 'city': 'Dallas', 'state': 'TX', 'region': 'South'},
    {'city_id': 10, 'city': 'San Jose', 'state': 'CA', 'region': 'West'}
]

CITY_LIST = [c['city'] for c in CITY_MAPPING]
CITY_ID_MAP = {c['city']: c['city_id'] for c in CITY_MAPPING}

# Approximate city centres, used to keep generated coordinates inside the city
# the ride is attributed to.
CITY_COORDINATES = {
    1: (40.7128, -74.0060),
    2: (34.0522, -118.2437),
    3: (41.8781, -87.6298),
    4: (29.7604, -95.3698),
    5: (33.4484, -112.0740),
    6: (39.9526, -75.1652),
    7: (29.4241, -98.4936),
    8: (32.7157, -117.1611),
    9: (32.7767, -96.7970),
    10: (37.3382, -121.8863)
}

# Spread of generated points around a city centre, in degrees (~15 km).
CITY_SPREAD_DEGREES = 0.15

CANCELLATION_REASON_MAPPING = [
    {'cancellation_reason_id': 1, 'cancellation_reason': 'Driver cancelled'},
    {'cancellation_reason_id': 2, 'cancellation_reason': 'Passenger cancelled'},
    {'cancellation_reason_id': 3, 'cancellation_reason': 'No show'},
    {'cancellation_reason_id': 4, 'cancellation_reason': None}  # Completed rides
]

CANCELLATION_REASON_ID_MAP = {c['cancellation_reason']: c['cancellation_reason_id'] for c in CANCELLATION_REASON_MAPPING}

# The id that means "this ride was not cancelled".
NOT_CANCELLED_REASON_ID = 4
CANCELLATION_REASONS_LIST = [
    c['cancellation_reason'] for c in CANCELLATION_REASON_MAPPING
    if c['cancellation_reason'] is not None
]

VEHICLE_COLORS = ['Black', 'White', 'Gray', 'Silver', 'Blue', 'Red']

# Share of rides that end up cancelled.
CANCELLATION_RATE = 0.1

# Passengers, drivers and vehicles are drawn from fixed pools so the same
# entities recur across rides. Without this every event would invent a new
# passenger and driver, and the dimension tables would grow as fast as the
# fact table.
PASSENGER_POOL_SIZE = 500
DRIVER_POOL_SIZE = 150
VEHICLE_POOL_SIZE = 150


def _build_passenger_pool(size):
    return [
        {
            'passenger_id': str(uuid.uuid4()),
            'passenger_name': fake.name(),
            'passenger_email': fake.email(),
            'passenger_phone': fake.phone_number()
        }
        for _ in range(size)
    ]


def _build_driver_pool(size):
    return [
        {
            'driver_id': str(uuid.uuid4()),
            'driver_name': fake.name(),
            'driver_rating': round(random.uniform(4.0, 5.0), 2),
            'driver_phone': fake.phone_number(),
            'driver_license': fake.bothify('??-???-#######')
        }
        for _ in range(size)
    ]


def _build_vehicle_pool(size):
    pool = []
    for _ in range(size):
        vehicle_make = random.choice(VEHICLE_MAKES_LIST)
        vehicle_type = random.choice(VEHICLE_TYPES_LIST)
        pool.append({
            'vehicle_id': str(uuid.uuid4()),
            'vehicle_make_id': VEHICLE_MAKE_ID_MAP[vehicle_make],
            'vehicle_type_id': VEHICLE_TYPE_ID_MAP[vehicle_type],
            'vehicle_model': fake.word().capitalize(),
            'vehicle_color': random.choice(VEHICLE_COLORS),
            'license_plate': fake.bothify('???-####')
        })
    return pool


PASSENGER_POOL = _build_passenger_pool(PASSENGER_POOL_SIZE)
DRIVER_POOL = _build_driver_pool(DRIVER_POOL_SIZE)
VEHICLE_POOL = _build_vehicle_pool(VEHICLE_POOL_SIZE)


def _coordinates_near(city_id):
    """Return a random point within CITY_SPREAD_DEGREES of the city centre."""
    latitude, longitude = CITY_COORDINATES[city_id]
    return (
        round(latitude + random.uniform(-CITY_SPREAD_DEGREES, CITY_SPREAD_DEGREES), 6),
        round(longitude + random.uniform(-CITY_SPREAD_DEGREES, CITY_SPREAD_DEGREES), 6)
    )


def generate_uber_ride_confirmation():

    # The event fires when the ride is booked, so booking_timestamp is "now".
    # The silver layer watermarks on this column, so backdating it here would
    # put live events behind the watermark and drop them from the join.
    booking_time = datetime.now()
    pickup_time = booking_time + timedelta(minutes=random.randint(1, 10))
    duration_minutes = random.randint(5, 120)
    dropoff_time = pickup_time + timedelta(minutes=duration_minutes)

    # Distance in miles
    distance = round(random.uniform(0.5, 50), 2)

    # Draw the participants from the fixed pools
    passenger = random.choice(PASSENGER_POOL)
    driver = random.choice(DRIVER_POOL)
    vehicle = random.choice(VEHICLE_POOL)

    # Price the ride from the rate card of its own vehicle type
    rates = VEHICLE_TYPE_BY_ID[vehicle['vehicle_type_id']]
    base_fare = rates['base_rate']
    distance_fare = round(distance * rates['per_mile'], 2)
    time_fare = round(duration_minutes * rates['per_minute'], 2)
    surge_multiplier = round(random.uniform(1.0, 2.5), 2)
    subtotal = round((distance_fare + time_fare + base_fare) * surge_multiplier, 2)

    # Get cities and their IDs
    pickup_city = random.choice(CITY_LIST)
    dropoff_city = random.choice(CITY_LIST)
    pickup_city_id = CITY_ID_MAP[pickup_city]
    dropoff_city_id = CITY_ID_MAP[dropoff_city]

    # Location details, anchored to the city the ride is attributed to
    pickup_address = fake.address().replace('\n', ', ')
    dropoff_address = fake.address().replace('\n', ', ')
    pickup_latitude, pickup_longitude = _coordinates_near(pickup_city_id)
    dropoff_latitude, dropoff_longitude = _coordinates_near(dropoff_city_id)

    # Status and cancellation reason are decided together, so a Completed ride
    # never carries a cancellation reason and a Cancelled one always does.
    is_cancelled = random.random() < CANCELLATION_RATE
    if is_cancelled:
        ride_status = 'Cancelled'
        cancellation_reason_id = CANCELLATION_REASON_ID_MAP[random.choice(CANCELLATION_REASONS_LIST)]
        # A cancelled ride is neither tipped nor rated.
        tip = 0.0
        rating = None
    else:
        ride_status = 'Completed'
        cancellation_reason_id = NOT_CANCELLED_REASON_ID
        tip = round(random.choice([0, 0, 0, 1, 2, 3, 5, random.uniform(1, 20)]), 2)
        rating = random.choice([None, random.randint(1, 5)])

    ride_status_id = RIDE_STATUS_ID_MAP[ride_status]
    total_fare = round(subtotal + tip, 2)

    # Get payment method and its ID
    payment_method = random.choice(PAYMENT_METHODS_LIST)
    payment_method_id = PAYMENT_METHOD_ID_MAP[payment_method]

    # Ride confirmation
    ride_confirmation = {
        # Keys/Identifiers
        'ride_id': str(uuid.uuid4()),
        'confirmation_number': fake.bothify('??#-####-??##'),
        'passenger_id': passenger['passenger_id'],
        'driver_id': driver['driver_id'],
        'vehicle_id': vehicle['vehicle_id'],
        'pickup_location_id': str(uuid.uuid4()),
        'dropoff_location_id': str(uuid.uuid4()),

        # Foreign Keys to Mapping Tables
        'vehicle_type_id': vehicle['vehicle_type_id'],
        'vehicle_make_id': vehicle['vehicle_make_id'],
        'payment_method_id': payment_method_id,
        'ride_status_id': ride_status_id,
        'pickup_city_id': pickup_city_id,
        'dropoff_city_id': dropoff_city_id,
        'cancellation_reason_id': cancellation_reason_id,

        # Passenger Information
        'passenger_name': passenger['passenger_name'],
        'passenger_email': passenger['passenger_email'],
        'passenger_phone': passenger['passenger_phone'],

        # Driver Information
        'driver_name': driver['driver_name'],
        'driver_rating': driver['driver_rating'],
        'driver_phone': driver['driver_phone'],
        'driver_license': driver['driver_license'],

        # Vehicle Information
        'vehicle_model': vehicle['vehicle_model'],
        'vehicle_color': vehicle['vehicle_color'],
        'license_plate': vehicle['license_plate'],

        # Pickup & Dropoff Locations
        'pickup_address': pickup_address,
        'pickup_latitude': pickup_latitude,
        'pickup_longitude': pickup_longitude,
        'dropoff_address': dropoff_address,
        'dropoff_latitude': dropoff_latitude,
        'dropoff_longitude': dropoff_longitude,

        # Ride Details - Measures
        'distance_miles': distance,
        'duration_minutes': duration_minutes,
        'booking_timestamp': booking_time.isoformat(),
        'pickup_timestamp': pickup_time.isoformat(),
        'dropoff_timestamp': dropoff_time.isoformat(),

        # Pricing - Measures
        'base_fare': base_fare,
        'distance_fare': distance_fare,
        'time_fare': time_fare,
        'surge_multiplier': surge_multiplier,
        'subtotal': subtotal,
        'tip_amount': tip,
        'total_fare': total_fare,

        # Payment & Status
        'rating': rating
    }

    return ride_confirmation
