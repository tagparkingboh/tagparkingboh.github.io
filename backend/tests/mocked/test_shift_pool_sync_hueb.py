"""HUEB tests for duplicate shift booking-pool sync.

Unit-level coverage for the recursive sync helper. Router-level TestClient
coverage lives in test_roster_actions_v3.py.
"""
import sys
from datetime import date, time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db_models import Booking, BookingStatus, RosterShift, ShiftBookingLink, ShiftStatus, ShiftType
from shift_pool_sync import (
    sync_shift_pool_from_parent,
    synced_booking_source_shift,
    validate_shift_parent_assignment,
)


def make_shift(id, *, shift_date=date(2026, 7, 2), parent_shift_id=None, independent=False):
    s = RosterShift(
        id=id,
        staff_id=None,
        booking_id=None,
        date=shift_date,
        end_date=None,
        start_time=time(9, 0),
        end_time=time(17, 0),
        shift_type=ShiftType.MORNING,
        status=ShiftStatus.SCHEDULED,
        created_source="manual",
        intended_driver_type="jockey",
        parent_shift_id=parent_shift_id,
        dependents_independent=independent,
    )
    s.bookings = []
    return s


def make_booking(id, status=BookingStatus.CONFIRMED):
    b = Booking(
        id=id,
        reference=f"TAG-{id}",
        customer_id=1,
        vehicle_id=1,
        dropoff_date=date(2026, 7, 2),
        dropoff_time=time(10, 0),
        pickup_date=date(2026, 7, 9),
        pickup_time=time(10, 0),
        status=status,
    )
    return b


class FakeQuery:
    def __init__(self, db, model):
        self.db = db
        self.model = model
        self.shift_id = None
        self.parent_shift_id = None
        self.id_value = None

    def join(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def filter(self, *args):
        for arg in args:
            key = getattr(getattr(arg, "left", None), "key", None)
            value = getattr(getattr(arg, "right", None), "value", None)
            if key == "id":
                self.id_value = value
            elif key == "shift_id":
                self.shift_id = value
            elif key == "parent_shift_id":
                self.parent_shift_id = value
        return self

    def first(self):
        if self.model is RosterShift:
            return self.db.shifts.get(self.id_value)
        return None

    def all(self):
        if self.model is RosterShift:
            if self.parent_shift_id is not None:
                return [
                    s for s in self.db.shifts.values()
                    if s.parent_shift_id == self.parent_shift_id
                ]
            return list(self.db.shifts.values())
        if getattr(self.model, "key", None) == "booking_id":
            return [
                (link.booking_id,)
                for link in self.db.links
                if link.shift_id == self.shift_id
                and self.db.bookings[link.booking_id].status != BookingStatus.CANCELLED
            ]
        if self.model is ShiftBookingLink:
            return [link for link in self.db.links if link.shift_id == self.shift_id]
        return []


class FakeDB:
    def __init__(self):
        self.shifts = {}
        self.bookings = {}
        self.links = []
        self.deleted = []

    def query(self, model):
        return FakeQuery(self, model)

    def add(self, obj):
        if isinstance(obj, ShiftBookingLink):
            self.links.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)
        if isinstance(obj, ShiftBookingLink) and obj in self.links:
            self.links.remove(obj)


def link(db, shift_id, booking_id):
    db.links.append(ShiftBookingLink(shift_id=shift_id, booking_id=booking_id))


def linked_ids(db, shift_id):
    return sorted(link.booking_id for link in db.links if link.shift_id == shift_id)


def test_H_recursive_sync_copies_parent_confirmed_and_refunded_set():
    db = FakeDB()
    db.shifts = {
        1: make_shift(1),
        2: make_shift(2, parent_shift_id=1),
        3: make_shift(3, parent_shift_id=2),
    }
    db.bookings = {
        10: make_booking(10, BookingStatus.CONFIRMED),
        11: make_booking(11, BookingStatus.REFUNDED),
        12: make_booking(12, BookingStatus.CANCELLED),
        99: make_booking(99, BookingStatus.CONFIRMED),
    }
    link(db, 1, 10)
    link(db, 1, 11)
    link(db, 1, 12)
    link(db, 2, 99)
    link(db, 3, 99)

    changed = sync_shift_pool_from_parent(db, 1)

    assert changed == [2, 3]
    assert linked_ids(db, 2) == [10, 11]
    assert linked_ids(db, 3) == [10, 11]


def test_H_independent_parent_stops_sync_at_that_edge():
    db = FakeDB()
    db.shifts = {
        1: make_shift(1, independent=True),
        2: make_shift(2, parent_shift_id=1),
    }
    db.bookings = {
        10: make_booking(10),
        99: make_booking(99),
    }
    link(db, 1, 10)
    link(db, 2, 99)

    changed = sync_shift_pool_from_parent(db, 1)

    assert changed == []
    assert linked_ids(db, 2) == [99]


def test_H_pre_july_parent_never_syncs_even_if_tail_reaches_july():
    db = FakeDB()
    db.shifts = {
        1: make_shift(1, shift_date=date(2026, 6, 30)),
        2: make_shift(2, shift_date=date(2026, 7, 1), parent_shift_id=1),
    }
    db.bookings = {
        10: make_booking(10),
        99: make_booking(99),
    }
    link(db, 1, 10)
    link(db, 2, 99)

    changed = sync_shift_pool_from_parent(db, 1)

    assert changed == []
    assert linked_ids(db, 2) == [99]


def test_H_synced_booking_source_climbs_unchecked_ancestors():
    db = FakeDB()
    db.shifts = {
        1: make_shift(1),
        2: make_shift(2, parent_shift_id=1),
        3: make_shift(3, parent_shift_id=2),
    }

    assert synced_booking_source_shift(db, db.shifts[3]).id == 1


def test_H_cycle_guard_raises_instead_of_looping():
    db = FakeDB()
    db.shifts = {
        1: make_shift(1, parent_shift_id=2),
        2: make_shift(2, parent_shift_id=1),
    }

    with pytest.raises(ValueError):
        sync_shift_pool_from_parent(db, 1)


def test_H_source_guard_raises_same_cycle_contract():
    db = FakeDB()
    db.shifts = {
        1: make_shift(1, parent_shift_id=2),
        2: make_shift(2, parent_shift_id=1),
    }

    with pytest.raises(ValueError, match="Cycle detected in roster shift dependency tree"):
        synced_booking_source_shift(db, db.shifts[1])


def test_U_parent_assignment_rejects_self_parent():
    db = FakeDB()
    db.shifts = {1: make_shift(1)}

    with pytest.raises(ValueError, match="own parent"):
        validate_shift_parent_assignment(db, shift_id=1, parent_shift_id=1)


def test_U_parent_assignment_rejects_reparent_that_closes_loop():
    db = FakeDB()
    db.shifts = {
        1: make_shift(1),
        2: make_shift(2, parent_shift_id=1),
        3: make_shift(3, parent_shift_id=2),
    }

    with pytest.raises(ValueError, match="Cycle detected in roster shift dependency tree"):
        validate_shift_parent_assignment(db, shift_id=1, parent_shift_id=3)
