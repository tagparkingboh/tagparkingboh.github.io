"""Synchronized booking pools for duplicated roster shifts.

The pool is directional: a parent shift owns the booking set, and its children
mirror it while the parent remains `dependents_independent = false`.
"""
from __future__ import annotations

from datetime import date as date_type

from sqlalchemy.orm import Session

from db_models import Booking, BookingStatus, RosterShift, ShiftBookingLink
from roster_effective_date import get_roster_effective_date


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _int_id(value) -> int | None:
    return value if isinstance(value, int) else None


def shift_pool_sync_enabled(shift: RosterShift | None) -> bool:
    shift_date = getattr(shift, "date", None) if shift is not None else None
    return bool(
        isinstance(shift_date, date_type)
        and shift_date >= get_roster_effective_date()
    )


def _cycle_error(shift_id: int) -> ValueError:
    return ValueError(f"Cycle detected in roster shift dependency tree at shift {shift_id}")


def validate_shift_parent_assignment(
    db: Session,
    *,
    shift_id: int,
    parent_shift_id: int | None,
) -> None:
    """Reject parent assignments that would break the dependency tree."""
    if parent_shift_id is None:
        return
    if shift_id == parent_shift_id:
        raise ValueError("Shift cannot be its own parent")

    current_id = parent_shift_id
    seen: set[int] = set()
    while current_id is not None:
        if current_id == shift_id:
            raise _cycle_error(shift_id)
        if current_id in seen:
            raise _cycle_error(current_id)
        seen.add(current_id)

        current = db.query(RosterShift).filter(RosterShift.id == current_id).first()
        if current is None:
            raise ValueError(f"Parent shift {current_id} not found")
        current_id = _int_id(getattr(current, "parent_shift_id", None))


def synced_booking_source_shift(db: Session, shift: RosterShift) -> RosterShift:
    """Return the source shift for writes to a synced pool.

    For a synced child, booking-link writes belong on the nearest ancestor whose
    dependency edge is still synced. Detached children remain their own source.
    """
    current = shift
    seen: set[int] = set()
    while (
        current is not None
        and _int_id(getattr(current, "parent_shift_id", None)) is not None
        and shift_pool_sync_enabled(current)
    ):
        current_id = _int_id(getattr(current, "id", None))
        parent_id = _int_id(getattr(current, "parent_shift_id", None))
        if current_id is None or parent_id is None:
            break
        if current_id in seen:
            raise _cycle_error(current_id)
        seen.add(current_id)
        parent = (
            db.query(RosterShift)
            .filter(RosterShift.id == parent_id)
            .first()
        )
        if (
            parent is None
            or not shift_pool_sync_enabled(parent)
            or getattr(parent, "dependents_independent", False) is True
        ):
            break
        current = parent
    return current


def parent_booking_ids(db: Session, parent_shift_id: int) -> set[int]:
    rows = (
        db.query(ShiftBookingLink.booking_id)
        .join(Booking, Booking.id == ShiftBookingLink.booking_id)
        .filter(
            ShiftBookingLink.shift_id == parent_shift_id,
            Booking.status != BookingStatus.CANCELLED,
        )
        .all()
    )
    return {row[0] for row in rows}


def set_shift_booking_ids(db: Session, shift_id: int, booking_ids: set[int]) -> bool:
    existing_rows = (
        db.query(ShiftBookingLink)
        .filter(ShiftBookingLink.shift_id == shift_id)
        .all()
    )
    existing = {row.booking_id for row in existing_rows}
    changed = False

    for row in existing_rows:
        if row.booking_id not in booking_ids:
            db.delete(row)
            changed = True

    for booking_id in sorted(booking_ids - existing):
        db.add(ShiftBookingLink(shift_id=shift_id, booking_id=booking_id))
        changed = True

    return changed


def sync_shift_pool_from_parent(db: Session, parent_shift_id: int) -> list[int]:
    """Sync a parent's booking set to recursive children.

    Returns child shift ids whose links were changed. The function does not
    commit; callers keep transaction ownership.
    """
    changed_shift_ids: list[int] = []
    visited: set[int] = set()

    def walk(parent_id: int) -> None:
        if parent_id in visited:
            raise _cycle_error(parent_id)
        visited.add(parent_id)

        parent = db.query(RosterShift).filter(RosterShift.id == parent_id).first()
        if (
            parent is None
            or not shift_pool_sync_enabled(parent)
            or getattr(parent, "dependents_independent", False) is True
        ):
            return

        desired = parent_booking_ids(db, parent.id)
        children = (
            db.query(RosterShift)
            .filter(RosterShift.parent_shift_id == parent.id)
            .order_by(RosterShift.id)
            .all()
        )
        for child in children:
            if not shift_pool_sync_enabled(child):
                continue
            child_id = _int_id(getattr(child, "id", None))
            if child_id is None:
                continue
            if child_id in visited:
                raise _cycle_error(child_id)
            if set_shift_booking_ids(db, child.id, desired):
                changed_shift_ids.append(child.id)
            walk(child.id)

    walk(parent_shift_id)
    return changed_shift_ids


def sync_shift_pool_for_shift(db: Session, shift_id: int) -> list[int]:
    shift = db.query(RosterShift).filter(RosterShift.id == shift_id).first()
    if shift is None:
        return []
    source = synced_booking_source_shift(db, shift)
    return sync_shift_pool_from_parent(db, source.id)
