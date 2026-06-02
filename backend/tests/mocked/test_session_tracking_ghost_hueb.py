"""
HUEB tests pinning the two-part fix for funnel double-counting caused by
"ghost" BOOKING_CONFIRMED audit rows.

Background:
  When a customer pays via a Stripe Payment Link that an admin created
  outside the app (manual-booking flow), the payment_intent_id isn't tied
  to a Payment row in our DB. The Stripe webhook still wrote PAYMENT_SUCCEEDED
  and BOOKING_CONFIRMED audit rows for those events, but with
  booking_reference=None and session_id=None — "ghost" rows. The Session
  Tracking funnel deduplicated by session_id/booking_reference/anon_<id>,
  so each ghost counted as its own unique session and inflated
  booking_confirmed. The same booking was already counted by the separate
  Manual column, producing a double-count (e.g. 2026-05-22 showed
  booking_confirmed=10 = 8 online + 2 manual ghosts).

Fixes pinned here:
  A) Stripe webhook (POST /api/webhooks/stripe): skip the two log_audit_event
     calls when `payment is None` (manual-booking-payment-link case).
  B) GET /api/admin/reports/session-tracking: drop BOOKING_CONFIRMED audit
     rows where booking_reference is None on read, so the 23 historical
     ghosts already in the DB stop double-counting on past days.
"""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import get_db
from db_models import AuditLog, AuditLogEvent, BookingStatus, PaymentStatus


# ============================================================================
# Fix A — webhook guard
# ============================================================================

def _stripe_obj(**fields):
    obj = MagicMock()
    for k, v in fields.items():
        setattr(obj, k, v)
    obj.__getitem__.side_effect = lambda k: fields.get(k)
    obj.__contains__.side_effect = lambda k: k in fields
    return obj


def _event(event_type, data_object):
    return {"type": event_type, "data": {"object": data_object}}


def _override_db(db):
    def _gen():
        yield db
    app.dependency_overrides[get_db] = _gen


def _post_webhook():
    return TestClient(app).post(
        "/api/webhooks/stripe",
        content=b"{}",
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": "t=1,v1=fake",
        },
    )


def _mock_payment(booking_id=1, intent_id="pi_HUEB_001"):
    p = MagicMock()
    p.id = 1
    p.booking_id = booking_id
    p.stripe_payment_intent_id = intent_id
    p.status = PaymentStatus.SUCCEEDED
    p.refund_amount_pence = None
    return p


def _wire_db(payment=None, booking=None):
    """Route db.query(Model) by model name so the webhook's canonical
    booking_reference lookup (db.query(Booking).filter(id==...)) can
    return a different row than the Payment lookup."""
    db = MagicMock()
    def _query(model):
        chain = MagicMock()
        name = getattr(model, "__name__", "")
        if name == "Booking":
            chain.filter.return_value.first.return_value = booking
        else:
            # Payment, anything else used inside webhook helpers
            chain.filter.return_value.first.return_value = payment
        chain.filter.return_value.all.return_value = []
        return chain
    db.query.side_effect = _query
    db.commit = MagicMock()
    return db


def _mock_booking(booking_id=42, reference="TAG-CANON001"):
    b = MagicMock()
    b.id = booking_id
    b.reference = reference
    return b


