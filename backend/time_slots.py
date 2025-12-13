"""
Time slot calculation logic for TAG booking system.

Handles the calculation of drop-off times including edge cases where
flights depart shortly after midnight (e.g., 00:35 Tuesday requires
drop-off on Monday evening).
"""
from datetime import date, time, datetime, timedelta
from typing import Tuple
from models import SlotType, TimeSlot


# Time offsets in minutes before departure (for drop-offs)
SLOT_OFFSETS = {
    SlotType.EARLY: 165,  # 2 hours 45 minutes (2¾ hours)
    SlotType.LATE: 120,   # 2 hours
}

SLOT_LABELS = {
    SlotType.EARLY: "2¾ hours before",
    SlotType.LATE: "2 hours before",
}

# Minimum time in minutes for passengers to clear security/immigration after landing
ARRIVAL_CLEARANCE_BUFFER = 35


def calculate_drop_off_datetime(
    flight_date: date,
    flight_time: time,
    slot_type: SlotType
) -> Tuple[date, time]:
    """
    Calculate the drop-off date and time for a given flight and slot type.

    This handles the edge case where early morning flights (e.g., 00:35)
    require drop-off on the previous day.

    Args:
        flight_date: The date of the flight departure
        flight_time: The time of the flight departure
        slot_type: Either EARLY (2¾ hours before) or LATE (2 hours before)

    Returns:
        Tuple of (drop_off_date, drop_off_time)

    Examples:
        - Flight at 07:10 on Tuesday with EARLY slot:
          Drop-off at 04:25 on Tuesday

        - Flight at 00:35 on Tuesday with EARLY slot (165 min = 2h45m):
          00:35 - 2:45 = 21:50 on Monday

        - Flight at 00:35 on Tuesday with LATE slot (120 min = 2h):
          00:35 - 2:00 = 22:35 on Monday
    """
    offset_minutes = SLOT_OFFSETS[slot_type]

    # Combine date and time into a datetime for arithmetic
    flight_datetime = datetime.combine(flight_date, flight_time)

    # Subtract the offset
    drop_off_datetime = flight_datetime - timedelta(minutes=offset_minutes)

    return drop_off_datetime.date(), drop_off_datetime.time()


def calculate_all_slots(
    flight_date: date,
    flight_time: time,
    flight_number: str,
    airline_code: str
) -> list[TimeSlot]:
    """
    Calculate all available drop-off time slots for a flight.

    Args:
        flight_date: The date of the flight departure
        flight_time: The time of the flight departure
        flight_number: The flight number (e.g., "5523")
        airline_code: The airline code (e.g., "FR")

    Returns:
        List of TimeSlot objects, one for each slot type
    """
    slots = []

    for slot_type in SlotType:
        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, slot_type
        )

        # Create unique slot ID: date_time_flight_slottype
        slot_id = f"{drop_off_date.isoformat()}_{drop_off_time.strftime('%H%M')}_{airline_code}{flight_number}_{slot_type.value}"

        slot = TimeSlot(
            slot_id=slot_id,
            slot_type=slot_type,
            drop_off_date=drop_off_date,
            drop_off_time=drop_off_time,
            flight_date=flight_date,
            flight_time=flight_time,
            flight_number=flight_number,
            airline_code=airline_code,
            label=SLOT_LABELS[slot_type],
            is_available=True,
            booking_id=None
        )
        slots.append(slot)

    return slots


def format_time_display(t: time) -> str:
    """
    Format a time object for display.

    Args:
        t: A time object

    Returns:
        String in HH:MM format
    """
    return t.strftime("%H:%M")


def is_overnight_drop_off(flight_date: date, drop_off_date: date) -> bool:
    """
    Check if the drop-off occurs on a different day than the flight.

    This is useful for displaying warnings or additional information
    to users booking early morning flights.

    Args:
        flight_date: The date of the flight
        drop_off_date: The calculated drop-off date

    Returns:
        True if drop-off is on a different (earlier) day than the flight
    """
    return drop_off_date < flight_date


def get_day_name(d: date) -> str:
    """
    Get the day name for a date.

    Args:
        d: A date object

    Returns:
        Day name (e.g., "Monday", "Tuesday")
    """
    return d.strftime("%A")


