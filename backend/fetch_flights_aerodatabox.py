#!/usr/bin/env python3
"""
Fetch flight schedules from AeroDataBox API for Bournemouth Airport (BOH).

Fetches departures and arrivals from March 1st to December 31st 2026.
Each day requires 2 API calls (00:00-12:00 and 12:00-24:00).
Results are incrementally saved to CSV files.

Usage:
    python fetch_flights_aerodatabox.py

The script will resume from the last fetched date if interrupted.
"""

import os
import csv
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# Configuration
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "154bc10511msh00651eb8841f3dbp1316d7jsn6f1bea1da0c0")
AIRPORT_CODE = "BOH"
BASE_URL = "https://aerodatabox.p.rapidapi.com/flights/airports/iata"

# Date range: February 27, 2026 to December 31, 2026
START_DATE = datetime(2026, 2, 27)
END_DATE = datetime(2026, 12, 31)

# Output files
OUTPUT_DIR = Path(__file__).parent
DEPARTURES_CSV = OUTPUT_DIR / "aerodatabox_departures_feb27_dec31.csv"
ARRIVALS_CSV = OUTPUT_DIR / "aerodatabox_arrivals_feb27_dec31.csv"

# Rate limiting
DELAY_BETWEEN_CALLS = 1.5  # seconds

# CSV headers matching database schema
DEPARTURES_HEADERS = [
    "date", "flight_number", "airline_code", "airline_name",
    "departure_time", "destination_code", "destination_name", "fetched_at"
]
ARRIVALS_HEADERS = [
    "date", "flight_number", "airline_code", "airline_name",
    "arrival_time", "origin_code", "origin_name", "fetched_at"
]


def get_last_fetched_date(csv_path: Path) -> Optional[datetime]:
    """Check the CSV to find the last date that was fetched."""
    if not csv_path.exists():
        return None

    last_date = None
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('date'):
                    last_date = row['date']

        if last_date:
            return datetime.strptime(last_date, '%Y-%m-%d')
    except Exception as e:
        print(f"Error reading {csv_path}: {e}")

    return None