class TestStripeWebhookGhostAuditGuard:
    """Fix A: webhook only writes PAYMENT_SUCCEEDED + BOOKING_CONFIRMED
    audit rows when the payment_intent resolves to a Payment row in our DB."""

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    @patch("main.log_audit_event")
    def test_U_no_ghost_audit_rows_when_payment_not_in_db(
        self, mock_audit, mock_update, mock_verify, mock_cfg
    ):
        """Unhappy: webhook for a manual-booking Payment Link (admin
        created it in Stripe Dashboard, app has no Payment row) must NOT
        write ghost PAYMENT_SUCCEEDED / BOOKING_CONFIRMED audit rows.

        This is the root cause of the 23 ghost rows currently in prod
        that double-count manual bookings against the Manual column."""
        mock_update.return_value = (None, False)  # payment not found
        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(id="pi_manual_link_001", metadata={}),
        )
        _override_db(_wire_db(payment=None))

        resp = _post_webhook()
        assert resp.status_code == 200

        audit_events = [
            call.kwargs.get("event") for call in mock_audit.call_args_list
        ]
        assert AuditLogEvent.PAYMENT_SUCCEEDED not in audit_events, (
            "Webhook wrote a ghost PAYMENT_SUCCEEDED audit row for a payment "
            "that isn't tied to a Payment row in our DB"
        )
        assert AuditLogEvent.BOOKING_CONFIRMED not in audit_events, (
            "Webhook wrote a ghost BOOKING_CONFIRMED audit row for a payment "
            "that isn't tied to a Payment row in our DB"
        )

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    @patch("main.log_audit_event")
    def test_H_audit_rows_written_when_payment_resolves(
        self, mock_audit, mock_update, mock_verify, mock_cfg
    ):
        """Happy: real online booking. payment_intent resolves to a
        Payment row, so both audit events MUST still be written AND must
        carry the canonical booking_reference (so the funnel filter
        doesn't accidentally drop them as ghosts).

        Regression fence for Fix A + Issue 1: over-tightening the guard
        would silently drop legitimate online funnel events; leaving
        booking_reference riding on metadata would cause the same drop
        whenever metadata is missing/stale."""
        payment = _mock_payment(intent_id="pi_HUEB_002", booking_id=42)
        canonical_booking = _mock_booking(booking_id=42, reference="TAG-HUEB002")
        mock_update.return_value = (payment, False)
        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(
                id="pi_HUEB_002",
                metadata={"booking_reference": "TAG-HUEB002"},
            ),
        )
        _override_db(_wire_db(payment=payment, booking=canonical_booking))

        resp = _post_webhook()
        assert resp.status_code == 200

        events_by_type = {
            call.kwargs.get("event"): call.kwargs.get("booking_reference")
            for call in mock_audit.call_args_list
        }
        assert AuditLogEvent.PAYMENT_SUCCEEDED in events_by_type
        assert AuditLogEvent.BOOKING_CONFIRMED in events_by_type
        # Pin: ref MUST be the canonical Booking.reference, not None.
        assert events_by_type[AuditLogEvent.PAYMENT_SUCCEEDED] == "TAG-HUEB002"
        assert events_by_type[AuditLogEvent.BOOKING_CONFIRMED] == "TAG-HUEB002"

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    @patch("main.log_audit_event")
    def test_H_stale_metadata_falls_back_to_canonical_ref(
        self, mock_audit, mock_update, mock_verify, mock_cfg
    ):
        """Happy with stale metadata: payment_intent resolves to a real
        Payment row, but Stripe metadata.booking_reference is missing.
        update_payment_status confirms via PaymentIntent ID anyway (see
        top-of-handler comment in main.py). Without Issue 1's canonical
        lookup, audit rows would have booking_reference=None and Fix B's
        filter would then drop these legitimate confirmations from the
        funnel — exactly the over-tightening risk the QA agent called out."""
        payment = _mock_payment(intent_id="pi_HUEB_004", booking_id=99)
        canonical_booking = _mock_booking(booking_id=99, reference="TAG-CANON99")
        mock_update.return_value = (payment, False)
        # Metadata is empty — booking_reference would resolve to None
        # without the canonical fallback.
        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(id="pi_HUEB_004", metadata={}),
        )
        _override_db(_wire_db(payment=payment, booking=canonical_booking))

        resp = _post_webhook()
        assert resp.status_code == 200

        events_by_type = {
            call.kwargs.get("event"): call.kwargs.get("booking_reference")
            for call in mock_audit.call_args_list
        }
        assert events_by_type.get(AuditLogEvent.BOOKING_CONFIRMED) == "TAG-CANON99", (
            "Audit row used metadata's None instead of the canonical "
            "Booking.reference — funnel filter will drop this real "
            "confirmation as a ghost."
        )
        assert events_by_type.get(AuditLogEvent.PAYMENT_SUCCEEDED) == "TAG-CANON99"

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    @patch("main.log_audit_event")
    def test_E_payment_lookup_raises_skips_audit(
        self, mock_audit, mock_update, mock_verify, mock_cfg
    ):
        """Edge: if update_payment_status itself raises (DB hiccup), the
        outer try/except logs an error but `payment` stays None. Guard
        must still hold — we never reach the audit block with a fabricated
        confirmation."""
        mock_update.side_effect = RuntimeError("db down")
        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(id="pi_HUEB_003", metadata={}),
        )
        _override_db(_wire_db(payment=None))

        resp = _post_webhook()
        assert resp.status_code == 200

        audit_events = [
            call.kwargs.get("event") for call in mock_audit.call_args_list
        ]
        assert AuditLogEvent.PAYMENT_SUCCEEDED not in audit_events
        assert AuditLogEvent.BOOKING_CONFIRMED not in audit_events