def get_drop_off_summary(
    flight_date: date,
    flight_time: time,
    slot_type: SlotType
) -> dict:
    """
    Get a comprehensive summary of drop-off details for display.

    This is useful for the frontend to display clear information
    to the user, especially for overnight scenarios.

    Args:
        flight_date: The date of the flight
        flight_time: The time of the flight
        slot_type: The selected slot type

    Returns:
        Dictionary with drop-off details and display strings
    """
    drop_off_date, drop_off_time = calculate_drop_off_datetime(
        flight_date, flight_time, slot_type
    )

    is_overnight = is_overnight_drop_off(flight_date, drop_off_date)

    summary = {
        "flight_date": flight_date.isoformat(),
        "flight_time": format_time_display(flight_time),
        "flight_day": get_day_name(flight_date),
        "drop_off_date": drop_off_date.isoformat(),
        "drop_off_time": format_time_display(drop_off_time),
        "drop_off_day": get_day_name(drop_off_date),
        "slot_type": slot_type.value,
        "slot_label": SLOT_LABELS[slot_type],
        "is_overnight": is_overnight,
        "display_message": None
    }

    if is_overnight:
        summary["display_message"] = (
            f"Please note: Your flight departs at {format_time_display(flight_time)} on "
            f"{get_day_name(flight_date)}, so your drop-off will be at "
            f"{format_time_display(drop_off_time)} on {get_day_name(drop_off_date)} "
            f"(the evening before your flight)."
        )

    return summary


def calculate_pickup_datetime(
    arrival_date: date,
    arrival_time: time,
) -> Tuple[date, time]:
    """
    Calculate the pickup date and time for a returning passenger.

    Passengers need time to clear security/immigration after landing,
    so the pickup time is the arrival time plus the clearance buffer.

    This handles the edge case where late-night arrivals (e.g., 23:55)
    result in a pickup time after midnight (next day).

    Args:
        arrival_date: The date of the flight arrival
        arrival_time: The time of the flight arrival

    Returns:
        Tuple of (pickup_date, pickup_time)

    Examples:
        - Flight arrives at 14:30 on Tuesday:
          Pickup at 15:05 on Tuesday (14:30 + 35 min)

        - Flight arrives at 23:55 on Tuesday:
          Pickup at 00:30 on Wednesday (crosses midnight)

        - Flight arrives at 23:30 on Tuesday:
          Pickup at 00:05 on Wednesday (crosses midnight)
    """
    # Combine date and time into a datetime for arithmetic
    arrival_datetime = datetime.combine(arrival_date, arrival_time)

    # Add the clearance buffer
    pickup_datetime = arrival_datetime + timedelta(minutes=ARRIVAL_CLEARANCE_BUFFER)

    return pickup_datetime.date(), pickup_datetime.time()


def is_overnight_pickup(arrival_date: date, pickup_date: date) -> bool:
    """
    Check if the pickup occurs on a different day than the arrival.

    This happens when a late-night flight plus clearance time
    pushes the pickup past midnight.

    Args:
        arrival_date: The date of the flight arrival
        pickup_date: The calculated pickup date

    Returns:
        True if pickup is on a different (later) day than the arrival
    """
    return pickup_date > arrival_date


def get_pickup_summary(
    arrival_date: date,
    arrival_time: time,
) -> dict:
    """
    Get a comprehensive summary of pickup details for display.

    This is useful for the frontend to display clear information
    to the user, especially for overnight scenarios where a late
    arrival means pickup is technically the next day.

    Args:
        arrival_date: The date of the flight arrival
        arrival_time: The time of the flight arrival

    Returns:
        Dictionary with pickup details and display strings
    """
    pickup_date, pickup_time = calculate_pickup_datetime(
        arrival_date, arrival_time
    )

    is_overnight = is_overnight_pickup(arrival_date, pickup_date)

    summary = {
        "arrival_date": arrival_date.isoformat(),
        "arrival_time": format_time_display(arrival_time),
        "arrival_day": get_day_name(arrival_date),
        "pickup_date": pickup_date.isoformat(),
        "pickup_time": format_time_display(pickup_time),
        "pickup_day": get_day_name(pickup_date),
        "clearance_buffer_minutes": ARRIVAL_CLEARANCE_BUFFER,
        "is_overnight": is_overnight,
        "display_message": None
    }

    if is_overnight:
        summary["display_message"] = (
            f"Please note: Your flight arrives at {format_time_display(arrival_time)} on "
            f"{get_day_name(arrival_date)}. After clearing security/immigration "
            f"(approximately {ARRIVAL_CLEARANCE_BUFFER} minutes), your pickup will be at "
            f"{format_time_display(pickup_time)} on {get_day_name(pickup_date)} "
            f"(after midnight)."
        )
    else:
        summary["display_message"] = (
            f"Your flight arrives at {format_time_display(arrival_time)}. "
            f"We'll meet you at {format_time_display(pickup_time)} "
            f"(allowing {ARRIVAL_CLEARANCE_BUFFER} minutes to clear arrivals)."
        )

    return summary
