"""
Import flight schedule from Excel into the database.

This script reads the Bournemouth Airport flight schedule Excel file
and populates the flight_departures and flight_arrivals tables.

Mapping from Excel to Database:
- Date -> date
- Type -> determines table (Departure/Arrival)
- Mkt Al -> airline_code, airline_name (e.g., "FR : Ryanair")
- Flight -> flight_number
- Orig/Dest -> origin/destination codes and names
- Dep Time -> departure_time
- Arr Time -> arrival_time

For departures: is_slot_1_booked and is_slot_2_booked default to False
"""
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
import re
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine
from db_models import FlightDeparture, FlightArrival, Base


def parse_airline(mkt_al: str) -> tuple:
    """Parse 'FR : Ryanair' into ('FR', 'Ryanair')."""
    if pd.isna(mkt_al):
        return ('', '')
    parts = mkt_al.split(' : ')
    if len(parts) == 2:
        return (parts[0].strip(), parts[1].strip())
    return (mkt_al.strip(), mkt_al.strip())


def parse_airport_code(airport_name: str) -> str:
    """Extract airport code from name or generate one."""
    if pd.isna(airport_name):
        return ''

    # Known airport code mappings
    airport_codes = {
        'Bournemouth Airport': 'BOH',
        'Keflavík International Airport': 'KEF',
        'Málaga-Costa del Sol Airport': 'AGP',
        'Edinburgh Airport': 'EDI',
        'Alicante-Elche Airport': 'ALC',
        'Václav Havel Airport Prague': 'PRG',
        'Gran Canaria Airport': 'LPA',
        'Lanzarote Airport': 'ACE',
        'Malta International Airport': 'MLA',
        'Kraków John Paul II International Airport': 'KRK',
        'Tenerife South Airport': 'TFS',
        'Faro Airport': 'FAO',
        'Geneva Airport': 'GVA',
        'Palma de Mallorca Airport': 'PMI',
        'Fuerteventura Airport': 'FUE',
        'Dublin Airport': 'DUB',
        'Madeira Airport': 'FNC',
        'Ibiza Airport': 'IBZ',
        'Barcelona–El Prat Airport': 'BCN',
        'Menorca Airport': 'MAH',
        'Dalaman Airport': 'DLM',
        'Antalya Airport': 'AYT',
        'Paphos International Airport': 'PFO',
        'Split Airport': 'SPU',
        'Corfu International Airport': 'CFU',
        'Rhodes International Airport': 'RHO',
        'Heraklion International Airport': 'HER',
        'Enfidha-Hammamet International Airport': 'NBE',
    }

    # Check for exact match
    for name, code in airport_codes.items():
        if name.lower() in airport_name.lower():
            return code

    # Try to extract code from parentheses like "Lanzarote Airport (César Manrique-Lanzarote Airport)"
    match = re.search(r'\(([A-Z]{3})\)', airport_name)
    if match:
        return match.group(1)

    # Generate a code from first 3 letters as fallback
    clean_name = re.sub(r'[^a-zA-Z]', '', airport_name)
    return clean_name[:3].upper() if clean_name else 'UNK'


def parse_time(time_str) -> str:
    """Parse time string to HH:MM format."""
    if pd.isna(time_str):
        return None

    if isinstance(time_str, datetime):
        return time_str.strftime('%H:%M')

    time_str = str(time_str).strip()

    # Handle HH:MM format
    if ':' in time_str:
        parts = time_str.split(':')
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    return time_str


def import_flights(excel_path: str, db: Session):
    """Import flights from Excel file."""
    print(f"Reading Excel file: {excel_path}")

    # Read Excel, skip first 2 rows (title and blank)
    df = pd.read_excel(excel_path, skiprows=2)

    # Rename columns based on position
    column_names = [
        'date', 'day', 'type', 'mkt_al', 'alliance', 'op_al',
        'origin', 'destination', 'kilometers', 'flight', 'stops',
        'equip', 'seats', 'first', 'business', 'prem_econ', 'econ',
        'other', 'dep_term', 'arr_term', 'dep_time', 'arr_time',
        'block_mins', 'arr_flag', 'on_booking', 'num_spaces', 'total_hours'
    ]
    df.columns = column_names[:len(df.columns)]

    # Filter out header row and empty rows
    df = df[df['date'].notna()]
    df = df[df['date'] != 'Date']

    departures_count = 0
    arrivals_count = 0

    for _, row in df.iterrows():
        try:
            # Parse date
            date_val = row['date']
            if isinstance(date_val, str):
                date_val = datetime.strptime(date_val, '%Y-%m-%d').date()
            elif isinstance(date_val, datetime):
                date_val = date_val.date()
            else:
                continue

            # Parse airline
            airline_code, airline_name = parse_airline(row['mkt_al'])
            flight_number = str(int(row['flight'])) if pd.notna(row['flight']) else ''

            flight_type = str(row['type']).strip().lower()

            if flight_type == 'departure':
                # Get destination info
                dest_name = str(row['destination']) if pd.notna(row['destination']) else ''
                dest_code = parse_airport_code(dest_name)
                dep_time = parse_time(row['dep_time'])

                if not dep_time:
                    continue

                departure = FlightDeparture(
                    date=date_val,
                    flight_number=flight_number,
                    airline_code=airline_code,
                    airline_name=airline_name,
                    departure_time=datetime.strptime(dep_time, '%H:%M').time(),
                    destination_code=dest_code,
                    destination_name=dest_name[:100] if dest_name else None,
                    is_slot_1_booked=False,
                    is_slot_2_booked=False,
                )
                db.add(departure)
                departures_count += 1

            elif flight_type == 'arrival':
                # Get origin info
                orig_name = str(row['origin']) if pd.notna(row['origin']) else ''
                orig_code = parse_airport_code(orig_name)
                dep_time = parse_time(row['dep_time'])
                arr_time = parse_time(row['arr_time'])

                if not arr_time:
                    continue

                arrival = FlightArrival(
                    date=date_val,
                    flight_number=flight_number,
                    airline_code=airline_code,
                    airline_name=airline_name,
                    departure_time=datetime.strptime(dep_time, '%H:%M').time() if dep_time else None,
                    arrival_time=datetime.strptime(arr_time, '%H:%M').time(),
                    origin_code=orig_code,
                    origin_name=orig_name[:100] if orig_name else None,
                )
                db.add(arrival)
                arrivals_count += 1

        except Exception as e:
            print(f"Error processing row: {e}")
            print(f"Row data: {row.to_dict()}")
            continue

    db.commit()
    print(f"\nImport complete!")
    print(f"  Departures: {departures_count}")
    print(f"  Arrivals: {arrivals_count}")
    print(f"  Total: {departures_count + arrivals_count}")


def main():
    """Main entry point."""
    excel_path = "../tag-website/src/Bournemouth_Flight_Schedule_1 week model.xlsx"

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    # Clear existing flight data
    db = SessionLocal()
    try:
        db.query(FlightDeparture).delete()
        db.query(FlightArrival).delete()
        db.commit()
        print("Cleared existing flight data")

        import_flights(excel_path, db)

        # Verify counts
        dep_count = db.query(FlightDeparture).count()
        arr_count = db.query(FlightArrival).count()
        print(f"\nDatabase now contains:")
        print(f"  flight_departures: {dep_count}")
        print(f"  flight_arrivals: {arr_count}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
