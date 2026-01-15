"""
Fix missing destination_code values in flight_departures table.

This script updates departures that have empty destination_code by looking up
the IATA code from the destination_name.

Usage:
    python scripts/fix_destination_codes.py [--dry-run]
"""
import os
import sys
import re

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# IATA airport code mappings (destination_name -> code)
AIRPORT_CODES = {
    'bournemouth airport': 'BOH',
    'keflavík international airport': 'KEF',
    'keflavik international airport': 'KEF',
    'málaga-costa del sol airport': 'AGP',
    'malaga-costa del sol airport': 'AGP',
    'malaga': 'AGP',
    'edinburgh airport': 'EDI',
    'edinburgh': 'EDI',
    'alicante-elche airport': 'ALC',
    'alicante': 'ALC',
    'václav havel airport prague': 'PRG',
    'prague': 'PRG',
    'gran canaria airport': 'LPA',
    'gran canaria': 'LPA',
    'lanzarote airport': 'ACE',
    'lanzarote airport (césar manrique-lanzarote airport)': 'ACE',
    'lanzarote': 'ACE',
    'malta international airport': 'MLA',
    'malta': 'MLA',
    'kraków john paul ii international airport': 'KRK',
    'krakow john paul ii international airport': 'KRK',
    'krakow': 'KRK',
    'tenerife south airport': 'TFS',
    'tenerife': 'TFS',
    'faro airport': 'FAO',
    'faro': 'FAO',
    'geneva airport': 'GVA',
    'geneva': 'GVA',
    'palma de mallorca airport': 'PMI',
    'palma de mallorca': 'PMI',
    'palma': 'PMI',
    'fuerteventura airport': 'FUE',
    'fuerteventura': 'FUE',
    'dublin airport': 'DUB',
    'dublin': 'DUB',
    'madeira airport': 'FNC',
    'madeira airport (cristiano ronaldo international airport)': 'FNC',
    'madeira': 'FNC',
    'ibiza airport': 'IBZ',
    'ibiza': 'IBZ',
    'barcelona–el prat airport': 'BCN',
    'barcelona-el prat airport': 'BCN',
    'barcelona': 'BCN',
    'menorca airport': 'MAH',
    'menorca': 'MAH',
    'dalaman airport': 'DLM',
    'dalaman': 'DLM',
    'antalya airport': 'AYT',
    'antalya': 'AYT',
    'paphos international airport': 'PFO',
    'paphos': 'PFO',
    'split airport': 'SPU',
    'split': 'SPU',
    'corfu international airport': 'CFU',
    'corfu': 'CFU',
    'rhodes international airport': 'RHO',
    'rhodes': 'RHO',
    'heraklion international airport': 'HER',
    'heraklion': 'HER',
    'enfidha-hammamet international airport': 'NBE',
    'enfidha': 'NBE',
    'wrocław copernicus airport': 'WRO',
    'wroclaw copernicus airport': 'WRO',
    'wroclaw': 'WRO',
    'agadir–al massira airport': 'AGA',
    'agadir-al massira airport': 'AGA',
    'agadir': 'AGA',
    'grantley adams international airport': 'BGI',
    'barbados': 'BGI',
    'tenerife-reinasofia': 'TFS',
    'reykjavik': 'KEF',
    # Additional airports
    'trapani-birgi airport': 'TPS',
    'trapani': 'TPS',
    'región de murcia international airport': 'RMU',
    'murcia': 'RMU',
    'chania international airport': 'CHQ',
    'chania': 'CHQ',
    'carcassonne airport': 'CCF',
    'carcassonne': 'CCF',
    'zakynthos international airport': 'ZTH',
    'zakynthos': 'ZTH',
    'kefalonia international airport': 'EFL',
    'kefalonia': 'EFL',
    'zadar airport': 'ZAD',
    'zadar': 'ZAD',
    'larnaca international airport': 'LCA',
    'larnaca': 'LCA',
    'girona-costa brava airport': 'GRO',
    'girona': 'GRO',
    'kos island international airport': 'KGS',
    'kos': 'KGS',
}


def get_airport_code(airport_name: str) -> str:
    """Extract or lookup airport code from name."""
    if not airport_name:
        return None

    name_lower = airport_name.lower().strip()

    # Check exact match
    if name_lower in AIRPORT_CODES:
        return AIRPORT_CODES[name_lower]

    # Check partial match (airport name contains the key)
    for key, code in AIRPORT_CODES.items():
        if key in name_lower or name_lower in key:
            return code

    # Try to extract code from parentheses like "(ABC)"
    match = re.search(r'\(([A-Z]{3})\)', airport_name)
    if match:
        return match.group(1)

    return None


def fix_destination_codes(dry_run: bool = False):
    """Update departures with missing destination_code."""

    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        # Use production database
        database_url = 'postgresql://postgres:wjqOmlfMamCcuIEwydmamWeGoJKmUlJb@trolley.proxy.rlwy.net:39730/railway'

    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Get all unique destination_names with empty codes
        result = conn.execute(text("""
            SELECT DISTINCT destination_name
            FROM flight_departures
            WHERE destination_code = '' OR destination_code IS NULL
        """))

        destinations = [row[0] for row in result]
        print(f"Found {len(destinations)} unique destinations with empty codes:\n")

        updates = []
        unmatched = []

        for dest_name in destinations:
            code = get_airport_code(dest_name)
            if code:
                updates.append((dest_name, code))
                print(f"  ✓ '{dest_name}' -> {code}")
            else:
                unmatched.append(dest_name)
                print(f"  ✗ '{dest_name}' -> NO MATCH")

        print(f"\n{len(updates)} destinations matched, {len(unmatched)} unmatched")

        if unmatched:
            print("\nUnmatched destinations (need manual mapping):")
            for name in unmatched:
                print(f"  - {name}")

        if dry_run:
            print("\n[DRY RUN] No changes made")
            return

        if not updates:
            print("\nNo updates to make")
            return

        # Apply updates
        print(f"\nApplying {len(updates)} updates...")

        for dest_name, code in updates:
            result = conn.execute(
                text("""
                    UPDATE flight_departures
                    SET destination_code = :code
                    WHERE destination_name = :name
                    AND (destination_code = '' OR destination_code IS NULL)
                """),
                {"code": code, "name": dest_name}
            )
            print(f"  Updated {result.rowcount} rows for '{dest_name}' -> {code}")

        conn.commit()
        print("\n✓ All updates committed")

        # Verify
        result = conn.execute(text("""
            SELECT COUNT(*) FROM flight_departures
            WHERE destination_code = '' OR destination_code IS NULL
        """))
        remaining = result.scalar()
        print(f"\nRemaining departures with empty destination_code: {remaining}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("Running in DRY RUN mode\n")

    fix_destination_codes(dry_run=dry_run)
