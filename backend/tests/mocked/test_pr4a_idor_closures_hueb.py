"""
HUEB tests for PR 4a of the 2026-05-29 security review: low-risk closures
of three public booking IDORs that did not require a customer-flow
ownership model.

Three closures:
  1. GET /api/bookings/email/{email} — DELETED (was unauth, leaked every
     booking for any submitted email).
  2. GET /api/bookings/{booking_id}  — DELETED (was unauth, dumped any
     booking by sequential id iteration).
  3. DELETE /api/bookings/{booking_id} — kept but gated with
     Depends(require_admin) (was unauth, destructive — anyone who could
     guess a booking_id could cancel a customer's reservation).

PR 4b will handle the 5 customer-flow endpoints (PATCH customer/vehicle,
POST vehicle, DVLA lookup, heard-about-us) with a real ownership token
issued at the start of the booking draft — see
[[project_pr_4b_design]] for the design constraint.

Implementation notes:
  - We mock main.get_service to a stub so the handler reaches a usable
    service without booting the real BookingService (which would call
    get_pricing_from_db and fail without the autouse pricing-patch
    fixture used in test_concurrent_booking.py).
  - We override require_admin (NOT get_current_user) because the
    cancel_booking handler depends on require_admin directly. Overriding
    the chained get_current_user dependency works too but is one
    indirection further than needed.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient

import main
from main import app, require_admin


@pytest.fixture
def fake_admin():
    """SimpleNamespace shaped like a User row with is_admin=True."""
    return SimpleNamespace(
        id=1, email="admin@tag.test", is_admin=True, is_active=True,
        first_name="Admin", last_name="Test",
    )


@pytest.fixture
def stub_service(monkeypatch):
    """Mock main.get_service so the handler doesn't touch the real
    BookingService init (which needs a pricing-db patch we don't run
    here). cancel_booking returns False by default → handler raises
    404 'Booking not found'. Tests can override the return value via
    the spy.
    """
    class _StubService:
        def __init__(self):
            self.cancel_return = False
            self.cancel_called_with = []

        def cancel_booking(self, booking_id):
            self.cancel_called_with.append(booking_id)
            return self.cancel_return

    svc = _StubService()
    monkeypatch.setattr(main, "get_service", lambda: svc)
    return svc


@pytest.fixture
def admin_override(fake_admin):
    """Install fake admin via require_admin override; clean up after."""
    app.dependency_overrides[require_admin] = lambda: fake_admin
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_admin, None)


# ============================================================================
# 1. Deleted endpoints stay deleted
# ============================================================================


class TestDeletedRoutesAreInaccessible:
    """Regression: GET /api/bookings/email/{email} and GET
    /api/bookings/{booking_id} are gone. Pins the closure so a future
    commit can't accidentally re-add either endpoint without an
    explicit test failure flagging the re-introduced IDOR.

    Status-code subtlety:
      • /api/bookings/email/{email} → 404 (route fully removed, no
        path match).
      • /api/bookings/{booking_id}  → 405 Method Not Allowed (the path
        still matches the surviving DELETE handler, just not GET).
        Both 404 and 405 prove the GET method is no longer routable;
        what matters is that 200 with a booking body is IMPOSSIBLE.
    """

    def test_H_bookings_by_email_route_is_gone(self):
        # H: GET to the old email-lookup path returns 404 with FastAPI's
        # no-route body — the route is no longer registered.
        client = TestClient(app)
        resp = client.get("/api/bookings/email/anyone@example.com")
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Not Found"}, (
            "Expected FastAPI no-route 404, got an in-handler 404 — "
            "looks like the GET /api/bookings/email/{email} route was "
            "re-added. This was a confirmed IDOR; close it again."
        )

    def test_U_bookings_by_email_url_encoded_email_also_404(self):
        # U: URL-encoded characters in the email path segment — still
        # 404 (rules out partial re-introduction with a different pattern).
        client = TestClient(app)
        resp = client.get("/api/bookings/email/test%40example.com")
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Not Found"}

    def test_E_get_booking_by_id_returns_405_not_200(self):
        # E: GET /api/bookings/{booking_id} — the path STILL matches a
        # route (the surviving DELETE), so FastAPI returns 405 Method
        # Not Allowed rather than 404. The IDOR closure is proven by
        # the absence of a 200 with booking data, not by 404 specifically.
        client = TestClient(app)
        resp = client.get("/api/bookings/some-booking-id-xyz")
        assert resp.status_code == 405, (
            f"Expected 405 (DELETE survives, GET removed); got "
            f"{resp.status_code}. If 200 — the GET handler was re-added."
        )

    def test_B_numeric_booking_id_also_405(self):
        # B: Boundary — numeric path segment (the original enumeration
        # vector) → 405 (DELETE method still matches the path; GET
        # method gone).
        client = TestClient(app)
        resp = client.get("/api/bookings/1")
        assert resp.status_code == 405


# ============================================================================
# 2. DELETE /api/bookings/{booking_id} requires admin
# ============================================================================


class TestCancelBookingRequiresAdmin:
    """H/U/E/B for the new Depends(require_admin) gate on DELETE
    /api/bookings/{booking_id}.

    Pre-2026-05-29 this was a public destructive endpoint — anyone who
    could guess or enumerate booking_id could cancel a customer's
    reservation. Closed by require_admin; Admin.jsx is the only
    legitimate caller.
    """

    def test_U_unauth_returns_401(self):
        # U: Unauthenticated DELETE — require_admin's chain begins with
        # get_current_user, which raises 401 when no Bearer token is
        # supplied. Pre-fix this returned 200 and DELETED the booking.
        client = TestClient(app)
        resp = client.delete("/api/bookings/any-id")
        assert resp.status_code == 401, (
            f"Expected 401 for unauth DELETE — got {resp.status_code}. "
            "The require_admin gate is the IDOR closure; without it any "
            "anonymous attacker can cancel any booking by guessing id."
        )

    def test_H_admin_authed_cancel_succeeds(
        self, admin_override, stub_service
    ):
        # H: With admin override + stub service returning True (booking
        # found and cancelled), the handler returns 200 with the
        # success body.
        stub_service.cancel_return = True
        client = TestClient(app)
        resp = client.delete("/api/bookings/booking-xyz-123")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["booking_id"] == "booking-xyz-123"
        # Confirm the handler did call through to the service.
        assert stub_service.cancel_called_with == ["booking-xyz-123"]

    def test_E_admin_authed_missing_booking_returns_404(
        self, admin_override, stub_service
    ):
        # E: Admin auth lets the request through. Stub returns False
        # → handler raises HTTPException(404, "Booking not found").
        # Confirms the handler's own 404 path is reachable (not blocked
        # by the auth gate), and the body matches the in-handler
        # message (not FastAPI's no-route default).
        stub_service.cancel_return = False
        client = TestClient(app)
        resp = client.delete("/api/bookings/missing-id")
        assert resp.status_code == 404
        assert resp.json().get("detail") == "Booking not found"

    def test_B_unauth_then_authed_proves_gate_is_discriminator(
        self, fake_admin, stub_service
    ):
        # B: Boundary — the SAME request URL/body returns 401 without
        # the override and 200/404 with it. Confirms the gate is the
        # active discriminator (auth, not anything else like path
        # validation or rate limiting that might give a misleading
        # green light in test_U above).
        client = TestClient(app)
        resp_no_auth = client.delete("/api/bookings/x")
        assert resp_no_auth.status_code == 401

        # Install admin override locally for this assertion only.
        app.dependency_overrides[require_admin] = lambda: fake_admin
        try:
            stub_service.cancel_return = True
            resp_authed = client.delete("/api/bookings/x")
        finally:
            app.dependency_overrides.pop(require_admin, None)

        assert resp_authed.status_code == 200, (
            "Admin override should bypass the auth gate. Got "
            f"{resp_authed.status_code} — the override target may not "
            "match the actual dependency."
        )
