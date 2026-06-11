"""Focused HUEB coverage for high-value branches in ``main.py``.

These tests avoid live services and drive endpoints directly with tiny DB
stubs. The goal is to keep the large ``main.py`` module covered where previous
scheduled runs showed sizeable missed blocks.
"""
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open

import pytest
from fastapi import BackgroundTasks
from fastapi.responses import StreamingResponse
from starlette.requests import Request
import sys

import main
from db_models import AuditLogEvent, BookingStatus, PaymentStatus, SMSDirection, SMSStatus


class QueryStub:
    def __init__(self, rows=None, first=None, count_value=None, update_value=None, delete_value=None):
        self.rows = list(rows or [])
        self._first = first
        self._count_value = count_value
        self._update_value = update_value
        self._delete_value = delete_value

    def filter(self, *_, **__):
        return self

    def join(self, *_, **__):
        return self

    def options(self, *_, **__):
        return self

    def order_by(self, *_, **__):
        return self

    def distinct(self, *_, **__):
        return self

    def group_by(self, *_, **__):
        return self

    def limit(self, *_, **__):
        return self

    def offset(self, *_, **__):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        if self._first is not None:
            return self._first
        return self.rows[0] if self.rows else None

    def count(self):
        if self._count_value is not None:
            return self._count_value
        return len(self.rows)

    def update(self, *_, **__):
        if self._update_value is not None:
            return self._update_value
        return len(self.rows)

    def delete(self, *_, **__):
        if self._delete_value is not None:
            return self._delete_value
        return len(self.rows)


def _db_from_sequence(items):
    db = MagicMock()
    queue = [QueryStub(rows=item) for item in items]
    def _query(model, *_, **__):
        name = getattr(model, "__name__", "")
        if name == "ParkingCapacitySetting":
            return QueryStub()
        return queue.pop(0) if queue else QueryStub()
    db.query.side_effect = _query
    return db


def _user():
    return SimpleNamespace(id=1, email="admin@tag.test", role="admin")


def _request(overrides=None):
    payload = {
        "first_name": "Jo",
        "last_name": "Coverage",
        "email": "jo.coverage@tag.test",
        "phone": "07700900000",
        "billing_address1": "1 Test Street",
        "billing_city": "Bournemouth",
        "billing_postcode": "BH1 1AA",
        "package": "longer",
        "flight_number": "BY123",
        "flight_date": "2026-08-15",
        "drop_off_date": "2026-08-15",
        "pickup_date": "2026-08-22",
        "drop_off_time": "10:00",
        "flight_departure_time": "13:00",
        "flight_arrival_time": "14:30",
        "pickup_flight_number": "EZY456",
        "pickup_origin": "Malaga, ES",
        "registration": "AB12CDE",
        "make": "Tesla",
        "model": "Model 3",
        "colour": "Blue",
    }
    payload.update(overrides or {})
    return main.CreatePaymentRequest(**payload)


def _http_request():
    return Request({"type": "http", "method": "POST", "path": "/api/payments/create-intent", "headers": []})


class PaymentDb:
    def __init__(self, *, promo_code=None, promotion=None, booking=None, vehicle=None, departure=None, arrival=None):
        self.promo_code = promo_code
        self.promotion = promotion
        self.booking = booking
        self.vehicle = vehicle
        self.departure = departure
        self.arrival = arrival
        self.commit = MagicMock()
        self.refresh = MagicMock()
        self.delete = MagicMock()

    def query(self, model, *_, **__):
        name = getattr(model, "__name__", "")
        if name == "PromoCode":
            return QueryStub(first=self.promo_code)
        if name == "Promotion":
            return QueryStub(first=self.promotion)
        if name == "Booking":
            return QueryStub(first=self.booking)
        if name == "Vehicle":
            return QueryStub(first=self.vehicle)
        if name == "FlightDeparture":
            return QueryStub(first=self.departure)
        if name == "FlightArrival":
            return QueryStub(first=self.arrival)
        return QueryStub()


class DummyWebhookRequest:
    async def body(self):
        return b"{}"


