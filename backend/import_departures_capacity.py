"""
Import departure flights with capacity tiers from the new format.

New format columns:
- Date, Day, Op Al, Dest, Flight, Dep Time, Forming Service Arr Time
- 0 Spaces, 2 Spaces, 4 Spaces, 6 Spaces, 8 Spaces (exactly one TRUE per row)

This script reads the departure data and populates flight_departures with:
- capacity_tier (0, 2, 4, 6, or 8)
- slots_booked_early = 0
- slots_booked_late = 0

Usage:
    python import_departures_capacity.py <csv_or_xlsx_file>

Or from Python:
    from import_departures_capacity import import_from_csv_string
    import_from_csv_string(csv_data)
"""
import sys
import os
from datetime import datetime
import re

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine
from db_models import FlightDeparture, Base


# Known airport code mappings
AIRPORT_CODES = {
    'bournemouth airport': 'BOH',
    'keflavík international airport': 'KEF',
    'keflavik international airport': 'KEF',
    'málaga-costa del sol airport': 'AGP',
    'malaga-costa del sol airport': 'AGP',
    'edinburgh airport': 'EDI',
    'alicante-elche airport': 'ALC',
    'václav havel airport prague': 'PRG',
    'gran canaria airport': 'LPA',
    'lanzarote airport': 'ACE',
    'lanzarote airport (césar manrique-lanzarote airport)': 'ACE',
    'malta international airport': 'MLA',
    'kraków john paul ii international airport': 'KRK',
    'krakow john paul ii international airport': 'KRK',
    'tenerife south airport': 'TFS',
    'faro airport': 'FAO',
    'geneva airport': 'GVA',
    'palma de mallorca airport': 'PMI',
    'fuerteventura airport': 'FUE',
    'dublin airport': 'DUB',
    'madeira airport': 'FNC',
    'madeira airport (cristiano ronaldo international airport)': 'FNC',
    'ibiza airport': 'IBZ',
    'barcelona–el prat airport': 'BCN',
    'menorca airport': 'MAH',
    'dalaman airport': 'DLM',
    'antalya airport': 'AYT',
    'paphos international airport': 'PFO',
    'split airport': 'SPU',
    'corfu international airport': 'CFU',
    'rhodes international airport': 'RHO',
    'heraklion international airport': 'HER',
    'enfidha-hammamet international airport': 'NBE',
    'wrocław copernicus airport': 'WRO',
    'wroclaw copernicus airport': 'WRO',
    'agadir–al massira airport': 'AGA',
    'agadir-al massira airport': 'AGA',
    'grantley adams international airport': 'BGI',
}


def get_airport_code(airport_name: str) -> str:
    """Extract or lookup airport code from name."""
    if not airport_name:
        return 'UNK'

    name_lower = airport_name.lower().strip()

    # Check known mappings
    if name_lower in AIRPORT_CODES:
        return AIRPORT_CODES[name_lower]

    # Try to extract code from parentheses like "(ABC)"
    match = re.search(r'\(([A-Z]{3})\)', airport_name)
    if match:
        return match.group(1)

    # Generate a code from first 3 letters as fallback
    clean_name = re.sub(r'[^a-zA-Z]', '', airport_name)
    return clean_name[:3].upper() if clean_name else 'UNK'


def parse_airline(op_al: str) -> tuple:
    """Parse 'FR : Ryanair' into ('FR', 'Ryanair')."""
    if not op_al:
        return ('', '')
    parts = op_al.split(' : ')
    if len(parts) == 2:
        return (parts[0].strip(), parts[1].strip())
    return (op_al.strip(), op_al.strip())


def parse_time(time_str: str) -> str:
    """Parse time string to HH:MM format."""
    if not time_str:
        return None

    time_str = str(time_str).strip()

    # Handle HH:MM format
    if ':' in time_str:
        parts = time_str.split(':')
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    return time_str


def get_capacity_tier(row_data: dict) -> int:
    """
    Determine capacity tier from the boolean columns.
    Exactly one of 0/2/4/6/8 Spaces should be TRUE.
    """
    for tier in [0, 2, 4, 6, 8]:
        col_name = f'{tier} Spaces' if tier > 0 else '0 Spaces'
        # Also check alternate names
        alt_names = [col_name, f'{tier}_spaces', f'{tier}spaces', f'{tier} spaces']

        for name in alt_names:
            if name in row_data:
                val = row_data[name]
                if isinstance(val, bool):
                    if val:
                        return tier
                elif isinstance(val, str):
                    if val.upper() == 'TRUE':
                        return tier

    # Default to 0 if no TRUE found
    return 0


