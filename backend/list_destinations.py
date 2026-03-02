#!/usr/bin/env python3
"""List all destinations used in the booking system."""
from dotenv import load_dotenv
load_dotenv()

from database import SessionLocal
from db_models import FlightDeparture

db = SessionLocal()
destinations = db.query(
    FlightDeparture.destination_code,
    FlightDeparture.destination_name
).distinct().order_by(FlightDeparture.destination_name).all()

print('Destinations used in online and manual booking flows:')
print('=' * 50)
for code, name in destinations:
    if code and name:
        print(f'{code:4} | {name}')
print()
print(f'Total: {len([d for d in destinations if d[0] and d[1]])} destinations')
db.close()