# ============================================================================
# Fix B — session-tracking funnel filter
# ============================================================================

def _audit_row(event, *, ref=None, session_id=None, when=None, row_id=1):
    """Build a fake AuditLog row sufficient for the endpoint's read path."""
    return SimpleNamespace(
        id=row_id,
        event=event,
        booking_reference=ref,
        session_id=session_id,
        created_at=when or datetime.now(timezone.utc),
    )


class _RoutingDB:
    """Routes db.query(Model) to per-model row lists, so we can return
    crafted AuditLog rows without disturbing the separate Manual/free
    Booking queries (which we set to empty)."""
    def __init__(self, audit_rows):
        self._audit_rows = audit_rows

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "AuditLog":
            return _Chain(self._audit_rows)
        # Booking queries (manual + free counts) — return empty for these tests
        return _Chain([])


class _Chain:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *a, **kw):
        return self

    def join(self, *a, **kw):
        return self

    def order_by(self, *a, **kw):
        return self

    def all(self):
        return self._rows


@pytest.fixture
def _admin_client():
    """TestClient with admin auth stubbed.

    Also resets the module-global _session_tracking_cache before each test
    so cached responses from a prior test don't bleed into this one (and
    so the cached payload we leave behind doesn't break subsequent files
    like test_session_tracking_integration.py::test_empty_audit_logs)."""
    import main as main_mod
    from main import require_admin

    def _admin():
        u = MagicMock()
        u.id = 1
        u.email = "admin@tag-parking.co.uk"
        u.role = "admin"
        return u

    main_mod._session_tracking_cache = {"data": None, "cached_at": None}
    app.dependency_overrides[require_admin] = _admin
    yield TestClient(app)
    app.dependency_overrides.clear()
    main_mod._session_tracking_cache = {"data": None, "cached_at": None}


