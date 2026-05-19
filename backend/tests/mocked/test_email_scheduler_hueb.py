"""
HUEB tests for email_scheduler.py — Happy / Unhappy / Edge / Boundary.

Covers the per-process functions (welcome, promo, 2-day reminder,
thank-you, founder followup, DVLA recheck, weekly conflict report,
cleanup_old_snapshots), the `process_all_pending_emails` orchestrator
and the four `_*_standalone` wrappers. APScheduler itself is not
started — `start_scheduler` / `stop_scheduler` are exercised via direct
attribute mocks so no background thread spawns.
"""
from datetime import date as date_type, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import email_scheduler


# ============================================================================
# Helpers
# ============================================================================

def _subscriber(**kw):
    base = dict(
        id=1,
        email="jo@x.test",
        first_name="Jo",
        unsubscribe_token="tok-jo",
        welcome_email_sent=False,
        welcome_email_sent_at=None,
        promo_code=None,
        promo_code_sent=False,
        promo_code_sent_at=None,
        unsubscribed=False,
        subscribed_at=datetime.utcnow() - timedelta(hours=1),
    )
    base.update(kw)
    s = SimpleNamespace(**base)
    return s


def _customer(**kw):
    base = dict(
        id=11,
        email="jo@x.test",
        first_name="Jo",
        last_name="K",
        founder_followup_sent=False,
        founder_followup_sent_at=None,
        created_at=datetime(2026, 4, 1),
        updated_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _booking(**kw):
    base = dict(
        id=99,
        reference="TAG-1",
        customer_id=11,
        customer_first_name="Jo",
        customer_last_name="K",
        status=None,
        dropoff_date=date_type(2026, 6, 1),
        pickup_date=date_type(2026, 6, 8),
        dropoff_time=time(10, 0),
        pickup_time=time(11, 30),
        flight_departure_time=time(12, 30),
        reminder_2day_sent=False,
        reminder_2day_sent_at=None,
        thank_you_email_sent=False,
        thank_you_email_sent_at=None,
        completed_at=datetime.utcnow() - timedelta(hours=3),
        vehicle=None,
        last_compliance_alert_sent_at=None,
        customer=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _vehicle(**kw):
    base = dict(
        id=21,
        registration="AB12CDE",
        colour="Blue",
        make="Ford",
        tax_status="Taxed",
        tax_due_date=None,
        mot_status="Valid",
        mot_expiry_date=None,
        dvla_checked_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class _DBStub:
    """Minimal SA Session-shaped mock that returns pre-set values from .query().filter()...
    Override the dispatch dict per test."""

    def __init__(self):
        self._first = {}   # model_name -> first() return
        self._all = {}     # model_name -> all() return
        self._limit_all = {}  # model_name -> .limit().all() return
        self._delete = 0
        self.commit = MagicMock()
        self.rollback = MagicMock()
        self.close = MagicMock()
        self.add = MagicMock()

    def query(self, *models):
        # primary model = first arg
        primary = models[0] if models else None
        name = primary.__name__ if hasattr(primary, "__name__") else str(primary)
        return _ChainStub(name, self)


class _ChainStub:
    def __init__(self, name, owner):
        self.name = name
        self.owner = owner

    def filter(self, *a, **kw):
        return self

    def order_by(self, *a, **kw):
        return self

    def join(self, *a, **kw):
        return self

    def outerjoin(self, *a, **kw):
        return self

    def limit(self, *a, **kw):
        # Some tests want .limit(n).all() to behave like .all()
        # Allow a separate stash for limit-suffixed queries.
        if self.name in self.owner._limit_all:
            inner = _ChainStub(self.name, self.owner)
            inner._forced_all = self.owner._limit_all[self.name]
            return inner
        return self

    def exists(self):
        # used by founder followup subquery
        return self

    def all(self):
        if getattr(self, "_forced_all", None) is not None:
            return self._forced_all
        return self.owner._all.get(self.name, [])

    def first(self):
        return self.owner._first.get(self.name)

    def delete(self):
        return self.owner._delete


# ============================================================================
# process_pending_welcome_emails
# ============================================================================

class TestProcessPendingWelcomeEmails:
    def test_H_sends_welcome_and_marks_sent(self, monkeypatch):
        sub = _subscriber()
        db = _DBStub()
        db._limit_all["MarketingSubscriber"] = [sub]
        monkeypatch.setattr(email_scheduler, "send_welcome_email", lambda **kw: True)
        email_scheduler.process_pending_welcome_emails(db)
        assert sub.welcome_email_sent is True
        assert sub.welcome_email_sent_at is not None
        assert db.commit.called

    def test_U_send_fails_does_not_mark(self, monkeypatch):
        sub = _subscriber()
        db = _DBStub()
        db._limit_all["MarketingSubscriber"] = [sub]
        monkeypatch.setattr(email_scheduler, "send_welcome_email", lambda **kw: False)
        email_scheduler.process_pending_welcome_emails(db)
        assert sub.welcome_email_sent is False

    def test_E_unsubscribed_is_skipped(self, monkeypatch):
        sub = _subscriber(unsubscribed=True)
        db = _DBStub()
        db._limit_all["MarketingSubscriber"] = [sub]
        called = {"n": 0}
        def fake(**kw):
            called["n"] += 1
            return True
        monkeypatch.setattr(email_scheduler, "send_welcome_email", fake)
        email_scheduler.process_pending_welcome_emails(db)
        assert called["n"] == 0
        assert sub.welcome_email_sent is False

    def test_E_empty_pending_is_noop(self, monkeypatch):
        db = _DBStub()
        db._limit_all["MarketingSubscriber"] = []
        monkeypatch.setattr(email_scheduler, "send_welcome_email", lambda **kw: True)
        email_scheduler.process_pending_welcome_emails(db)
        assert db.commit.called is False

    def test_U_exception_rolls_back(self, monkeypatch):
        db = _DBStub()
        def boom(*a, **kw):
            raise RuntimeError("DB down")
        db.query = boom
        # Should NOT raise — exception is caught
        email_scheduler.process_pending_welcome_emails(db)
        assert db.rollback.called


# ============================================================================
# process_pending_promo_emails
# ============================================================================

class TestProcessPendingPromoEmails:
    def test_H_generates_new_promo_code_and_sends(self, monkeypatch):
        sub = _subscriber(welcome_email_sent=True, welcome_email_sent_at=datetime.utcnow() - timedelta(hours=2))
        db = _DBStub()
        db._limit_all["MarketingSubscriber"] = [sub]
        # First .first() lookup for collision returns None -> code is free
        # But chain.first() can't differentiate from the limit call; we rely on
        # _first key fallback for unrelated lookups.
        monkeypatch.setattr(email_scheduler, "generate_promo_code", lambda: "TAG-AAA-BBB")
        monkeypatch.setattr(email_scheduler, "send_promo_code_email", lambda **kw: True)
        email_scheduler.process_pending_promo_emails(db)
        assert sub.promo_code == "TAG-AAA-BBB"
        assert sub.promo_code_sent is True

    def test_H_reuses_existing_promo_code(self, monkeypatch):
        sub = _subscriber(welcome_email_sent=True, promo_code="TAG-EXIST-OLD")
        db = _DBStub()
        db._limit_all["MarketingSubscriber"] = [sub]
        gen_calls = {"n": 0}
        def gen():
            gen_calls["n"] += 1
            return "should-not-be-called"
        monkeypatch.setattr(email_scheduler, "generate_promo_code", gen)
        monkeypatch.setattr(email_scheduler, "send_promo_code_email", lambda **kw: True)
        email_scheduler.process_pending_promo_emails(db)
        assert sub.promo_code == "TAG-EXIST-OLD"
        assert gen_calls["n"] == 0
        assert sub.promo_code_sent is True

    def test_U_send_fails_keeps_sent_false(self, monkeypatch):
        sub = _subscriber(welcome_email_sent=True, promo_code="TAG-X-Y")
        db = _DBStub()
        db._limit_all["MarketingSubscriber"] = [sub]
        monkeypatch.setattr(email_scheduler, "send_promo_code_email", lambda **kw: False)
        email_scheduler.process_pending_promo_emails(db)
        assert sub.promo_code_sent is False

    def test_E_empty_pending_is_noop(self, monkeypatch):
        db = _DBStub()
        db._limit_all["MarketingSubscriber"] = []
        email_scheduler.process_pending_promo_emails(db)
        assert db.commit.called is False

    def test_U_exception_rolls_back(self, monkeypatch):
        db = _DBStub()
        db.query = MagicMock(side_effect=RuntimeError("boom"))
        email_scheduler.process_pending_promo_emails(db)
        assert db.rollback.called


# ============================================================================
# process_pending_2day_reminders
# ============================================================================

class TestProcess2DayReminders:
    def _wire(self, bookings, customer=None):
        """Use a custom DB that returns bookings for first .all() call
        (after .limit) and the customer for Customer.first()."""
        db = MagicMock()
        # First chain — bookings.
        b_chain = MagicMock()
        b_chain.filter.return_value = b_chain
        b_chain.limit.return_value.all.return_value = bookings
        b_chain.all.return_value = bookings

        # Customer chain
        c_chain = MagicMock()
        c_chain.filter.return_value = c_chain
        c_chain.first.return_value = customer

        def _query(model):
            return b_chain if model.__name__ == "Booking" else c_chain
        db.query.side_effect = _query
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db

    def test_H_sends_when_within_48h(self, monkeypatch):
        import pytz
        uk = pytz.timezone("Europe/London")
        soon = (datetime.now(uk) + timedelta(hours=24))
        b = _booking(dropoff_date=soon.date(), dropoff_time=soon.time().replace(microsecond=0))
        cust = _customer()
        db = self._wire([b], cust)
        monkeypatch.setattr(email_scheduler, "send_2_day_reminder_email", lambda **kw: True)
        monkeypatch.setattr(email_scheduler.sms_service, "is_sms_enabled", lambda: False)
        email_scheduler.process_pending_2day_reminders(db)
        assert b.reminder_2day_sent is True

    def test_U_customer_missing_is_skipped(self, monkeypatch):
        import pytz
        uk = pytz.timezone("Europe/London")
        soon = (datetime.now(uk) + timedelta(hours=24))
        b = _booking(dropoff_date=soon.date(), dropoff_time=soon.time().replace(microsecond=0))
        db = self._wire([b], customer=None)
        called = {"n": 0}
        def fake(**kw):
            called["n"] += 1
            return True
        monkeypatch.setattr(email_scheduler, "send_2_day_reminder_email", fake)
        monkeypatch.setattr(email_scheduler.sms_service, "is_sms_enabled", lambda: False)
        email_scheduler.process_pending_2day_reminders(db)
        assert called["n"] == 0

    def test_U_send_fails_does_not_mark(self, monkeypatch):
        import pytz
        uk = pytz.timezone("Europe/London")
        soon = (datetime.now(uk) + timedelta(hours=24))
        b = _booking(dropoff_date=soon.date(), dropoff_time=soon.time().replace(microsecond=0))
        cust = _customer()
        db = self._wire([b], cust)
        monkeypatch.setattr(email_scheduler, "send_2_day_reminder_email", lambda **kw: False)
        monkeypatch.setattr(email_scheduler.sms_service, "is_sms_enabled", lambda: False)
        email_scheduler.process_pending_2day_reminders(db)
        assert b.reminder_2day_sent is False

    def test_E_sms_failure_is_caught(self, monkeypatch):
        import pytz
        uk = pytz.timezone("Europe/London")
        soon = (datetime.now(uk) + timedelta(hours=24))
        b = _booking(dropoff_date=soon.date(), dropoff_time=soon.time().replace(microsecond=0))
        cust = _customer()
        db = self._wire([b], cust)
        monkeypatch.setattr(email_scheduler, "send_2_day_reminder_email", lambda **kw: True)
        monkeypatch.setattr(email_scheduler.sms_service, "is_sms_enabled", lambda: True)
        async def boom(*a, **kw):
            raise RuntimeError("sms api down")
        monkeypatch.setattr(email_scheduler.sms_service, "send_reminder_2day_sms", boom)
        # Should not raise — exception is caught and logged
        email_scheduler.process_pending_2day_reminders(db)
        assert b.reminder_2day_sent is True  # email succeeded even if SMS failed

    def test_B_outside_48h_window_is_skipped(self, monkeypatch):
        import pytz
        uk = pytz.timezone("Europe/London")
        far = (datetime.now(uk) + timedelta(hours=72))
        b = _booking(dropoff_date=far.date(), dropoff_time=far.time().replace(microsecond=0))
        cust = _customer()
        db = self._wire([b], cust)
        called = {"n": 0}
        def fake(**kw):
            called["n"] += 1
            return True
        monkeypatch.setattr(email_scheduler, "send_2_day_reminder_email", fake)
        monkeypatch.setattr(email_scheduler.sms_service, "is_sms_enabled", lambda: False)
        email_scheduler.process_pending_2day_reminders(db)
        # 72h out — not in 48h window, no send
        assert called["n"] == 0

    def test_U_exception_rolls_back(self, monkeypatch):
        db = MagicMock()
        db.query.side_effect = RuntimeError("DB down")
        db.rollback = MagicMock()
        email_scheduler.process_pending_2day_reminders(db)
        assert db.rollback.called


# ============================================================================
# process_pending_thankyou_emails
# ============================================================================

class TestProcessThankYouEmails:
    def _wire(self, bookings, customer=None):
        db = MagicMock()
        b_chain = MagicMock()
        b_chain.filter.return_value = b_chain
        b_chain.limit.return_value.all.return_value = bookings
        c_chain = MagicMock()
        c_chain.filter.return_value = c_chain
        c_chain.first.return_value = customer
        def _query(model):
            return b_chain if model.__name__ == "Booking" else c_chain
        db.query.side_effect = _query
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db

    def test_H_sends_and_marks(self, monkeypatch):
        b = _booking()
        cust = _customer()
        db = self._wire([b], cust)
        monkeypatch.setattr(email_scheduler, "send_thank_you_email", lambda **kw: True)
        monkeypatch.setattr(email_scheduler.sms_service, "is_sms_enabled", lambda: False)
        email_scheduler.process_pending_thankyou_emails(db)
        assert b.thank_you_email_sent is True

    def test_U_customer_missing_skipped(self, monkeypatch):
        b = _booking()
        db = self._wire([b], customer=None)
        called = {"n": 0}
        def fake(**kw):
            called["n"] += 1
            return True
        monkeypatch.setattr(email_scheduler, "send_thank_you_email", fake)
        monkeypatch.setattr(email_scheduler.sms_service, "is_sms_enabled", lambda: False)
        email_scheduler.process_pending_thankyou_emails(db)
        assert called["n"] == 0

    def test_U_email_fails(self, monkeypatch):
        b = _booking()
        db = self._wire([b], _customer())
        monkeypatch.setattr(email_scheduler, "send_thank_you_email", lambda **kw: False)
        monkeypatch.setattr(email_scheduler.sms_service, "is_sms_enabled", lambda: False)
        email_scheduler.process_pending_thankyou_emails(db)
        assert b.thank_you_email_sent is False

    def test_E_sms_failure_caught(self, monkeypatch):
        b = _booking()
        db = self._wire([b], _customer())
        monkeypatch.setattr(email_scheduler, "send_thank_you_email", lambda **kw: True)
        monkeypatch.setattr(email_scheduler.sms_service, "is_sms_enabled", lambda: True)
        async def boom(*a, **kw):
            raise RuntimeError("sms down")
        monkeypatch.setattr(email_scheduler.sms_service, "send_thank_you_sms", boom)
        email_scheduler.process_pending_thankyou_emails(db)
        assert b.thank_you_email_sent is True  # email succeeded

    def test_U_exception_rolls_back(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("DB down")
        db.rollback = MagicMock()
        email_scheduler.process_pending_thankyou_emails(db)
        assert db.rollback.called


# ============================================================================
# process_pending_founder_followups
# ============================================================================

class TestProcessFounderFollowups:
    def _wire(self, customers):
        db = MagicMock()
        # Customer query
        c_chain = MagicMock()
        c_chain.filter.return_value = c_chain
        c_chain.limit.return_value.all.return_value = customers
        # Booking subquery
        b_chain = MagicMock()
        b_chain.filter.return_value = b_chain
        b_chain.exists.return_value = MagicMock()  # used inside ~has_any_booking

        def _query(model):
            return c_chain if model.__name__ == "Customer" else b_chain
        db.query.side_effect = _query
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db

    def test_H_sends_and_marks(self, monkeypatch):
        c = _customer()
        db = self._wire([c])
        monkeypatch.setattr(email_scheduler, "send_founder_followup_email", lambda **kw: True)
        email_scheduler.process_pending_founder_followups(db)
        assert c.founder_followup_sent is True

    def test_U_send_fails(self, monkeypatch):
        c = _customer()
        db = self._wire([c])
        monkeypatch.setattr(email_scheduler, "send_founder_followup_email", lambda **kw: False)
        email_scheduler.process_pending_founder_followups(db)
        assert c.founder_followup_sent is False

    def test_E_existing_customer_with_updated_at_uses_that_for_last_activity(self, monkeypatch):
        """Branch where customer was updated after the start date."""
        import pytz
        uk_tz = pytz.timezone('Europe/London')
        c = _customer(
            created_at=uk_tz.localize(datetime(2026, 2, 15)),
            updated_at=uk_tz.localize(datetime(2026, 4, 1)),
        )
        db = self._wire([c])
        monkeypatch.setattr(email_scheduler, "send_founder_followup_email", lambda **kw: True)
        email_scheduler.process_pending_founder_followups(db)
        assert c.founder_followup_sent is True

    def test_U_exception_rolls_back(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("DB down")
        db.rollback = MagicMock()
        email_scheduler.process_pending_founder_followups(db)
        assert db.rollback.called

    def test_E_empty_list_is_noop(self, monkeypatch):
        db = self._wire([])
        called = {"n": 0}
        def fake(**kw):
            called["n"] += 1
            return True
        monkeypatch.setattr(email_scheduler, "send_founder_followup_email", fake)
        email_scheduler.process_pending_founder_followups(db)
        assert called["n"] == 0


# ============================================================================
# process_pending_dvla_rechecks
# ============================================================================

class TestProcessDvlaRechecks:
    def _wire(self, bookings):
        db = MagicMock()
        b_chain = MagicMock()
        b_chain.filter.return_value = b_chain
        b_chain.all.return_value = bookings
        db.query.return_value = b_chain
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db

    def test_U_no_api_key_returns_early(self, monkeypatch):
        settings = SimpleNamespace(environment="staging", dvla_api_key_test="", dvla_api_key_prod="")
        monkeypatch.setattr("config.get_settings", lambda: settings)
        db = self._wire([])
        # Should not blow up; just returns
        email_scheduler.process_pending_dvla_rechecks(db)
        # No commits expected
        assert db.commit.called is False

    def test_H_sends_alert_when_unchecked_and_alertable(self, monkeypatch):
        settings = SimpleNamespace(environment="staging", dvla_api_key_test="key", dvla_api_key_prod="")
        monkeypatch.setattr("config.get_settings", lambda: settings)
        veh = _vehicle()
        b = _booking(vehicle=veh, customer=_customer())
        # Make dropoff_date == tomorrow (UK)
        import pytz
        uk = pytz.timezone("Europe/London")
        b.dropoff_date = (datetime.now(uk) + timedelta(days=1)).date()
        db = self._wire([b])
        monkeypatch.setattr("dvla_compliance.refresh_vehicle_dvla", lambda *a, **kw: True)
        monkeypatch.setattr("email_service.send_vehicle_compliance_alert", lambda **kw: True)
        email_scheduler.process_pending_dvla_rechecks(db)
        assert b.last_compliance_alert_sent_at is not None

    def test_E_vehicle_none_is_skipped(self, monkeypatch):
        settings = SimpleNamespace(environment="staging", dvla_api_key_test="key", dvla_api_key_prod="")
        monkeypatch.setattr("config.get_settings", lambda: settings)
        b = _booking(vehicle=None)
        db = self._wire([b])
        # Should not blow up
        email_scheduler.process_pending_dvla_rechecks(db)
        assert b.last_compliance_alert_sent_at is None

    def test_E_dedup_skips_alert_already_sent_today(self, monkeypatch):
        settings = SimpleNamespace(environment="staging", dvla_api_key_test="key", dvla_api_key_prod="")
        monkeypatch.setattr("config.get_settings", lambda: settings)
        import pytz
        uk = pytz.timezone("Europe/London")
        veh = _vehicle()
        b = _booking(vehicle=veh, customer=_customer())
        b.dropoff_date = (datetime.now(uk) + timedelta(days=1)).date()
        # Already sent at start of today UK
        b.last_compliance_alert_sent_at = uk.localize(datetime.combine(datetime.now(uk).date(), time.min))
        db = self._wire([b])
        monkeypatch.setattr("dvla_compliance.refresh_vehicle_dvla", lambda *a, **kw: True)
        sent = {"n": 0}
        def fake(**kw):
            sent["n"] += 1
            return True
        monkeypatch.setattr("email_service.send_vehicle_compliance_alert", fake)
        email_scheduler.process_pending_dvla_rechecks(db)
        assert sent["n"] == 0

    def test_E_already_checked_today_uses_should_alert(self, monkeypatch):
        """Branch where vehicle.dvla_checked_at >= today_start_uk."""
        settings = SimpleNamespace(environment="staging", dvla_api_key_test="key", dvla_api_key_prod="")
        monkeypatch.setattr("config.get_settings", lambda: settings)
        import pytz
        uk = pytz.timezone("Europe/London")
        veh = _vehicle(dvla_checked_at=datetime.now(uk))  # checked today
        b = _booking(vehicle=veh, customer=_customer())
        b.dropoff_date = (datetime.now(uk) + timedelta(days=1)).date()
        db = self._wire([b])
        monkeypatch.setattr("dvla_compliance.should_alert", lambda tax, mot: True)
        monkeypatch.setattr("email_service.send_vehicle_compliance_alert", lambda **kw: True)
        email_scheduler.process_pending_dvla_rechecks(db)
        assert b.last_compliance_alert_sent_at is not None

    def test_U_exception_rolls_back(self, monkeypatch):
        settings = SimpleNamespace(environment="staging", dvla_api_key_test="key", dvla_api_key_prod="")
        monkeypatch.setattr("config.get_settings", lambda: settings)
        db = MagicMock()
        db.query.side_effect = RuntimeError("DB down")
        db.rollback = MagicMock()
        email_scheduler.process_pending_dvla_rechecks(db)
        assert db.rollback.called


# ============================================================================
# process_weekly_conflict_report
# ============================================================================

class TestWeeklyConflictReport:
    def _wire(self, rows):
        db = MagicMock()
        chain = MagicMock()
        chain.join.return_value = chain
        chain.outerjoin.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = rows
        db.query.return_value = chain
        db.close = MagicMock()
        return db

    def test_H_sends_report_with_tax_conflict(self, monkeypatch):
        b = _booking()
        v = _vehicle(tax_status="Taxed",
                     tax_due_date=date_type(2026, 6, 4))
        c = _customer()
        db = self._wire([(b, v, c)])
        captured = {"conflicts": None}
        def fake_send(conflicts):
            captured["conflicts"] = conflicts
            return True
        monkeypatch.setattr("email_service.send_compliance_conflict_report", fake_send)
        email_scheduler.process_weekly_conflict_report(db)
        assert captured["conflicts"] is not None
        assert len(captured["conflicts"]) == 1
        assert captured["conflicts"][0]["tax_conflict_date"] == date_type(2026, 6, 4)

    def test_H_sends_with_mot_conflict_only(self, monkeypatch):
        b = _booking()
        v = _vehicle(tax_status="Untaxed", tax_due_date=None,
                     mot_status="Valid", mot_expiry_date=date_type(2026, 6, 5))
        c = _customer()
        db = self._wire([(b, v, c)])
        captured = {"conflicts": None}
        monkeypatch.setattr("email_service.send_compliance_conflict_report",
                            lambda conf: captured.update({"conflicts": conf}) or True)
        email_scheduler.process_weekly_conflict_report(db)
        assert captured["conflicts"][0]["tax_conflict_date"] is None
        assert captured["conflicts"][0]["mot_conflict_date"] == date_type(2026, 6, 5)

    def test_E_empty_rows_still_calls_send(self, monkeypatch):
        db = self._wire([])
        called = {"n": 0}
        def fake(conf):
            called["n"] += 1
            return True
        monkeypatch.setattr("email_service.send_compliance_conflict_report", fake)
        email_scheduler.process_weekly_conflict_report(db)
        assert called["n"] == 1  # called with []

    def test_U_exception_caught(self, monkeypatch):
        db = MagicMock()
        db.query.side_effect = RuntimeError("DB down")
        db.close = MagicMock()
        # Should not raise
        email_scheduler.process_weekly_conflict_report(db)

    def test_E_own_session_branch_closes_db(self, monkeypatch):
        """When called with db=None, the function opens its own session and
        must close it at the end."""
        owned_db = MagicMock()
        chain = MagicMock()
        chain.join.return_value = chain
        chain.outerjoin.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = []
        owned_db.query.return_value = chain
        owned_db.close = MagicMock()
        monkeypatch.setattr(email_scheduler, "get_db", lambda: owned_db)
        monkeypatch.setattr("email_service.send_compliance_conflict_report", lambda c: True)
        email_scheduler.process_weekly_conflict_report()
        assert owned_db.close.called


# ============================================================================
# process_all_pending_emails + standalones
# ============================================================================

class TestProcessAllPendingEmails:
    def test_U_email_disabled_short_circuits(self, monkeypatch):
        monkeypatch.setattr(email_scheduler, "is_email_enabled", lambda: False)
        called = {"db": 0}
        def fake_db():
            called["db"] += 1
            return MagicMock()
        monkeypatch.setattr(email_scheduler, "get_db", fake_db)
        email_scheduler.process_all_pending_emails()
        assert called["db"] == 0

    def test_H_fires_all_sub_processes(self, monkeypatch):
        monkeypatch.setattr(email_scheduler, "is_email_enabled", lambda: True)
        db = MagicMock()
        monkeypatch.setattr(email_scheduler, "get_db", lambda: db)
        calls = []
        monkeypatch.setattr(email_scheduler, "process_pending_welcome_emails", lambda d: calls.append("welcome"))
        monkeypatch.setattr(email_scheduler, "process_pending_2day_reminders", lambda d: calls.append("2day"))
        monkeypatch.setattr(email_scheduler, "process_pending_thankyou_emails", lambda d: calls.append("ty"))
        monkeypatch.setattr(email_scheduler, "process_pending_founder_followups", lambda d: calls.append("founder"))
        monkeypatch.setattr(email_scheduler, "process_pending_dvla_rechecks", lambda d: calls.append("dvla"))
        email_scheduler.process_all_pending_emails()
        assert calls == ["welcome", "2day", "ty", "founder", "dvla"]
        assert db.close.called


class TestStandaloneWrappers:
    @pytest.mark.parametrize("fn,inner_attr", [
        ("_process_welcome_emails_standalone", "process_pending_welcome_emails"),
        ("_process_2day_reminders_standalone", "process_pending_2day_reminders"),
        ("_process_thankyou_emails_standalone", "process_pending_thankyou_emails"),
        ("_process_founder_followups_standalone", "process_pending_founder_followups"),
    ])
    def test_H_calls_inner_when_enabled(self, monkeypatch, fn, inner_attr):
        monkeypatch.setattr(email_scheduler, "is_email_enabled", lambda: True)
        db = MagicMock()
        monkeypatch.setattr(email_scheduler, "get_db", lambda: db)
        called = {"n": 0}
        monkeypatch.setattr(email_scheduler, inner_attr, lambda d: called.__setitem__("n", called["n"] + 1))
        getattr(email_scheduler, fn)()
        assert called["n"] == 1
        assert db.close.called

    @pytest.mark.parametrize("fn", [
        "_process_welcome_emails_standalone",
        "_process_2day_reminders_standalone",
        "_process_thankyou_emails_standalone",
        "_process_founder_followups_standalone",
    ])
    def test_U_disabled_short_circuits(self, monkeypatch, fn):
        monkeypatch.setattr(email_scheduler, "is_email_enabled", lambda: False)
        called = {"db": 0}
        monkeypatch.setattr(email_scheduler, "get_db", lambda: called.__setitem__("db", called["db"] + 1) or MagicMock())
        getattr(email_scheduler, fn)()
        assert called["db"] == 0


# ============================================================================
# cleanup_old_snapshots
# ============================================================================

class TestCleanupOldSnapshots:
    def test_H_deletes_old_rows(self, monkeypatch):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.delete.return_value = 3
        db.query.return_value = chain
        monkeypatch.setattr(email_scheduler, "get_db", lambda: db)
        email_scheduler.cleanup_old_snapshots()
        assert db.commit.called
        assert db.close.called

    def test_E_nothing_to_delete(self, monkeypatch):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.delete.return_value = 0
        db.query.return_value = chain
        monkeypatch.setattr(email_scheduler, "get_db", lambda: db)
        email_scheduler.cleanup_old_snapshots()
        assert db.commit.called

    def test_U_exception_does_not_propagate(self, monkeypatch):
        def boom():
            raise RuntimeError("DB down")
        monkeypatch.setattr(email_scheduler, "get_db", boom)
        # Should not raise
        email_scheduler.cleanup_old_snapshots()


# ============================================================================
# start_scheduler / stop_scheduler / trigger_immediate_check
# ============================================================================

class TestSchedulerControl:
    def test_H_start_when_not_running_adds_jobs_and_starts(self, monkeypatch):
        fake_sched = MagicMock()
        fake_sched.running = False
        monkeypatch.setattr(email_scheduler, "scheduler", fake_sched)
        email_scheduler.start_scheduler()
        assert fake_sched.add_job.call_count >= 3  # process / cleanup / weekly report
        assert fake_sched.start.called

    def test_E_start_when_already_running_is_noop(self, monkeypatch):
        fake_sched = MagicMock()
        fake_sched.running = True
        monkeypatch.setattr(email_scheduler, "scheduler", fake_sched)
        email_scheduler.start_scheduler()
        assert fake_sched.start.called is False

    def test_H_stop_when_running(self, monkeypatch):
        fake_sched = MagicMock()
        fake_sched.running = True
        monkeypatch.setattr(email_scheduler, "scheduler", fake_sched)
        email_scheduler.stop_scheduler()
        assert fake_sched.shutdown.called

    def test_E_stop_when_not_running_is_noop(self, monkeypatch):
        fake_sched = MagicMock()
        fake_sched.running = False
        monkeypatch.setattr(email_scheduler, "scheduler", fake_sched)
        email_scheduler.stop_scheduler()
        assert fake_sched.shutdown.called is False

    def test_H_trigger_immediate_check_runs_orchestrator(self, monkeypatch):
        called = {"n": 0}
        monkeypatch.setattr(email_scheduler, "process_all_pending_emails",
                            lambda: called.__setitem__("n", called["n"] + 1))
        email_scheduler.trigger_immediate_check()
        assert called["n"] == 1
