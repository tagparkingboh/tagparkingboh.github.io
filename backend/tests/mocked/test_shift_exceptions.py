from datetime import date, time
from types import SimpleNamespace

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db_models import ShiftStatus
from routers.roster import _build_shift_exceptions


def mk_booking(*, shifts=None, pickup_date=None):
    return SimpleNamespace(
        id=778,
        reference="TAG-FZM98471",
        customer_first_name="Joe",
        customer_last_name="Cross",
        shifts=shifts or [],
        dropoff_date=date(2026, 6, 14),
        dropoff_time=time(5, 5),
        dropoff_flight_number="TOM6728",
        dropoff_destination="Palma de Mallorca Airport",
        pickup_date=pickup_date,
        pickup_time=None,
        pickup_flight_number=None,
        pickup_origin=None,
        flight_arrival_date=None,
        flight_arrival_time=None,
    )


def mk_shift(*, id=4628, intended_driver_type="fleet", start_time=time(3, 35), end_time=time(7, 15)):
    return SimpleNamespace(
        id=id,
        date=date(2026, 6, 14),
        end_date=None,
        start_time=start_time,
        end_time=end_time,
        status=ShiftStatus.SCHEDULED,
        intended_driver_type=intended_driver_type,
        created_source="auto",
        staff_id=None,
        staff=None,
        booking_id=None,
    )


def test_unlinked_booking_inside_shift_window_surfaces_suggested_shift():
    shift = mk_shift()
    booking = mk_booking()

    result = _build_shift_exceptions(
        [booking],
        [shift],
        date(2026, 6, 14),
        date(2026, 6, 14),
    )

    assert len(result) == 1
    exception = result[0]
    assert exception["issue"] == "unlinked_shift"
    assert exception["booking_reference"] == "TAG-FZM98471"
    assert exception["event_type"] == "dropoff"
    assert exception["event_time"] == "05:05"
    assert exception["suggested_shift"]["id"] == 4628
    assert exception["suggested_shift"]["intended_driver_type"] == "fleet"


def test_linked_booking_inside_shift_window_clears_exception():
    shift = mk_shift()
    booking = mk_booking(shifts=[shift])

    result = _build_shift_exceptions(
        [booking],
        [shift],
        date(2026, 6, 14),
        date(2026, 6, 14),
    )

    assert result == []


def test_linked_booking_inside_implicit_midnight_shift_clears_exception():
    shift = mk_shift(start_time=time(19, 30), end_time=time(0, 0))
    booking = mk_booking(shifts=[shift])
    booking.dropoff_time = time(22, 50)

    result = _build_shift_exceptions(
        [booking],
        [shift],
        date(2026, 6, 14),
        date(2026, 6, 14),
    )

    assert result == []


def test_booking_without_covering_shift_surfaces_no_shift_issue():
    booking = mk_booking()

    result = _build_shift_exceptions(
        [booking],
        [mk_shift(start_time=time(8, 0), end_time=time(10, 0))],
        date(2026, 6, 14),
        date(2026, 6, 14),
    )

    assert len(result) == 1
    assert result[0]["issue"] == "no_shift"
    assert result[0]["suggested_shift"] is None
