"""
PR 5 (2026-05-29 security review): regression for the deletion of the
legacy POST /api/bookings endpoint.

What got deleted:
  - The handler at backend/main.py @app.post("/api/bookings"),
    `create_booking`, that wrote a CONFIRMED booking row directly
    via the in-memory BookingService, bypassing Stripe AND the
    capacity advisory-lock path from PR 3.
  - backend/tests/mocked/test_concurrent_booking.py, ~17 tests that
    exercised the legacy in-memory concurrency. Modern concurrency
    invariants (capacity oversell, advisory lock) are already
    covered by test_capacity_lock_hueb.py against the actual
    production flow (POST /api/payments/create-intent → Stripe →
    webhook → confirm).

Why it was an IDOR risk:
  - No auth, no draft token, no payment proof. Anyone could POST a
    body and reserve/confirm a slot without paying. Bypassed the
    PR 3 capacity-race lock AND the PR 4b customer-ownership token.

What stays:
  - BookingService.create_booking the in-memory method itself
    remains because /api/admin/bookings still routes through it.
    That's the legacy in-memory path admin tooling uses; not part
    of the customer journey. PR 5 closes only the public HTTP front
    door, not the underlying class.

This file pins the closure. A future commit that re-registers
POST /api/bookings (or the legacy GET siblings that PR 4a also
removed) would fail one of these tests loudly.
"""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from main import app


class TestPostBookingsRouteIsGone:
    """The legacy POST /api/bookings handler must not come back without
    an explicit IDOR-risk review. Pre-2026-05-29 it was the unauth
    direct-confirm bypass."""

    def test_H_post_to_bookings_path_405_or_404(self):
        # H: A POST to /api/bookings — the path may still match other
        # method handlers (e.g., the FastAPI router may share path
        # patterns with DELETE /api/bookings/{id} for prefix purposes),
        # so 404 (no route) and 405 (method not allowed on a known
        # path) are BOTH acceptable signals that the legacy endpoint
        # is gone. A 200 with a booking body would mean the IDOR
        # surface was reopened.
        client = TestClient(app)
        resp = client.post("/api/bookings", json={
            "first_name": "Mallory",
            "last_name": "Attacker",
            "email": "mallory@example.com",
            "phone": "07700900000",
            "drop_off_date": "2026-12-01",
            "drop_off_slot_type": "165",
            "flight_date": "2026-12-01",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "destination_code": "KRK",
            "destination_name": "Krakow, PL",
            "pickup_date": "2026-12-08",
            "return_flight_time": "14:30",
            "return_flight_number": "5524",
            "registration": "AB12 CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
            "package": "quick",
            "billing_address1": "123 Test St",
            "billing_city": "London",
            "billing_postcode": "SW1A 1AA",
            "billing_country": "United Kingdom",
        })
        assert resp.status_code in (404, 405), (
            f"Expected 404 (no route) or 405 (method gone); got "
            f"{resp.status_code}. If 200 — the legacy direct-confirm "
            f"bypass was re-registered. Close it again."
        )

    def test_U_post_with_minimal_body_still_405_or_404(self):
        # U: Any POST body (even malformed/empty) must not reach a
        # working handler. Confirms the closure isn't accidentally
        # relying on body validation.
        client = TestClient(app)
        resp = client.post("/api/bookings", json={})
        assert resp.status_code in (404, 405)

    def test_E_post_with_empty_body_405_or_404(self):
        # E: Empty body — same outcome.
        client = TestClient(app)
        resp = client.post("/api/bookings")
        assert resp.status_code in (404, 405)