class TestSessionTrackingGhostFilter:
    """Fix B: ghost BOOKING_CONFIRMED rows (booking_reference=None) are
    excluded from the funnel on read, but everything else is kept."""

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_U_ghost_booking_confirmed_excluded_from_funnel(self, _admin_client):
        """Unhappy: two ghost BOOKING_CONFIRMED rows + two real ones must
        report booking_confirmed=2, not 4."""
        when = datetime.now(timezone.utc) - timedelta(hours=1)
        rows = [
            _audit_row(AuditLogEvent.BOOKING_CONFIRMED, ref="TAG-REAL001",
                       session_id=None, when=when, row_id=1),
            _audit_row(AuditLogEvent.BOOKING_CONFIRMED, ref="TAG-REAL002",
                       session_id=None, when=when, row_id=2),
            # Ghosts — Stripe webhook for manual-payment-link bookings
            _audit_row(AuditLogEvent.BOOKING_CONFIRMED, ref=None,
                       session_id=None, when=when, row_id=3),
            _audit_row(AuditLogEvent.BOOKING_CONFIRMED, ref=None,
                       session_id=None, when=when, row_id=4),
        ]
        _override_db(_RoutingDB(rows))

        resp = _admin_client.get(
            "/api/admin/reports/session-tracking?period=daily&refresh=true"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["cumulative"]["counts"]["booking_confirmed"] == 2

    def test_H_real_booking_confirmed_with_ref_is_counted(self, _admin_client):
        """Happy: a normal online BOOKING_CONFIRMED row (ref set) is
        counted — guarantees the filter doesn't over-reach."""
        when = datetime.now(timezone.utc) - timedelta(hours=1)
        rows = [
            _audit_row(AuditLogEvent.BOOKING_CONFIRMED, ref="TAG-ONL0001",
                       session_id="sess_abc", when=when, row_id=1),
        ]
        _override_db(_RoutingDB(rows))

        resp = _admin_client.get(
            "/api/admin/reports/session-tracking?period=daily&refresh=true"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["cumulative"]["counts"]["booking_confirmed"] == 1

    def test_E_non_booking_confirmed_events_with_no_ref_are_kept(self, _admin_client):
        """Edge: upstream funnel events (DATES_SELECTED, FLIGHT_SELECTED,
        CUSTOMER_ENTERED, PAYMENT_INITIATED) legitimately have no
        booking_reference — the booking doesn't exist yet. Filter must
        NOT drop them, only BOOKING_CONFIRMED ghosts."""
        when = datetime.now(timezone.utc) - timedelta(hours=1)
        rows = [
            _audit_row(AuditLogEvent.DATES_SELECTED, ref=None,
                       session_id="sess_1", when=when, row_id=10),
            _audit_row(AuditLogEvent.FLIGHT_SELECTED, ref=None,
                       session_id="sess_1", when=when, row_id=11),
            _audit_row(AuditLogEvent.CUSTOMER_ENTERED, ref=None,
                       session_id="sess_1", when=when, row_id=12),
            _audit_row(AuditLogEvent.PAYMENT_INITIATED, ref=None,
                       session_id="sess_1", when=when, row_id=13),
        ]
        _override_db(_RoutingDB(rows))

        resp = _admin_client.get(
            "/api/admin/reports/session-tracking?period=daily&refresh=true"
        )
        assert resp.status_code == 200, resp.text
        counts = resp.json()["cumulative"]["counts"]
        assert counts["dates_selected"] == 1
        assert counts["flight_selected"] == 1
        assert counts["customer_entered"] == 1
        assert counts["payment_initiated"] == 1
        assert counts["booking_confirmed"] == 0

    def test_B_mixed_ghosts_and_reals_match_screenshot_scenario(self, _admin_client):
        """Boundary: reproduces the 2026-05-22 prod shape — 8 online
        confirmations (ref set) + 2 webhook ghosts (ref None) — and pins
        booking_confirmed=8 after the filter, instead of the buggy 10.
        Plus 17 dates_selected sessions upstream so the conversion-rate
        codepath also runs without underflow."""
        when = datetime.now(timezone.utc) - timedelta(hours=2)
        rows = []
        rows += [
            _audit_row(AuditLogEvent.DATES_SELECTED, ref=None,
                       session_id=f"sess_d{i}", when=when, row_id=100 + i)
            for i in range(17)
        ]
        rows += [
            _audit_row(AuditLogEvent.BOOKING_CONFIRMED,
                       ref=f"TAG-ONLINE{i:03d}",
                       session_id=None, when=when, row_id=200 + i)
            for i in range(8)
        ]
        rows += [
            _audit_row(AuditLogEvent.BOOKING_CONFIRMED, ref=None,
                       session_id=None, when=when, row_id=300),
            _audit_row(AuditLogEvent.BOOKING_CONFIRMED, ref=None,
                       session_id=None, when=when, row_id=301),
        ]
        _override_db(_RoutingDB(rows))

        resp = _admin_client.get(
            "/api/admin/reports/session-tracking?period=daily&refresh=true"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["cumulative"]["counts"]["booking_confirmed"] == 8
        assert body["cumulative"]["counts"]["dates_selected"] == 17