def init_csv_files():
    """Initialize CSV files with headers if they don't exist."""
    if not DEPARTURES_CSV.exists():
        with open(DEPARTURES_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(DEPARTURES_HEADERS)
        print(f"Created {DEPARTURES_CSV}")

    if not ARRIVALS_CSV.exists():
        with open(ARRIVALS_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(ARRIVALS_HEADERS)
        print(f"Created {ARRIVALS_CSV}")


def fetch_flights(date: datetime, from_hour: int, to_hour: int, to_minute: int = 0) -> dict:
    """
    Fetch flights from AeroDataBox API for a specific date and time range.

    Args:
        date: The date to fetch
        from_hour: Start hour (0-23)
        to_hour: End hour (0-23)
        to_minute: End minute (0-59), defaults to 0

    Returns:
        API response as dict with 'departures' and 'arrivals' keys
    """
    # Format: YYYY-MM-DDTHH:MM
    from_time = f"{date.strftime('%Y-%m-%d')}T{from_hour:02d}:00"
    to_time = f"{date.strftime('%Y-%m-%d')}T{to_hour:02d}:{to_minute:02d}"

    url = f"{BASE_URL}/{AIRPORT_CODE}/{from_time}/{to_time}"

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "aerodatabox.p.rapidapi.com"
    }

    params = {
        "direction": "Both",
        "withLeg": "true",
        "withCancelled": "false",
        "withCodeshared": "false",
        "withCargo": "false",
        "withPrivate": "false"
    }

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    return response.json()


def parse_departure(flight: Dict, date: datetime, fetched_at: str) -> Dict:
    """
    Parse a departure flight from API response (with withLeg=true).

    API structure for departures:
    - 'departure' contains scheduled departure time from BOH
    - 'arrival' contains destination airport info
    - 'number' is the flight number (e.g., "FR 3944")
    - 'airline' contains airline info
    """
    departure_info = flight.get('departure', {})
    arrival_info = flight.get('arrival', {})

    # Extract departure time from local format "2026-02-27 06:45+00:00" -> "06:45"
    departure_time = ''
    local_time = departure_info.get('scheduledTime', {}).get('local', '')
    if local_time and len(local_time) >= 16:
        departure_time = local_time[11:16]  # Extract HH:MM

    # Clean flight number (remove space: "FR 3944" -> "FR3944")
    flight_number = flight.get('number', '').replace(' ', '')

    return {
        "date": date.strftime('%Y-%m-%d'),
        "flight_number": flight_number,
        "airline_code": flight.get('airline', {}).get('iata', ''),
        "airline_name": flight.get('airline', {}).get('name', ''),
        "departure_time": departure_time,
        "destination_code": arrival_info.get('airport', {}).get('iata', ''),
        "destination_name": arrival_info.get('airport', {}).get('name', ''),
        "fetched_at": fetched_at
    }


def parse_arrival(flight: Dict, date: datetime, fetched_at: str) -> Dict:
    """
    Parse an arrival flight from API response (with withLeg=true).

    API structure for arrivals:
    - 'departure' contains origin airport info
    - 'arrival' contains scheduled arrival time at BOH
    - 'number' is the flight number
    - 'airline' contains airline info
    """
    departure_info = flight.get('departure', {})
    arrival_info = flight.get('arrival', {})

    # Extract arrival time at BOH
    arrival_time = ''
    local_time = arrival_info.get('scheduledTime', {}).get('local', '')
    if local_time and len(local_time) >= 16:
        arrival_time = local_time[11:16]

    # Clean flight number
    flight_number = flight.get('number', '').replace(' ', '')

    return {
        "date": date.strftime('%Y-%m-%d'),
        "flight_number": flight_number,
        "airline_code": flight.get('airline', {}).get('iata', ''),
        "airline_name": flight.get('airline', {}).get('name', ''),
        "arrival_time": arrival_time,
        "origin_code": departure_info.get('airport', {}).get('iata', ''),
        "origin_name": departure_info.get('airport', {}).get('name', ''),
        "fetched_at": fetched_at
    }


def append_to_csv(csv_path: Path, rows: List[Dict], headers: List[str]):
    """Append rows to CSV file."""
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        for row in rows:
            writer.writerow(row)


def fetch_day(date: datetime) -> Tuple[List[Dict], List[Dict]]:
    """
    Fetch all flights for a single day (2 API calls).

    Returns:
        Tuple of (departures, arrivals)
    """
    departures = []
    arrivals = []
    fetched_at = datetime.now().isoformat()

    # First half of day: 00:00 - 12:00
    print(f"  Fetching {date.strftime('%Y-%m-%d')} 00:00-12:00...", end=" ", flush=True)
    try:
        data = fetch_flights(date, 0, 12)

        for flight in data.get('departures', []):
            departures.append(parse_departure(flight, date, fetched_at))
        for flight in data.get('arrivals', []):
            arrivals.append(parse_arrival(flight, date, fetched_at))

        print(f"OK ({len(data.get('departures', []))} dep, {len(data.get('arrivals', []))} arr)")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: {e}")
    except Exception as e:
        print(f"ERROR: {e}")

    time.sleep(DELAY_BETWEEN_CALLS)

    # Second half of day: 12:00 - 23:59
    print(f"  Fetching {date.strftime('%Y-%m-%d')} 12:00-23:59...", end=" ", flush=True)
    try:
        data = fetch_flights(date, 12, 23, 59)

        for flight in data.get('departures', []):
            departures.append(parse_departure(flight, date, fetched_at))
        for flight in data.get('arrivals', []):
            arrivals.append(parse_arrival(flight, date, fetched_at))

        print(f"OK ({len(data.get('departures', []))} dep, {len(data.get('arrivals', []))} arr)")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: {e}")
    except Exception as e:
        print(f"ERROR: {e}")

    time.sleep(DELAY_BETWEEN_CALLS)

    return departures, arrivals


def main():
    print("=" * 60)
    print("AeroDataBox Flight Fetcher for Bournemouth Airport (BOH)")
    print("=" * 60)
    print(f"Date range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Output: {DEPARTURES_CSV.name}, {ARRIVALS_CSV.name}")
    print()

    # Initialize CSV files
    init_csv_files()

    # Check for resume point
    last_dep_date = get_last_fetched_date(DEPARTURES_CSV)
    last_arr_date = get_last_fetched_date(ARRIVALS_CSV)

    # Use the earlier of the two (or START_DATE if none)
    resume_date = START_DATE
    if last_dep_date and last_arr_date:
        resume_date = min(last_dep_date, last_arr_date) + timedelta(days=1)
        print(f"Resuming from {resume_date.strftime('%Y-%m-%d')} (last completed: {min(last_dep_date, last_arr_date).strftime('%Y-%m-%d')})")
    elif last_dep_date or last_arr_date:
        last = last_dep_date or last_arr_date
        resume_date = last + timedelta(days=1)
        print(f"Resuming from {resume_date.strftime('%Y-%m-%d')}")

    # Calculate total days
    total_days = (END_DATE - resume_date).days + 1
    if total_days <= 0:
        print("All dates already fetched!")
        return

    print(f"Days to fetch: {total_days}")
    print(f"Estimated API calls: {total_days * 2}")
    print(f"Estimated time: {total_days * 2 * DELAY_BETWEEN_CALLS / 60:.1f} minutes")
    print()

    # Fetch each day
    current_date = resume_date
    day_count = 0
    total_departures = 0
    total_arrivals = 0

    while current_date <= END_DATE:
        day_count += 1
        print(f"[{day_count}/{total_days}] Processing {current_date.strftime('%Y-%m-%d')}...")

        departures, arrivals = fetch_day(current_date)

        # Append to CSV files
        if departures:
            append_to_csv(DEPARTURES_CSV, departures, DEPARTURES_HEADERS)
            total_departures += len(departures)

        if arrivals:
            append_to_csv(ARRIVALS_CSV, arrivals, ARRIVALS_HEADERS)
            total_arrivals += len(arrivals)

        print(f"  Saved: {len(departures)} departures, {len(arrivals)} arrivals")
        print()

        current_date += timedelta(days=1)

    print("=" * 60)
    print("COMPLETE!")
    print(f"Total departures: {total_departures}")
    print(f"Total arrivals: {total_arrivals}")
    print(f"Files: {DEPARTURES_CSV.name}, {ARRIVALS_CSV.name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