def import_from_tsv_string(tsv_data: str, clear_existing: bool = True) -> dict:
    """
    Import departure data from a TSV (tab-separated) string.

    Returns dict with counts.
    """
    db = SessionLocal()
    try:
        if clear_existing:
            db.query(FlightDeparture).delete()
            db.commit()
            print("Cleared existing departure data")

        lines = tsv_data.strip().split('\n')
        if not lines:
            return {"error": "No data provided"}

        # Parse header
        header = lines[0].split('\t')
        header = [h.strip() for h in header]

        count = 0
        errors = []

        for line_num, line in enumerate(lines[1:], start=2):
            try:
                values = line.split('\t')
                row = dict(zip(header, values))

                # Parse date
                date_str = row.get('Date', '').strip()
                if not date_str:
                    continue
                flight_date = datetime.strptime(date_str, '%Y-%m-%d').date()

                # Parse airline
                airline_code, airline_name = parse_airline(row.get('Op Al', ''))

                # Parse flight number
                flight_num = row.get('Flight', '').strip()

                # Parse departure time
                dep_time_str = parse_time(row.get('Dep Time', ''))
                if not dep_time_str:
                    continue
                dep_time = datetime.strptime(dep_time_str, '%H:%M').time()

                # Parse destination
                dest_name = row.get('Dest', '').strip()
                dest_code = get_airport_code(dest_name)

                # Get capacity tier
                capacity_tier = get_capacity_tier(row)

                departure = FlightDeparture(
                    date=flight_date,
                    flight_number=flight_num,
                    airline_code=airline_code,
                    airline_name=airline_name,
                    departure_time=dep_time,
                    destination_code=dest_code,
                    destination_name=dest_name[:100] if dest_name else None,
                    capacity_tier=capacity_tier,
                    slots_booked_early=0,
                    slots_booked_late=0,
                )
                db.add(departure)
                count += 1

            except Exception as e:
                errors.append(f"Line {line_num}: {str(e)}")
                continue

        db.commit()

        return {
            "success": True,
            "departures_imported": count,
            "errors": errors[:10] if errors else []  # Return first 10 errors
        }

    finally:
        db.close()


def import_from_xlsx(xlsx_path: str, clear_existing: bool = True) -> dict:
    """
    Import departure data from an Excel file.
    """
    try:
        import pandas as pd
    except ImportError:
        return {"error": "pandas not installed. Run: pip install pandas openpyxl"}

    try:
        df = pd.read_excel(xlsx_path)
    except Exception as e:
        return {"error": f"Failed to read Excel file: {str(e)}"}

    db = SessionLocal()
    try:
        if clear_existing:
            db.query(FlightDeparture).delete()
            db.commit()
            print("Cleared existing departure data")

        count = 0
        errors = []

        for idx, row in df.iterrows():
            try:
                # Parse date
                date_val = row.get('Date')
                if pd.isna(date_val):
                    continue
                if isinstance(date_val, str):
                    flight_date = datetime.strptime(date_val, '%Y-%m-%d').date()
                else:
                    flight_date = date_val.date() if hasattr(date_val, 'date') else date_val

                # Parse airline
                airline_code, airline_name = parse_airline(str(row.get('Op Al', '')))

                # Parse flight number
                flight_num = str(int(row.get('Flight'))) if pd.notna(row.get('Flight')) else ''

                # Parse departure time
                dep_time_val = row.get('Dep Time')
                if pd.isna(dep_time_val):
                    continue
                if hasattr(dep_time_val, 'strftime'):
                    dep_time_str = dep_time_val.strftime('%H:%M')
                else:
                    dep_time_str = parse_time(str(dep_time_val))
                dep_time = datetime.strptime(dep_time_str, '%H:%M').time()

                # Parse destination
                dest_name = str(row.get('Dest', '')) if pd.notna(row.get('Dest')) else ''
                dest_code = get_airport_code(dest_name)

                # Get capacity tier from boolean columns
                capacity_tier = 0
                for tier in [0, 2, 4, 6, 8]:
                    col_name = f'{tier} Spaces'
                    if col_name in row and pd.notna(row[col_name]):
                        val = row[col_name]
                        if val is True or (isinstance(val, str) and val.upper() == 'TRUE'):
                            capacity_tier = tier
                            break

                departure = FlightDeparture(
                    date=flight_date,
                    flight_number=flight_num,
                    airline_code=airline_code,
                    airline_name=airline_name,
                    departure_time=dep_time,
                    destination_code=dest_code,
                    destination_name=dest_name[:100] if dest_name else None,
                    capacity_tier=capacity_tier,
                    slots_booked_early=0,
                    slots_booked_late=0,
                )
                db.add(departure)
                count += 1

            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                continue

        db.commit()

        return {
            "success": True,
            "departures_imported": count,
            "errors": errors[:10] if errors else []
        }

    finally:
        db.close()


def main():
    """Main entry point for command line usage."""
    if len(sys.argv) < 2:
        print("Usage: python import_departures_capacity.py <xlsx_file>")
        print("       python import_departures_capacity.py --stdin  (reads TSV from stdin)")
        sys.exit(1)

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    arg = sys.argv[1]

    if arg == '--stdin':
        # Read from stdin (TSV format)
        tsv_data = sys.stdin.read()
        result = import_from_tsv_string(tsv_data)
    elif arg.endswith('.xlsx'):
        result = import_from_xlsx(arg)
    else:
        print(f"Unsupported file format: {arg}")
        print("Supported formats: .xlsx or --stdin for TSV")
        sys.exit(1)

    if result.get('error'):
        print(f"Error: {result['error']}")
        sys.exit(1)

    print(f"\nImport complete!")
    print(f"  Departures imported: {result['departures_imported']}")
    if result.get('errors'):
        print(f"  Errors ({len(result['errors'])}):")
        for err in result['errors']:
            print(f"    - {err}")

    # Verify counts
    db = SessionLocal()
    try:
        total = db.query(FlightDeparture).count()
        by_tier = {}
        for tier in [0, 2, 4, 6, 8]:
            by_tier[tier] = db.query(FlightDeparture).filter(
                FlightDeparture.capacity_tier == tier
            ).count()

        print(f"\nDatabase now contains {total} departures:")
        for tier, cnt in by_tier.items():
            print(f"  Capacity {tier}: {cnt} flights")
    finally:
        db.close()


if __name__ == "__main__":
    main()