class AttrDict(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


@pytest.mark.asyncio
class TestAdminFlightReferenceCoverage:
    def setup_method(self):
        main._flight_departures_cache = {"data": None, "cached_at": None}
        main._flight_arrivals_cache = {"data": None, "cached_at": None}
        main._flight_filters_cache = {"data": None, "cached_at": None}

    async def test_H_departures_formats_rows_and_cache_hit(self):
        dep = SimpleNamespace(
            id=10,
            date=date(2026, 7, 1),
            flight_number="BY123",
            airline_code="BY",
            airline_name="TUI",
            departure_time=time(13, 45),
            destination_code="PMI",
            destination_name="Palma, ES",
            capacity_tier=2,
            slots_booked_early=1,
            slots_booked_late=2,
            max_slots_per_time=4,
            early_slots_available=3,
            late_slots_available=2,
            updated_at=datetime(2026, 6, 1, 9, 0),
            updated_by="admin@tag.test",
        )
        db = _db_from_sequence([[dep]])

        result = await main.get_admin_departures(
            sort_order="asc",
            destination=None,
            airline=None,
            flight_number=None,
            month=None,
            year=None,
            start_date=None,
            refresh=False,
            db=db,
            current_user=_user(),
        )
        assert result["total"] == 1
        assert result["departures"][0]["departure_time"] == "13:45"
        assert result["cached"] is False

        cached = await main.get_admin_departures(
            sort_order="asc",
            destination=None,
            airline=None,
            flight_number=None,
            month=None,
            year=None,
            start_date=None,
            refresh=False,
            db=_db_from_sequence([[]]),
            current_user=_user(),
        )
        assert cached["cached"] is True
        assert cached["departures"][0]["flight_number"] == "BY123"

    async def test_H_arrivals_with_filters_and_export(self):
        arr = SimpleNamespace(
            id=11,
            date=date(2026, 7, 8),
            flight_number="EZY42",
            airline_code="EZY",
            airline_name="easyJet",
            departure_time=time(10, 0),
            arrival_time=time(12, 15),
            origin_code="AGP",
            origin_name="Malaga, ES",
            created_at=datetime(2026, 5, 1, 8, 0),
            updated_at=datetime(2026, 6, 1, 9, 0),
            updated_by="admin@tag.test",
        )
        db = _db_from_sequence([[arr]])

        result = await main.get_admin_arrivals(
            sort_order="desc",
            origin="Malaga",
            airline="easy",
            flight_number="EZY",
            month=7,
            year=2026,
            start_date=date(2026, 7, 1),
            refresh=True,
            db=db,
            current_user=_user(),
        )
        assert result["total"] == 1
        assert result["arrivals"][0]["arrival_time"] == "12:15"

        exported = await main.export_admin_flights(
            flight_type="arrivals",
            db=_db_from_sequence([[arr]]),
            current_user=_user(),
        )
        assert exported["exported_by"] == "admin@tag.test"
        assert exported["arrivals"][0]["origin_code"] == "AGP"
        assert "departures" not in exported

    async def test_H_filters_combines_and_caches_reference_data(self):
        db = _db_from_sequence([
            [("BY", "TUI")],
            [("EZY", "easyJet"), ("BY", "TUI")],
            [("PMI", "Palma"), ("AGP", "Malaga")],
            [("IBZ", "Ibiza")],
            [(7, 2026)],
            [(8, 2026)],
        ])

        result = await main.get_admin_flight_filters(refresh=True, db=db, current_user=_user())
        assert result["airlines"] == [
            {"code": "BY", "name": "TUI"},
            {"code": "EZY", "name": "easyJet"},
        ]
        assert result["months"] == [
            {"year": 2026, "month": 7, "label": "Jul 2026"},
            {"year": 2026, "month": 8, "label": "Aug 2026"},
        ]

        cached = await main.get_admin_flight_filters(
            refresh=False,
            db=_db_from_sequence([]),
            current_user=_user(),
        )
        assert cached["cached"] is True


@pytest.mark.asyncio
class TestAdminAnalyticsUtilityCoverage:
    async def test_H_abandoned_carts_aggregates_destinations_days_and_recent(self):
        now = datetime.utcnow()
        selected = SimpleNamespace(
            session_id="sess-1",
            created_at=now - timedelta(days=1),
            event=AuditLogEvent.FLIGHT_SELECTED,
            event_data={
                "dropoff_date": "2026-07-01",
                "pickup_date": "2026-07-08",
                "departure_time": "13:45",
                "arrival_time": "12:15",
                "departure_destination": "Palma",
                "departure_airline": "TUI",
            },
        )
        completed = SimpleNamespace(
            session_id="sess-2",
            created_at=now - timedelta(days=2),
            event=AuditLogEvent.DATES_SELECTED,
            event_data='{"dropoff_date":"2026-07-01","pickup_date":"2026-07-04","departure_destination":"Ibiza"}',
        )
        db = _db_from_sequence([[selected, completed], [("sess-2",)]])

        result = await main.get_abandoned_carts_report(
            period="weekly",
            refresh=True,
            db=db,
            current_user=_user(),
        )

        assert result["period_type"] == "weekly"
        assert result["cumulative"]["total_abandoned"] == 1
        assert result["cumulative"]["top_destinations"] == [{"destination": "Palma", "count": 1}]
        assert result["cumulative"]["top_days"] == [{"days": 7, "count": 1}]
        assert result["recent_abandoned"][0]["session_id"] == "sess-1"

    async def test_H_fix_customer_names_reports_and_persists_changes(self):
        customer = SimpleNamespace(id=1, first_name="jANE", last_name="DOE")
        booking = SimpleNamespace(
            reference="TAG-ABC123",
            customer_first_name="mARK",
            customer_last_name="o'neill",
        )
        subscriber = SimpleNamespace(id=2, first_name="ALICE", last_name="mCdonald")
        db = _db_from_sequence([[customer], [booking], [subscriber]])

        result = await main.fix_customer_names_endpoint(
            dry_run=False,
            db=db,
            current_user=_user(),
        )

        assert result["customers_fixed"] == 1
        assert result["bookings_fixed"] == 1
        assert result["subscribers_fixed"] == 1
        assert customer.first_name == "Jane"
        assert booking.customer_first_name == "Mark"
        assert subscriber.first_name == "Alice"
        db.commit.assert_called_once()


@pytest.mark.asyncio
class TestFinancialReportAdditionalCoverage:
    async def test_H_financial_report_uses_all_promo_sources_and_override_flags(self):
        today = main.get_uk_now().date()
        yesterday = today - timedelta(days=1)
        paid_today = datetime.combine(today, time(12, 0))
        paid_yesterday = datetime.combine(yesterday, time(12, 0))

        bookings = [
            SimpleNamespace(
                id=1,
                reference="TAG-NEWPROMO",
                status=BookingStatus.CONFIRMED,
                dropoff_date=today,
                pickup_date=today + timedelta(days=7),
                customer=SimpleNamespace(first_name="Jo", last_name="New"),
                payment=SimpleNamespace(
                    paid_at=paid_today,
                    amount_pence=9000,
                    refund_amount_pence=0,
                    status=PaymentStatus.SUCCEEDED,
                ),
                override_gross_pence=None,
                override_discount_pence=None,
            ),
            SimpleNamespace(
                id=2,
                reference="TAG-FREE",
                status=BookingStatus.REFUNDED,
                dropoff_date=yesterday,
                pickup_date=yesterday + timedelta(days=3),
                customer=SimpleNamespace(first_name="Free", last_name="Guest"),
                payment=SimpleNamespace(
                    paid_at=paid_yesterday,
                    amount_pence=0,
                    refund_amount_pence=0,
                    status=PaymentStatus.SUCCEEDED,
                ),
                override_gross_pence=None,
                override_discount_pence=None,
            ),
        ]
        promo = SimpleNamespace(
            booking_id=1,
            code="SAVE10",
            promotion=SimpleNamespace(discount_percent=10),
        )
        free_sub = SimpleNamespace(
            promo_free_used_booking_id=2,
            promo_free_code="FREEWEEK",
        )
        db = _db_from_sequence([
            bookings,
            [promo],
            [],
            [free_sub],
            [],
            [],
            [],
        ])

        result = await main.get_financial_report(
            from_date=None,
            to_date=None,
            status_filter="all",
            promo_filter="all",
            refresh=True,
            db=db,
            current_user=_user(),
        )

        assert result["summary"]["totalBookings"] == 2
        rows = [row for month in result["monthlyData"] for row in month["bookings"]]
        by_ref = {row["reference"]: row for row in rows}
        assert by_ref["TAG-NEWPROMO"]["promoCode"] == "SAVE10"
        assert by_ref["TAG-FREE"]["needsOverride"] is True
        assert result["funFacts"]["revenueToday"]["amount"].startswith("£")


@pytest.mark.asyncio
class TestCreatePaymentAdditionalBranches:
    def setup_method(self):
        self.patches = []

    def _patch_common(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        monkeypatch.setattr(
            main,
            "get_settings",
            lambda: SimpleNamespace(stripe_publishable_key="pk_test_coverage"),
        )
        monkeypatch.setattr(main.log_audit_event, "__call__", lambda *a, **kw: None, raising=False)
        monkeypatch.setattr(main, "log_audit_event", lambda *a, **kw: None)
        monkeypatch.setattr(main, "log_error", lambda *a, **kw: None)
        monkeypatch.setattr(main.db_service, "find_overcapacity_day_in_stay", lambda *a, **kw: None)

    async def test_H_reuses_existing_payment_intent_when_promo_unchanged(self, monkeypatch):
        self._patch_common(monkeypatch)
        payment = SimpleNamespace(stripe_payment_intent_id="pi_existing", amount_pence=12000)
        existing = SimpleNamespace(id=44, reference="TAG-EXIST44", payment=payment)
        monkeypatch.setattr(main.db_service, "get_pending_booking_by_session", lambda *a, **kw: existing)
        intent = SimpleNamespace(
            id="pi_existing",
            client_secret="secret_existing",
            amount=12000,
            status="requires_payment_method",
            metadata=SimpleNamespace(promo_code=""),
        )
        monkeypatch.setattr(main.stripe.PaymentIntent, "retrieve", lambda *_: intent)

        response = await main.create_payment(
            _request({"session_id": "sess-reuse"}),
            _http_request(),
            BackgroundTasks(),
            PaymentDb(),
        )

        assert response.payment_intent_id == "pi_existing"
        assert response.booking_reference == "TAG-EXIST44"
        assert response.amount == 12000

    async def test_H_modifies_existing_payment_intent_when_promo_changes(self, monkeypatch):
        self._patch_common(monkeypatch)
        payment = SimpleNamespace(stripe_payment_intent_id="pi_existing", amount_pence=12000)
        existing = SimpleNamespace(id=45, reference="TAG-EXIST45", payment=payment)
        monkeypatch.setattr(main.db_service, "get_pending_booking_by_session", lambda *a, **kw: existing)
        monkeypatch.setattr(main, "calculate_price_in_pence", lambda *a, **kw: 10000)

        retrieved = SimpleNamespace(
            id="pi_existing",
            client_secret="secret_old",
            amount=12000,
            status="requires_payment_method",
            metadata=SimpleNamespace(promo_code="OLDCODE"),
        )
        modified = SimpleNamespace(id="pi_existing", client_secret="secret_new")
        monkeypatch.setattr(main.stripe.PaymentIntent, "retrieve", lambda *_: retrieved)
        modify = MagicMock(return_value=modified)
        monkeypatch.setattr(main.stripe.PaymentIntent, "modify", modify)

        promo_code = SimpleNamespace(
            code="NEW10",
            promotion_id=7,
            is_used=False,
            used_at=None,
            expires_at=None,
            is_multi_use=False,
        )
        promotion = SimpleNamespace(
            id=7,
            name="New Ten",
            discount_percent=10,
            discount_type="percentage",
        )

        response = await main.create_payment(
            _request({"session_id": "sess-change", "promo_code": "new10"}),
            _http_request(),
            BackgroundTasks(),
            PaymentDb(promo_code=promo_code, promotion=promotion),
        )

        assert response.amount == 9000
        assert response.discount_amount == 1000
        assert response.promo_code_applied == "NEW10"
        modify.assert_called_once()

    async def test_H_free_booking_confirms_and_returns_without_stripe_intent(self, monkeypatch):
        self._patch_common(monkeypatch)
        monkeypatch.setattr(main.db_service, "get_pending_booking_by_session", lambda *a, **kw: None)
        monkeypatch.setattr(main, "calculate_price_in_pence", lambda *a, **kw: 15000)
        monkeypatch.setattr(main, "mark_promo_code_used", lambda *a, **kw: None)
        monkeypatch.setattr(main, "check_promo_modal_code_used", lambda *a, **kw: None)
        monkeypatch.setattr(main, "send_booking_confirmation_email", lambda *a, **kw: True)

        booking = SimpleNamespace(
            id=77,
            reference="TAG-FREE77",
            dropoff_airline_name="TUI",
            dropoff_destination="Palma",
            pickup_airline_name="easyJet",
            pickup_origin="Malaga",
            confirmation_email_sent=False,
            confirmation_email_sent_at=None,
        )
        monkeypatch.setattr(
            main.db_service,
            "create_full_booking",
            lambda *a, **kw: {"booking": booking, "customer": SimpleNamespace(id=12)},
        )
        payment = SimpleNamespace(status=None, paid_at=None)
        monkeypatch.setattr(main.db_service, "create_payment", lambda *a, **kw: payment)

        promo_code = SimpleNamespace(
            code="FREE100",
            promotion_id=9,
            recipient_email="jo.coverage@tag.test",
            is_used=False,
            used_at=None,
            expires_at=None,
            is_multi_use=False,
            can_be_used=True,
        )
        promotion = SimpleNamespace(
            id=9,
            name="Free",
            discount_percent=100,
            discount_type="free_100",
        )

        response = await main.create_payment(
            _request({"promo_code": "free100"}),
            _http_request(),
            BackgroundTasks(),
            PaymentDb(promo_code=promo_code, promotion=promotion, booking=booking),
        )

        assert response.is_free_booking is True
        assert response.client_secret is None
        assert response.payment_intent_id == "free_TAG-FREE77"
        assert booking.status == BookingStatus.CONFIRMED
        assert payment.status == PaymentStatus.SUCCEEDED

    async def test_H_existing_customer_paid_booking_creates_booking_payment_and_intent(self, monkeypatch):
        self._patch_common(monkeypatch)
        monkeypatch.setattr(main.db_service, "get_pending_booking_by_session", lambda *a, **kw: None)
        monkeypatch.setattr(main, "calculate_price_in_pence", lambda *a, **kw: 16000)

        created_booking = SimpleNamespace(id=88, reference="TAG-PAID88")
        created_payment = SimpleNamespace(id=91)
        create_booking = MagicMock(return_value=created_booking)
        create_payment_record = MagicMock(return_value=created_payment)
        monkeypatch.setattr(main.db_service, "get_customer_by_id", lambda *a, **kw: SimpleNamespace(id=10))
        monkeypatch.setattr(main.db_service, "create_booking", create_booking)
        monkeypatch.setattr(main.db_service, "create_payment", create_payment_record)
        monkeypatch.setattr(
            main,
            "create_payment_intent",
            lambda *_: SimpleNamespace(payment_intent_id="pi_paid88", client_secret="secret_paid88"),
        )

        departure = SimpleNamespace(
            id=51,
            departure_time=time(13, 0),
            destination_name="Tenerife-Reinasofia, ES",
            is_call_us_only=False,
            all_slots_booked=False,
            early_slots_available=2,
            late_slots_available=2,
        )
        db = PaymentDb(departure=departure)

        response = await main.create_payment(
            _request({
                "customer_id": 10,
                "vehicle_id": 20,
                "departure_id": 51,
                "drop_off_time": None,
                "dropoff_flight_time": "13:00",
                "drop_off_slot": "120",
                "pickup_origin": "Tenerife-Reinasofia, ES",
                "flight_arrival_time": "23:45",
                "session_id": "sess-paid",
            }),
            _http_request(),
            BackgroundTasks(),
            db,
        )

        assert response.payment_intent_id == "pi_paid88"
        assert response.amount == 16000
        create_booking.assert_called_once()
        kwargs = create_booking.call_args.kwargs
        assert kwargs["dropoff_time"] == time(11, 0)
        assert kwargs["pickup_time"] == time(0, 15)
        assert kwargs["pickup_date"] == date(2026, 8, 23)
        assert kwargs["dropoff_destination"] == "Tenerife"
        assert kwargs["pickup_origin"] == "Tenerife"
        create_payment_record.assert_called_once_with(
            db=db,
            booking_id=88,
            stripe_payment_intent_id="pi_paid88",
            amount_pence=16000,
        )


def test_H_run_migrations_executes_idempotent_upgrade_paths(monkeypatch):
    class Result:
        def fetchone(self):
            return None

        def scalar(self):
            return "sms_templates"

    class MigrationDb:
        def __init__(self):
            self.statements = []
            self.commit = MagicMock()
            self.rollback = MagicMock()
            self.close = MagicMock()

        def execute(self, statement, params=None):
            self.statements.append((str(statement), params))
            return Result()

    db = MigrationDb()
    monkeypatch.setattr("database.SessionLocal", lambda: db)

    main.run_migrations()

    assert db.commit.call_count >= 5
    db.close.assert_called_once()
    assert any("ALTER TABLE bookings" in sql for sql, _ in db.statements)


@pytest.mark.asyncio
class TestStatsExportWebhookCoverage:
    async def test_H_booking_stats_builds_growth_revenue_search_and_bid_sections(self):
        today = date.today()
        created_recent = datetime.combine(today, time(9, 30))
        created_last_week = datetime.combine(today - timedelta(days=8), time(20, 15))
        bookings = [
            SimpleNamespace(
                id=1,
                created_at=created_recent,
                status=BookingStatus.CONFIRMED,
                payment=SimpleNamespace(amount_pence=12000),
                dropoff_date=today + timedelta(days=10),
                pickup_date=today + timedelta(days=17),
                dropoff_time=time(6, 30),
                pickup_time=time(20, 45),
            ),
            SimpleNamespace(
                id=2,
                created_at=created_last_week,
                status=BookingStatus.COMPLETED,
                payment=SimpleNamespace(amount_pence=8000),
                dropoff_date=today + timedelta(days=20),
                pickup_date=today + timedelta(days=23),
                dropoff_time=time(15, 0),
                pickup_time=time(9, 0),
            ),
            SimpleNamespace(
                id=3,
                created_at=created_recent,
                status=BookingStatus.CANCELLED,
                payment=None,
                dropoff_date=None,
                pickup_date=None,
                dropoff_time=None,
                pickup_time=None,
            ),
        ]
        searches = [
            SimpleNamespace(created_at=created_recent, event=AuditLogEvent.DATES_SELECTED),
            SimpleNamespace(created_at=created_recent + timedelta(hours=1), event=AuditLogEvent.DATES_SELECTED),
            SimpleNamespace(created_at=created_last_week, event=AuditLogEvent.DATES_SELECTED),
        ]
        db = _db_from_sequence([bookings, searches])

        result = await main.get_booking_stats(db=db, current_user=_user())

        assert result["total_bookings"] == 3
        assert result["total_successful"] == 2
        assert result["total_revenue"] == 200.0
        assert result["dropoff_range"]["am"] == 1
        assert result["pickup_range"]["pm"] == 1
        assert result["total_searches"] == 3
        assert len(result["bid_recommendations"]) == 7
        assert result["monthly_booking_pattern"]["overall"]["total"] >= 0

    async def test_H_mark_booking_paid_books_slot_updates_payment_and_sends_email(self, monkeypatch):
        import email_service

        monkeypatch.setattr(email_service, "send_booking_confirmation_email", lambda *a, **kw: True)
        monkeypatch.setattr(main, "calculate_price_in_pence", lambda *a, **kw: 10000)

        booking = SimpleNamespace(
            id=55,
            reference="TAG-MARK55",
            status=BookingStatus.PENDING,
            departure_id=99,
            dropoff_slot="150",
            created_at=datetime(2026, 6, 1, 10, 0),
            dropoff_date=date(2026, 7, 1),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 7, 8),
            pickup_time=time(15, 0),
            flight_arrival_date=date(2026, 7, 8),
            flight_arrival_time=time(14, 30),
            flight_departure_time=time(13, 0),
            package="longer",
            dropoff_airline_name="TUI",
            dropoff_flight_number="BY123",
            dropoff_destination="Palma",
            pickup_airline_name="easyJet",
            pickup_flight_number="EZY456",
            pickup_origin="Malaga",
            customer=SimpleNamespace(email="jo@tag.test", first_name="Jo"),
            customer_first_name="Jo",
            vehicle=SimpleNamespace(make="Tesla", model="Model 3", colour="Blue", registration="AB12CDE"),
            confirmation_email_sent=False,
            confirmation_email_sent_at=None,
        )
        payment = SimpleNamespace(status=PaymentStatus.PENDING, paid_at=None, amount_pence=15000)
        subscriber = SimpleNamespace(
            promo_10_used_booking_id=55,
            promo_free_used_booking_id=None,
            promo_code_used_booking_id=None,
            promo_10_code="SAVE10",
            promo_free_code=None,
            promo_code=None,
        )
        db = _db_from_sequence([[booking], [], [payment], [subscriber]])

        result = await main.mark_booking_paid(
            booking_id=55,
            background_tasks=BackgroundTasks(),
            db=db,
            current_user=_user(),
        )

        assert result["success"] is True
        assert result["email_sent"] is True
        assert booking.status == BookingStatus.CONFIRMED
        assert payment.status == PaymentStatus.SUCCEEDED
        assert booking.confirmation_email_sent is True

    async def test_H_stripe_webhook_payment_failed_logs_structured_decline(self, monkeypatch):
        self._patch_webhook_common(monkeypatch)
        monkeypatch.setattr(
            main,
            "verify_webhook_signature",
            lambda *_: {
                "type": "payment_intent.payment_failed",
                "data": {
                    "object": AttrDict({
                        "id": "pi_failed",
                        "metadata": {"booking_reference": "TAG-FAIL"},
                        "last_payment_error": SimpleNamespace(
                            message="Card declined",
                            code="card_declined",
                            decline_code="do_not_honor",
                        ),
                    })
                },
            },
        )

        result = await main.stripe_webhook(
            request=DummyWebhookRequest(),
            background_tasks=BackgroundTasks(),
            stripe_signature="sig",
            db=MagicMock(),
        )

        assert result == {"status": "failed", "error": "Card declined"}

    async def test_H_stripe_webhook_refund_updated_updates_payment(self, monkeypatch):
        self._patch_webhook_common(monkeypatch)
        monkeypatch.setattr(
            main,
            "verify_webhook_signature",
            lambda *_: {
                "type": "refund.updated",
                "data": {
                    "object": {
                        "id": "re_123",
                        "amount": 5000,
                        "status": "succeeded",
                        "payment_intent": "pi_refund",
                    }
                },
            },
        )
        payment = SimpleNamespace(
            amount_pence=10000,
            refund_amount_pence=0,
            refunded_at=None,
            refund_id=None,
            status=PaymentStatus.SUCCEEDED,
        )
        db = _db_from_sequence([[payment]])

        result = await main.stripe_webhook(
            request=DummyWebhookRequest(),
            background_tasks=BackgroundTasks(),
            stripe_signature="sig",
            db=db,
        )

        assert result == {"status": "refunded", "payment_intent_id": "pi_refund"}
        assert payment.refund_amount_pence == 5000
        assert payment.status == PaymentStatus.PARTIALLY_REFUNDED

    async def test_H_export_financial_report_streams_discounted_rows(self):
        paid_at = datetime(2026, 6, 1, 12, 0)
        booking = SimpleNamespace(
            id=80,
            reference="TAG-CSV80",
            status=BookingStatus.CONFIRMED,
            payment=SimpleNamespace(
                paid_at=paid_at,
                amount_pence=9000,
                refund_amount_pence=1000,
                status=PaymentStatus.PARTIALLY_REFUNDED,
            ),
            dropoff_date=date(2026, 7, 1),
            pickup_date=date(2026, 7, 8),
            customer=SimpleNamespace(first_name="Csv", last_name="Guest"),
        )
        promo = SimpleNamespace(
            booking_id=80,
            code="SAVE10",
            promotion=SimpleNamespace(discount_percent=10),
        )
        db = _db_from_sequence([[booking], [promo], [], [], [], []])

        response = await main.export_financial_report(
            from_date="01/06/2026",
            to_date="30/06/2026",
            status_filter="confirmed",
            promo_filter="yes",
            db=db,
            current_user=_user(),
        )

        assert isinstance(response, StreamingResponse)
        chunks = [chunk async for chunk in response.body_iterator]
        body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)
        assert "TAG-CSV80" in body
        assert "SAVE10" in body
        assert "financial_report_from_01-06-2026_to_30-06-2026.csv" in response.headers["content-disposition"]

    def _patch_webhook_common(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        monkeypatch.setattr(main, "log_audit_event", lambda *a, **kw: None)
        monkeypatch.setattr(main, "log_error", lambda *a, **kw: None)
        monkeypatch.setattr(main.db_service, "update_payment_status", lambda *a, **kw: None)

    async def test_H_manual_booking_paid_path_creates_customer_vehicle_booking_and_email(self, monkeypatch):
        import email_service

        monkeypatch.setattr(main.db_service, "find_overcapacity_day_in_stay", lambda *a, **kw: None)
        monkeypatch.setattr(email_service, "send_manual_booking_payment_email", lambda *a, **kw: True)
        monkeypatch.setattr(main, "mark_promo_code_used", lambda *a, **kw: None)
        monkeypatch.setattr("random.choices", lambda *a, **kw: list("ABCDEFGH"))

        departure = SimpleNamespace(
            id=40,
            capacity_tier=4,
            slots_booked_early=0,
            slots_booked_late=0,
            destination_name="Tenerife-Reinasofia, ES",
        )
        arrival = SimpleNamespace(id=41, origin_name="Tenerife-Reinasofia, ES")
        promo_code = SimpleNamespace(code="MAN10", promotion_id=4, can_be_used=True)
        promotion = SimpleNamespace(discount_percent=10)
        db = _db_from_sequence([[], [], [departure], [arrival], [promo_code], [promotion]])

        def _add(obj):
            if getattr(obj, "id", None) is None:
                obj.id = 100 + db.add.call_count
        db.add.side_effect = _add

        request = main.ManualBookingRequest(
            first_name="jo",
            last_name="manual",
            email="manual@tag.test",
            phone="07700900000",
            billing_address1="1 Test Street",
            billing_city="Bournemouth",
            billing_postcode="BH1 1AA",
            registration="ab12cde",
            make="Tesla",
            model="Model 3",
            colour="Blue",
            tax_status="Taxed",
            mot_status="Valid",
            dropoff_date=date(2026, 8, 1),
            dropoff_time="10:00",
            pickup_date=date(2026, 8, 8),
            pickup_time="15:00",
            flight_arrival_date=date(2026, 8, 8),
            departure_id=40,
            dropoff_slot="150",
            dropoff_airline_name="TUI",
            dropoff_flight_number="BY123",
            pickup_airline_name="easyJet",
            pickup_flight_number="EZY456",
            flight_departure_time="13:00",
            flight_arrival_time="14:30",
            stripe_payment_link="https://pay.test/manual",
            amount_pence=9000,
            promo_code="MAN10",
            notes="phone booking",
        )

        result = await main.create_manual_booking(request=request, db=db, current_user=_user())

        assert result["success"] is True
        assert result["booking_reference"] == "TAG-ABCDEFGH"
        assert result["email_sent"] is True
        db.commit.assert_called_once()

    async def test_H_update_promo_modal_updates_fields_dates_status_and_subscriber_count(self):
        from db_models import PromoModalStatus, PromoModalType

        modal = SimpleNamespace(
            id=1,
            type=PromoModalType.INFO_MODAL,
            title="Old",
            message="Old message",
            button_text="Old",
            button_action="close",
            button_link=None,
            start_date=None,
            end_date=None,
            background_color="#000000",
            text_color="#ffffff",
            button_color="#111111",
            button_text_color="#ffffff",
            status=PromoModalStatus.INACTIVE,
            max_subscribers=10,
            subscribers_at_activation=None,
            promo_code=None,
            created_at=datetime(2026, 1, 1, 10, 0),
            view_count=0,
            click_count=0,
        )
        db = _db_from_sequence([[modal], []])
        db.query.side_effect = [QueryStub(first=modal), QueryStub(rows=[], first=None)]
        db.query.side_effect = lambda *args, **kwargs: QueryStub(first=modal) if db.query.call_count == 0 else QueryStub(rows=[1, 2, 3])
        # MagicMock increments call_count after side_effect, so use a closure instead.
        calls = {"count": 0}
        def _query(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return QueryStub(first=modal)
            return QueryStub(rows=[1, 2, 3])
        db.query.side_effect = _query

        result = await main.update_promo_modal(
            modal_id=1,
            request=main.PromoModalUpdate(
                type="promo_section",
                title="New",
                message="New message",
                button_text="Claim",
                button_action="promotions",
                button_link="https://tag.test",
                start_date="01/08/2026",
                end_date="31/08/2026",
                background_color="#123456",
                text_color="#eeeeee",
                button_color="#ccff00",
                button_text_color="#111111",
                status="active",
                max_subscribers=3,
                promo_code="SUMMER",
            ),
            db=db,
            current_user=_user(),
        )

        assert result["success"] is True
        assert result["promoModal"]["title"] == "New"
        assert result["promoModal"]["type"] == "promo_section"
        assert modal.subscribers_at_activation == 3

    async def test_H_export_marketing_sources_csv_streams_rows(self):
        source = SimpleNamespace(
            source="Google",
            source_detail="Search ad",
            created_at=datetime(2026, 6, 2, 9, 0),
        )
        customer = SimpleNamespace(
            id=5,
            email="source@tag.test",
            first_name="Source",
            last_name="Customer",
        )
        db = _db_from_sequence([[(source, customer)]])

        response = await main.export_marketing_sources_csv(
            from_date="01/06/2026",
            to_date="30/06/2026",
            db=db,
            current_user=_user(),
        )

        chunks = [chunk async for chunk in response.body_iterator]
        body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)
        assert "source@tag.test" in body
        assert "Google" in body
        assert "marketing_sources_from_01/06/2026_to_30/06/2026.csv" in response.headers["content-disposition"]


@pytest.mark.asyncio
class TestParkingSeedSmsAndReferralCoverage:
    async def test_H_public_flight_schedule_endpoints_format_blocked_and_combined_rows(self):
        flight_date = date(2026, 8, 1)
        blocked_dropoff = SimpleNamespace(reason="Staff training")
        blocked_pickup = SimpleNamespace(reason="Late closure")
        departure = SimpleNamespace(
            id=1,
            date=flight_date,
            departure_time=time(13, 0),
            airline_code="BY",
            airline_name="TUI",
            destination_code="TFS",
            destination_name="Tenerife",
            flight_number="BY123",
            capacity_tier=4,
            max_slots_per_time=2,
            early_slots_available=1,
            late_slots_available=2,
            is_call_us_only=False,
            all_slots_booked=False,
            total_slots_available=3,
            is_last_slot=False,
            early_is_last_slot=True,
            late_is_last_slot=False,
        )
        arrival = SimpleNamespace(
            id=2,
            date=flight_date,
            arrival_time=time(23, 45),
            departure_time=time(19, 15),
            airline_code="EZY",
            airline_name="easyJet",
            origin_code="AGP",
            origin_name="Malaga",
            flight_number="EZY456",
        )

        departures = await main.get_departures_for_date(
            flight_date=flight_date,
            db=_db_from_sequence([[blocked_dropoff], [departure]]),
        )
        arrivals = await main.get_arrivals_for_date(
            flight_date=flight_date,
            db=_db_from_sequence([[blocked_pickup], [arrival]]),
        )
        schedule = await main.get_schedule_for_date(
            flight_date=flight_date,
            db=_db_from_sequence([[departure], [arrival]]),
        )

        assert departures[0]["is_blocked"] is True
        assert departures[0]["blocked_reason"] == "Staff training"
        assert arrivals[0]["departureTime"] == "19:15"
        assert arrivals[0]["blocked_reason"] == "Late closure"
        assert [row["type"] for row in schedule] == ["departure", "arrival"]

    async def test_H_free_parking_email_template_success_and_failures(self, monkeypatch):
        send = MagicMock(return_value=True)
        monkeypatch.setattr("email_service.send_email", send)
        monkeypatch.setattr("builtins.open", mock_open(read_data="Hi {{FIRST_NAME}} code {{PROMO_CODE}}"))

        assert main.send_free_parking_promo_email("Jo", "jo@tag.test", "FREE100") is True
        send.assert_called_once()
        assert "Jo, you've won FREE airport parking!" in send.call_args.args[1]
        assert "Hi Jo code FREE100" == send.call_args.args[2]

        monkeypatch.setattr("builtins.open", MagicMock(side_effect=FileNotFoundError()))
        assert main.send_free_parking_promo_email("Jo", "jo@tag.test", "FREE100") is False

        monkeypatch.setattr("builtins.open", MagicMock(side_effect=RuntimeError("bad template")))
        assert main.send_free_parking_promo_email("Jo", "jo@tag.test", "FREE100") is False

    async def test_H_import_departures_capacity_success_error_and_secret_paths(self, monkeypatch):
        monkeypatch.setattr(main.os, "getenv", lambda *a, **kw: "secret")
        with pytest.raises(main.HTTPException) as exc:
            await main.import_departures_with_capacity(
                request=main.ImportDeparturesRequest(tsv_data="bad"),
                secret="wrong",
                db=MagicMock(),
                current_user=_user(),
            )
        assert exc.value.status_code == 403

        module = SimpleNamespace(import_from_tsv_string=MagicMock(return_value={"imported": 2}))
        monkeypatch.setitem(sys.modules, "import_departures_capacity", module)
        result = await main.import_departures_with_capacity(
            request=main.ImportDeparturesRequest(tsv_data="rows", clear_existing=False),
            secret="secret",
            db=MagicMock(),
            current_user=_user(),
        )
        assert result == {"imported": 2}
        module.import_from_tsv_string.assert_called_once_with("rows", False)

        module.import_from_tsv_string = MagicMock(return_value={"error": "bad tsv"})
        with pytest.raises(main.HTTPException) as bad_exc:
            await main.import_departures_with_capacity(
                request=main.ImportDeparturesRequest(tsv_data="bad"),
                secret="secret",
                db=MagicMock(),
                current_user=_user(),
            )
        assert bad_exc.value.status_code == 500

    async def test_H_flight_schedule_json_loader_and_financial_override(self, monkeypatch):
        main.FLIGHT_SCHEDULE_DATA = None
        monkeypatch.setattr("pathlib.Path.exists", lambda self: str(self).endswith("flightSchedule.json"))
        monkeypatch.setattr("builtins.open", mock_open(read_data='[{"type":"departure","date":"2026-08-01"}]'))

        loaded = main.load_flight_schedule_json()
        assert loaded == [{"type": "departure", "date": "2026-08-01"}]
        assert main.load_flight_schedule_json() is loaded

        main.FLIGHT_SCHEDULE_DATA = None
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        assert main.load_flight_schedule_json() is None

        booking = SimpleNamespace(id=20, override_gross_pence=None, override_discount_pence=None)
        result = await main.update_booking_financial_override(
            booking_id=20,
            gross_pence=15000,
            discount_pence=3000,
            db=_db_from_sequence([[booking]]),
            current_user=_user(),
        )
        assert result["override_gross_pence"] == 15000
        assert booking.override_discount_pence == 3000

        with pytest.raises(main.HTTPException) as missing:
            await main.update_booking_financial_override(
                booking_id=21,
                gross_pence=15000,
                discount_pence=3000,
                db=_db_from_sequence([[]]),
                current_user=_user(),
            )
        assert missing.value.status_code == 404

    async def test_H_send_parking_update_returns_partial_status_when_sms_failed(self, monkeypatch):
        from sqlalchemy.exc import SQLAlchemyError

        booking = SimpleNamespace(
            id=70,
            reference="TAG-PARK70",
            parking_update_email_status="sent",
            parking_update_sms_status="failed",
            parking_update_email_sent_at=datetime(2026, 6, 1, 10, 0),
            parking_update_email_attempt_count=2,
            parking_update_email_last_attempt_at=datetime(2026, 6, 1, 9, 55),
            parking_update_sms_sent_at=None,
            parking_update_last_error="SMS carrier unavailable",
        )
        db = _db_from_sequence([[booking]])
        send = MagicMock(return_value=True)
        monkeypatch.setattr("email_scheduler.send_parking_update_for_booking", send)

        result = await main.send_parking_update_endpoint(
            booking_id=70,
            db=db,
            current_user=_user(),
        )

        assert result["parking_update_status"] == "partial"
        assert result["parking_update_sms_status"] == "failed"
        assert "SMS failed" in result["message"]
        db.refresh.assert_called_once_with(booking)

        monkeypatch.setattr("email_scheduler.send_parking_update_for_booking", MagicMock(side_effect=SQLAlchemyError()))
        db_error = _db_from_sequence([[booking]])
        with pytest.raises(main.HTTPException) as exc:
            await main.send_parking_update_endpoint(booking_id=70, db=db_error, current_user=_user())
        assert exc.value.status_code == 500
        db_error.rollback.assert_called_once()

    async def test_H_seed_flights_validates_secret_and_loads_departures_arrivals(self, monkeypatch):
        monkeypatch.setattr(main.os, "getenv", lambda *a, **kw: "secret")
        with pytest.raises(main.HTTPException) as exc:
            await main.seed_flights(secret="wrong", clear_existing=True, db=MagicMock(), current_user=_user())
        assert exc.value.status_code == 403

        flights = [
            {
                "date": "2026-08-01",
                "type": "departure",
                "flightNumber": "BY123",
                "airlineCode": "BY",
                "airlineName": "TUI",
                "time": "13:00",
                "destinationCode": "TFS",
                "destinationName": "Tenerife",
                "capacity_tier": 4,
            },
            {
                "date": "2026-08-08",
                "type": "arrival",
                "flightNumber": "EZY456",
                "airlineCode": "EZY",
                "airlineName": "easyJet",
                "time": "23:45",
                "departureTime": "19:15",
                "originCode": "AGP",
                "originName": "Malaga",
            },
        ]
        monkeypatch.setattr(main, "load_flight_schedule_json", lambda: flights)
        db = _db_from_sequence([[], []])

        result = await main.seed_flights(secret="secret", clear_existing=True, db=db, current_user=_user())

        assert result == {"success": True, "departures": 1, "arrivals": 1, "total": 2}
        assert db.add.call_count == 2
        assert db.commit.call_count == 2

    async def test_H_sms_template_crud_variables_and_messages(self, monkeypatch):
        now = datetime(2026, 6, 1, 12, 0)
        template = SimpleNamespace(
            id=1,
            name="Arrival",
            content="Hi {{first_name}}",
            description="Arrival reminder",
            is_active=True,
            is_automated=False,
            trigger_event=None,
            created_at=now,
            updated_at=now,
        )
        db = _db_from_sequence([[template], [template], [template]])
        templates = await main.get_sms_templates(current_user=_user(), db=db)
        assert templates[0]["created_at"] == now.isoformat()

        created = await main.create_sms_template(
            data={
                "name": "Pickup",
                "content": "Meet soon",
                "description": "Pickup reminder",
                "is_active": False,
                "is_automated": True,
                "trigger_event": "pickup",
            },
            current_user=_user(),
            db=db,
        )
        assert created["name"] == "Pickup"
        db.add.assert_called_once()

        updated = await main.update_sms_template(
            template_id=1,
            data={
                "name": "Arrival updated",
                "content": "Updated",
                "description": "Updated desc",
                "is_active": False,
                "is_automated": True,
                "trigger_event": "arrival",
            },
            current_user=_user(),
            db=db,
        )
        assert updated["name"] == "Arrival updated"
        assert template.trigger_event == "arrival"

        deleted = await main.delete_sms_template(template_id=1, current_user=_user(), db=db)
        assert deleted["success"] is True
        db.delete.assert_called_once_with(template)

        monkeypatch.setattr(main.sms_service, "get_template_variables_list", lambda: ["first_name", "booking_reference"])
        assert await main.get_sms_template_variables(current_user=_user()) == ["first_name", "booking_reference"]

        message = SimpleNamespace(
            id=10,
            phone_number="+447700900000",
            booking_id=22,
            booking=SimpleNamespace(reference="TAG-SMS22"),
            customer_id=33,
            customer=SimpleNamespace(first_name="Sms", last_name="Guest"),
            direction=SMSDirection.OUTBOUND,
            content="Hello",
            status=SMSStatus.SENT,
            status_detail="ok",
            is_bulk=False,
            created_at=now,
            delivered_at=now + timedelta(minutes=1),
        )
        messages_db = MagicMock()
        messages_db.query.return_value = QueryStub(rows=[message], count_value=1)
        result = await main.get_sms_messages(
            phone="7700",
            booking_id=22,
            direction=SMSDirection.OUTBOUND.value,
            status=SMSStatus.SENT.value,
            limit=10,
            offset=0,
            current_user=_user(),
            db=messages_db,
        )
        assert result["total"] == 1
        assert result["messages"][0]["booking_reference"] == "TAG-SMS22"

    async def test_H_sms_threads_conversation_resend_delete_and_bulk_actions(self, monkeypatch):
        now = datetime(2026, 6, 2, 8, 0)
        thread_row = SimpleNamespace(
            phone_number="+447700900001",
            last_activity=now,
            message_count=3,
            customer_id=44,
        )
        customer = SimpleNamespace(id=44, first_name="Thread", last_name="Guest", email="thread@tag.test")
        last_message = SimpleNamespace(
            content="A" * 105,
            direction=SMSDirection.INBOUND,
            created_at=now,
        )
        conversation_messages = [
            SimpleNamespace(
                id=1,
                direction=SMSDirection.INBOUND,
                content="Hello",
                status=SMSStatus.SENT,
                booking_id=55,
                booking=SimpleNamespace(reference="TAG-THREAD55"),
                customer=customer,
                created_at=now,
                is_read=False,
            )
        ]
        calls = {"count": 0}
        db = MagicMock()

        def _query(*_, **__):
            calls["count"] += 1
            if calls["count"] == 1:
                return QueryStub(rows=[thread_row])
            if calls["count"] == 2:
                return QueryStub(first=customer)
            if calls["count"] == 3:
                return QueryStub(count_value=2)
            if calls["count"] == 4:
                return QueryStub(first=last_message)
            if calls["count"] == 5:
                return QueryStub(update_value=4)
            if calls["count"] in (6, 7, 8):
                return QueryStub(delete_value=2)
            return QueryStub(rows=conversation_messages, update_value=1)

        db.query.side_effect = _query
        monkeypatch.setattr(main.sms_service, "format_phone_number", lambda phone: "+447700900001")

        threads = await main.get_sms_threads(current_user=_user(), db=db)
        assert threads["total_unread"] == 2
        assert threads["threads"][0]["last_message"]["content"].endswith("...")

        assert await main.mark_thread_as_read("+44 7700 900001", current_user=_user(), db=db) == {"marked_read": 4}
        assert await main.delete_sms_thread("+44 7700 900001", current_user=_user(), db=db) == {"deleted": 2}
        bulk = await main.bulk_delete_sms_threads(
            request=main.BulkDeleteThreadsRequest(phone_numbers=["07700900001", "07700900002"]),
            current_user=_user(),
            db=db,
        )
        assert bulk == {"deleted": 4, "threads_removed": 2}

        conversation = await main.get_sms_conversation("+44 7700 900001", mark_read=True, current_user=_user(), db=db)
        assert conversation["customer"]["email"] == "thread@tag.test"
        assert conversation["messages"][0]["booking_reference"] == "TAG-THREAD55"

        outbound = SimpleNamespace(
            id=9,
            direction=SMSDirection.OUTBOUND,
            phone_number="+447700900001",
            content="Resend me",
            booking_id=55,
            customer_id=44,
            template_id=3,
        )
        resend_db = _db_from_sequence([[outbound]])
        async def _send_sms(**kwargs):
            return {"success": True, "message_id": 99}
        monkeypatch.setattr(main.sms_service, "send_sms", _send_sms)
        resent = await main.resend_sms_message(message_id=9, current_user=_user(), db=resend_db)
        assert resent["new_message_id"] == 99

        delete_db = _db_from_sequence([[outbound]])
        deleted = await main.delete_sms_message(message_id=9, current_user=_user(), db=delete_db)
        assert deleted["success"] is True

    async def test_H_referral_admin_actions_commit_and_format_program(self, monkeypatch):
        referral = SimpleNamespace(
            id=3,
            customer_id=10,
            status="active",
            invite_source="booking",
            referral_code=SimpleNamespace(
                code="REF123",
                can_be_used=True,
                expires_at=datetime(2026, 12, 31, 23, 59, tzinfo=main.timezone.utc),
                email_sent_at=datetime(2026, 1, 1, 9, 0),
            ),
            reward_code=SimpleNamespace(code="REWARD50"),
            qualified_referral_count=1,
            invite_sent_at=datetime(2026, 1, 1, 9, 0),
            reminder_sent_at=None,
            responded_at=None,
            reward_earned_at=None,
            reward_email_sent_at=None,
        )
        db = _db_from_sequence([[referral], [referral], [referral]])

        monkeypatch.setattr("referral_service.cancel_referral_code", lambda *_: SimpleNamespace(code="REF123"))
        cancelled = await main.admin_cancel_customer_referral_code(10, db=db, current_user=_user())
        assert cancelled["success"] is True
        assert cancelled["referral_program"]["referral_code"] == "REF123"

        monkeypatch.setattr("referral_service.generate_replacement_referral_code", lambda *_: SimpleNamespace(code="REF456"))
        generated = await main.admin_generate_customer_referral_code(10, db=db, current_user=_user())
        assert "REF456 generated" in generated["message"]

        monkeypatch.setattr("referral_service.resend_referral_code", lambda *_: SimpleNamespace(code="REF456"))
        resent = await main.admin_resend_customer_referral_code(10, db=db, current_user=_user())
        assert "REF456 resent" in resent["message"]
        assert db.commit.call_count == 3

    async def test_H_sms_send_bulk_status_and_refresh_endpoints(self, monkeypatch):
        template = SimpleNamespace(id=1, content="Hi {{first_name}}")
        booking = SimpleNamespace(
            id=7,
            customer=SimpleNamespace(id=9, phone="+447700900777", first_name="Bulk"),
        )
        send_sms = MagicMock(return_value={"success": True, "message_id": 10})
        async def _send_sms(**kwargs):
            return send_sms(**kwargs)
        async def _send_bulk_sms(**kwargs):
            return {"success": True, "sent": len(kwargs["messages"])}
        async def _refresh(db):
            return {"refreshed": 2}

        monkeypatch.setattr(main.sms_service, "get_booking_variables", lambda b: {"first_name": b.customer.first_name})
        monkeypatch.setattr(main.sms_service, "render_template", lambda content, variables: content.replace("{{first_name}}", variables["first_name"]))
        monkeypatch.setattr(main.sms_service, "send_sms", _send_sms)
        monkeypatch.setattr(main.sms_service, "send_bulk_sms", _send_bulk_sms)
        monkeypatch.setattr(main.sms_service, "refresh_message_statuses", _refresh)

        sent = await main.send_sms_message(
            data={"phone": "+447700900777", "content": "Fallback", "booking_id": 7, "customer_id": 9, "template_id": 1},
            current_user=_user(),
            db=_db_from_sequence([[template], [booking]]),
        )
        assert sent["message_id"] == 10
        assert send_sms.call_args.kwargs["content"] == "Hi Bulk"

        bulk = await main.send_bulk_sms(
            data={"booking_ids": [7, 8], "template_id": 1},
            current_user=_user(),
            db=_db_from_sequence([[template], [booking], []]),
        )
        assert bulk == {"success": True, "sent": 1}

        status_message = SimpleNamespace(
            id=10,
            status=SMSStatus.DELIVERED,
            status_detail="ok",
            delivered_at=datetime(2026, 6, 2, 9, 0),
        )
        status = await main.get_sms_status(message_id=10, current_user=_user(), db=_db_from_sequence([[status_message]]))
        assert status["status"] == "delivered"
        assert await main.refresh_sms_statuses(current_user=_user(), db=MagicMock()) == {"refreshed": 2}

        with pytest.raises(main.HTTPException) as missing_phone:
            await main.send_sms_message(data={"content": "No phone"}, current_user=_user(), db=MagicMock())
        assert missing_phone.value.status_code == 400

    async def test_H_session_tracking_monthly_counts_ghosts_manual_free_and_cache(self):
        main._session_tracking_cache = {"data": None, "cached_at": None}
        log_month = datetime(2026, 5, 4, 10, 0)
        logs = [
            SimpleNamespace(id=1, created_at=log_month, event=AuditLogEvent.DATES_SELECTED, session_id="s1", booking_reference=None),
            SimpleNamespace(id=2, created_at=log_month, event=AuditLogEvent.FLIGHT_SELECTED, session_id="s1", booking_reference=None),
            SimpleNamespace(id=3, created_at=log_month, event=AuditLogEvent.CUSTOMER_ENTERED, session_id="s1", booking_reference=None),
            SimpleNamespace(id=4, created_at=log_month, event=AuditLogEvent.PAYMENT_INITIATED, session_id="s1", booking_reference="TAG-ONE"),
            SimpleNamespace(id=5, created_at=log_month, event=AuditLogEvent.BOOKING_CONFIRMED, session_id=None, booking_reference="TAG-ONE"),
            SimpleNamespace(id=6, created_at=log_month, event=AuditLogEvent.BOOKING_CONFIRMED, session_id=None, booking_reference=None),
        ]
        manual_booking = SimpleNamespace(created_at=log_month)
        free_booking = SimpleNamespace(created_at=log_month)

        result = await main.get_session_tracking_report(
            period="monthly",
            refresh=True,
            db=_db_from_sequence([logs, [manual_booking], [free_booking]]),
            current_user=_user(),
        )

        assert result["period_type"] == "monthly"
        assert result["periods"][0]["label"] == "May 2026"
        assert result["periods"][0]["manual_bookings"] == 1
        assert result["periods"][0]["free_bookings"] == 1
        assert result["cumulative"]["counts"]["booking_confirmed"] == 1

        daily = await main.get_session_tracking_report(
            period="daily",
            refresh=True,
            db=_db_from_sequence([logs, [], []]),
            current_user=_user(),
        )
        cached = await main.get_session_tracking_report(
            period="daily",
            refresh=False,
            db=_db_from_sequence([]),
            current_user=_user(),
        )
        assert daily["cached"] is False
        assert cached["cached"] is True

    async def test_H_bookings_forecast_scores_history_searches_and_cache(self):
        main._forecast_cache = {"data": None, "cached_at": None}
        now = main.get_uk_now()
        today = now.date()
        booking = SimpleNamespace(
            dropoff_destination="ryanair city",
            dropoff_date=today + timedelta(days=3),
            pickup_date=today + timedelta(days=10),
            created_at=now - timedelta(days=14),
            dropoff_airline_name="Ryanair UK",
            flight_departure_time=time(6, 30),
            flight_arrival_time=time(23, 45),
        )
        abandoned_logs = [
            SimpleNamespace(
                session_id="search-1",
                event_data={
                    "departure_destination": "Emerging",
                    "dropoff_date": (today + timedelta(days=3)).isoformat(),
                    "departure_airline": "Ryanair UK Ltd",
                },
            ),
            SimpleNamespace(
                session_id="search-2",
                event_data='{"departure_destination":"Emerging","dropoff_date":"%s","departure_airline":"Jet2"}' % (today + timedelta(days=4)).isoformat(),
            ),
            SimpleNamespace(session_id="done", event_data={"departure_destination": "Ignored"}),
            SimpleNamespace(session_id="broken", event_data="{not json"),
        ]

        result = await main.get_bookings_forecast(
            refresh=True,
            db=_db_from_sequence([[booking], abandoned_logs, [("done",)]]),
            current_user=_user(),
        )
        assert result["cached"] is False
        assert result["destinations"][0]["destination"] in {"Emerging", "Ryanair City"}
        assert result["airlines"][0]["airline"] == "Ryanair"
        assert result["upcoming_demand"]
        assert result["opportunity_gaps"][0]["destination"] == "Emerging"

        cached = await main.get_bookings_forecast(refresh=False, db=_db_from_sequence([]), current_user=_user())
        assert cached["cached"] is True


def test_H_send_campaign_emails_marks_success_failure_and_skips_unsubscribed(monkeypatch):
    import email_service
    from db_models import MarketingEmailStatus

    campaign = SimpleNamespace(
        id=12,
        promo_code=SimpleNamespace(code="SUMMER10"),
        subject="Summer",
        message="Hello",
        sent_count=0,
        failed_count=0,
        status=None,
        completed_at=None,
    )
    recipients = [
        SimpleNamespace(
            subscriber=SimpleNamespace(
                email="ok@tag.test",
                first_name="Ok",
                unsubscribe_token="tok-ok",
                unsubscribed=False,
            ),
            email_sent=False,
            email_failed=False,
            email_sent_at=None,
            error_message=None,
        ),
        SimpleNamespace(
            subscriber=SimpleNamespace(
                email="fail@tag.test",
                first_name="Fail",
                unsubscribe_token="tok-fail",
                unsubscribed=False,
            ),
            email_sent=False,
            email_failed=False,
            email_sent_at=None,
            error_message=None,
        ),
        SimpleNamespace(
            subscriber=SimpleNamespace(
                email="skip@tag.test",
                first_name="Skip",
                unsubscribe_token="tok-skip",
                unsubscribed=True,
            ),
            email_sent=False,
            email_failed=False,
            email_sent_at=None,
            error_message=None,
        ),
    ]
    db = _db_from_sequence([[campaign], recipients])
    db.close = MagicMock()
    monkeypatch.setattr("database.SessionLocal", lambda: db)
    send = MagicMock(side_effect=[True, False])
    monkeypatch.setattr(email_service, "send_marketing_campaign_email", send)

    main.send_campaign_emails(12)

    assert recipients[0].email_sent is True
    assert recipients[1].email_failed is True
    assert recipients[2].email_sent is False
    assert campaign.sent_count == 1
    assert campaign.failed_count == 1
    assert campaign.status == MarketingEmailStatus.SENT
    db.close.assert_called_once()
