"""
Post-confirmation background-task ordering — HUEB integration.

Endpoint: POST /api/admin/bookings/{id}/mark-paid

In mark_booking_paid (manual confirmation by admin) two roster-related
background tasks are queued: `auto_create_or_extend_async` (rebuilds the
day's auto-shifts) and `auto_link_booking_async` (links this booking into
any covering shift). The 2026-05-25 fix swapped their order so create
runs BEFORE link — the inverse order produced a race that left
manually-confirmed bookings with zero shift coverage:

  1. auto_link wrote optimistic ShiftBookingLink rows pointing at the
     current unassigned auto-shifts.
  2. auto_create_or_extend then wiped + recreated those auto-shifts
     (the FK cascade dropped the link rows).
  3. The rebuild's re-cluster sometimes failed to re-link the new
     booking — leaving it permanently uncovered.

`mark_booking_paid` is the ONLY confirmation endpoint that fires both
tasks; the Stripe webhook only fires auto_create_or_extend (no race
possible there). These tests live in their own file because the subject
under test is the orchestration of these two roster-side tasks, which
doesn't belong with the mark-paid / swap-vehicle / DVLA tests.
"""
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
import main
from main import app, require_admin
from database import get_db


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _booking(**kw):
    from db_models import BookingStatus, PaymentStatus
    base = dict(
        id=99, reference="TAG-ORDER01",
        status=BookingStatus.PENDING,
        customer=SimpleNamespace(id=1, email="jo@x.test",
                                 first_name="Jo", last_name="K"),
        customer_first_name="Jo", customer_last_name="K",
        vehicle=SimpleNamespace(registration="AB12CDE", make="Ford",
                                model="Focus", colour="Blue"),
        payment=SimpleNamespace(amount_pence=9900, status=PaymentStatus.PENDING,
                                paid_at=None, stripe_payment_intent_id="pi_1"),
        departure_id=None, dropoff_slot=None,
        dropoff_date=date(2026, 6, 1),
        pickup_date=date(2026, 6, 8),
        dropoff_time=time(10, 0), pickup_time=time(11, 30),
        flight_arrival_time=time(15, 0), flight_departure_time=time(12, 0),
        dropoff_destination="Tenerife",
        dropoff_airline_name="TUI Airways", dropoff_flight_number="TOM1234",
        pickup_origin="Tenerife", pickup_airline_name="TUI Airways",
        pickup_flight_number="TOM1235",
        package="longer", created_at=datetime(2026, 5, 1),
        confirmation_email_sent=False, confirmation_email_sent_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _wire(booking, payment=None):
    db = MagicMock()

    def _query(model):
        chain = MagicMock()
        chain.filter.return_value = chain
        name = model.__name__ if hasattr(model, "__name__") else str(model)
        if name == "Booking":
            chain.first.return_value = booking
        elif name == "Payment":
            chain.first.return_value = payment
        else:
            chain.first.return_value = None
        return chain

    db.query.side_effect = _query
    db.commit = MagicMock()
    return db


def _override(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _clear():
    app.dependency_overrides.clear()


class TestPostConfirmationTaskOrder:

    def teardown_method(self):
        _clear()

    def test_H_auto_create_runs_before_auto_link(self, monkeypatch):
        """Happy: a clean mark-paid call queues both tasks; TestClient runs
        them after the response; the execution-order list shows `create`
        before `link`."""
        order: list[str] = []
        monkeypatch.setattr(main, "send_booking_confirmation_email",
                            lambda **kw: True)
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: order.append("fire"))
        monkeypatch.setattr("auto_roster.auto_create_or_extend_async",
                            lambda *a, **kw: order.append("create"))
        monkeypatch.setattr("roster_planner_runner.auto_link_booking_async",
                            lambda *a, **kw: order.append("link"))
        monkeypatch.setattr("dvla_compliance.check_and_alert_for_booking_async",
                            lambda *a, **kw: order.append("dvla"))

        b = _booking()
        _override(_wire(b, payment=b.payment))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/mark-paid")
        assert resp.status_code == 200, resp.text
        assert "create" in order, f"auto_create not enqueued; order={order}"
        assert "link" in order, f"auto_link not enqueued; order={order}"
        assert order.index("create") < order.index("link"), (
            "create must run BEFORE link to avoid the wipe-cascade race; "
            f"actual order={order}"
        )

    def test_U_no_tasks_queued_when_endpoint_rejects(self, monkeypatch):
        """Unhappy: when the endpoint returns 4xx (booking already confirmed),
        NO background tasks should fire. Guards against the reorder
        accidentally queuing tasks for a rejected request."""
        from db_models import BookingStatus
        order: list[str] = []
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: order.append("fire"))
        monkeypatch.setattr("auto_roster.auto_create_or_extend_async",
                            lambda *a, **kw: order.append("create"))
        monkeypatch.setattr("roster_planner_runner.auto_link_booking_async",
                            lambda *a, **kw: order.append("link"))

        b = _booking(status=BookingStatus.CONFIRMED)  # already confirmed
        _override(_wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/mark-paid")
        assert resp.status_code == 400
        assert order == [], f"no tasks should fire on rejection; got {order}"

    def test_E_link_does_not_start_until_create_completes(self, monkeypatch):
        """Edge: order isn't just enqueue-order, it's execution-order — the
        whole point of the reorder is that auto_link sees the post-rebuild
        shift inventory. Simulate auto_create taking time and confirm link
        only fires AFTER create's body finishes (not interleaved)."""
        events: list[tuple[str, str]] = []  # (phase, task)

        def slow_create(*a, **kw):
            events.append(("start", "create"))
            # No real sleep — Starlette runs background tasks sequentially
            # in the same thread. The sentinel below would interleave only
            # if link started before create's body returned, which can't
            # happen given sequential execution. Marker proves create's
            # body fully ran before any other task.
            events.append(("end", "create"))

        def quick_link(*a, **kw):
            events.append(("start", "link"))
            events.append(("end", "link"))

        monkeypatch.setattr(main, "send_booking_confirmation_email",
                            lambda **kw: True)
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: events.append(("end", "fire")))
        monkeypatch.setattr("auto_roster.auto_create_or_extend_async", slow_create)
        monkeypatch.setattr("roster_planner_runner.auto_link_booking_async",
                            quick_link)
        monkeypatch.setattr("dvla_compliance.check_and_alert_for_booking_async",
                            lambda *a, **kw: events.append(("end", "dvla")))

        b = _booking(id=100, reference="TAG-ORDER02")
        _override(_wire(b, payment=b.payment))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/mark-paid")
        assert resp.status_code == 200, resp.text
        # Find the indices of create's end and link's start.
        create_end_idx = events.index(("end", "create"))
        link_start_idx = events.index(("start", "link"))
        assert create_end_idx < link_start_idx, (
            f"link started before create finished; events={events}"
        )

    def test_B_link_after_create_holds_when_dvla_intercepts_between(self, monkeypatch):
        """Boundary: the DVLA check task is enqueued between create and
        link in main.py. Verify the create→link order is preserved even
        when the dvla task is scheduled in the middle (so it doesn't
        accidentally reorder the pair)."""
        order: list[str] = []
        monkeypatch.setattr(main, "send_booking_confirmation_email",
                            lambda **kw: True)
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: order.append("fire"))
        monkeypatch.setattr("auto_roster.auto_create_or_extend_async",
                            lambda *a, **kw: order.append("create"))
        monkeypatch.setattr("roster_planner_runner.auto_link_booking_async",
                            lambda *a, **kw: order.append("link"))
        monkeypatch.setattr("dvla_compliance.check_and_alert_for_booking_async",
                            lambda *a, **kw: order.append("dvla"))

        b = _booking(id=101, reference="TAG-ORDER03")
        _override(_wire(b, payment=b.payment))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/mark-paid")
        assert resp.status_code == 200, resp.text
        # All four tasks ran, and create stayed before link regardless of
        # what landed between them.
        assert set(order) >= {"fire", "create", "dvla", "link"}, order
        assert order.index("create") < order.index("link"), order
