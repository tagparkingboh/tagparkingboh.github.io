"""
Mocked unit and TestClient integration tests for referral program behavior.

These tests do not create a database engine. Service tests use small fake
Session/Query objects, and API tests override dependencies or patch service
boundaries in the same style as the existing mocked integration suite.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import referral_service
from db_models import BookingStatus, Customer, PromoCode, Promotion, ReferralAttribution, ReferralProgram


class FakeQuery:
    def __init__(self, all_rows=None, first_row=None, count_value=0):
        self.all_rows = all_rows or []
        self.first_row = first_row
        self.count_value = count_value
        self.filter_args = []

    def join(self, *args, **kwargs):
        return self

    def outerjoin(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        self.filter_args.extend(args)
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return self.all_rows

    def first(self):
        return self.first_row

    def count(self):
        return self.count_value


class SequenceDb:
    def __init__(self, queries_by_model):
        self.queries_by_model = {model: list(queries) for model, queries in queries_by_model.items()}
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0
        self.flush_count = 0
        self.refresh_count = 0

    def query(self, model):
        queries = self.queries_by_model.get(model, [])
        if queries:
            return queries.pop(0)
        return FakeQuery()

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flush_count += 1
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = 100 + self.flush_count

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def refresh(self, obj):
        self.refresh_count += 1


class FakeReferralDb:
    def __init__(self):
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0
        self.flush_count = 0
        self.queries = {}

    def query(self, model):
        query = self.queries.get(model)
        if query is None:
            query = FakeQuery()
            self.queries[model] = query
        return query

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flush_count += 1
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = 100 + self.flush_count

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


def make_customer(id=1, email="customer@example.com"):
    return SimpleNamespace(
        id=id,
        first_name="Test",
        last_name="Customer",
        email=email,
    )


def make_program(status=referral_service.PROGRAM_STATUS_INVITED, customer=None):
    customer = customer or make_customer()
    return SimpleNamespace(
        id=10,
        customer_id=customer.id,
        customer=customer,
        status=status,
        invite_sent_at=datetime.now(timezone.utc) - timedelta(days=30),
        reminder_sent_at=None,
        responded_at=None,
        referral_code_id=None,
        reward_code_id=None,
        qualified_referral_count=0,
        reward_earned_at=None,
        reward_email_sent_at=None,
        referral_code=None,
        reward_code=None,
    )


def _sql_right_value(expression):
    try:
        return expression.right.value
    except Exception:
        return None


class TestReferralInviteScheduler:
    def test_invites_eligible_customer_once(self, monkeypatch):
        customer = make_customer()
        db = FakeReferralDb()
        db.queries[Customer] = FakeQuery(all_rows=[customer])
        db.queries[ReferralProgram] = FakeQuery(first_row=None)

        monkeypatch.setenv("API_BASE_URL", "https://api.test")
        with patch("email_service.send_referral_invite_email", return_value=True) as send:
            sent = referral_service.process_eligible_referral_invites(
                db,
                now=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        assert sent == 1
        assert db.commit_count == 1
        program = db.added[0]
        assert program.customer_id == customer.id
        assert program.status == referral_service.PROGRAM_STATUS_INVITED
        assert program.invite_sent_at == datetime(2026, 6, 1, tzinfo=timezone.utc)
        send.assert_called_once()

    def test_invite_boundary_query_uses_completed_at_less_than_or_equal_7_day_cutoff(self):
        customer = make_customer()
        db = FakeReferralDb()
        customer_query = FakeQuery(all_rows=[customer])
        db.queries[Customer] = customer_query
        db.queries[ReferralProgram] = FakeQuery(first_row=None)
        now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

        with patch("email_service.send_referral_invite_email", return_value=True):
            referral_service.process_eligible_referral_invites(db, now=now)

        cutoff = now - timedelta(days=7)
        assert any(_sql_right_value(arg) == cutoff for arg in customer_query.filter_args)

    def test_invite_send_failure_rolls_back_and_does_not_mark_invited(self):
        customer = make_customer()
        db = FakeReferralDb()
        db.queries[Customer] = FakeQuery(all_rows=[customer])
        db.queries[ReferralProgram] = FakeQuery(first_row=None)

        with patch("email_service.send_referral_invite_email", return_value=False):
            sent = referral_service.process_eligible_referral_invites(db)

        assert sent == 0
        assert db.commit_count == 0
        assert db.rollback_count == 1

    def test_reminder_marks_reminded_once_after_success(self):
        program = make_program()
        db = FakeReferralDb()
        db.queries[ReferralProgram] = FakeQuery(all_rows=[program])

        with patch("email_service.send_referral_invite_reminder_email", return_value=True):
            sent = referral_service.process_referral_invite_reminders(
                db,
                now=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        assert sent == 1
        assert program.status == referral_service.PROGRAM_STATUS_REMINDED
        assert program.reminder_sent_at == datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert db.commit_count == 1

    def test_reminder_boundary_query_uses_invite_sent_at_less_than_or_equal_28_day_cutoff(self):
        program = make_program()
        db = FakeReferralDb()
        reminder_query = FakeQuery(all_rows=[program])
        db.queries[ReferralProgram] = reminder_query
        now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

        with patch("email_service.send_referral_invite_reminder_email", return_value=True):
            referral_service.process_referral_invite_reminders(db, now=now)

        cutoff = now - timedelta(days=28)
        assert any(_sql_right_value(arg) == cutoff for arg in reminder_query.filter_args)

    def test_reminder_send_failure_does_not_mark_sent(self):
        program = make_program()
        db = FakeReferralDb()
        db.queries[ReferralProgram] = FakeQuery(all_rows=[program])

        with patch("email_service.send_referral_invite_reminder_email", return_value=False):
            sent = referral_service.process_referral_invite_reminders(db)

        assert sent == 0
        assert program.status == referral_service.PROGRAM_STATUS_INVITED
        assert program.reminder_sent_at is None
        assert db.rollback_count == 1


class TestReferralResponses:
    def test_yes_response_opts_in_and_generates_code(self):
        program = make_program()
        token = referral_service.generate_response_token(program)
        db = FakeReferralDb()
        db.queries[ReferralProgram] = FakeQuery(first_row=program)

        with patch("referral_service.ensure_referral_code") as ensure_code:
            result = referral_service.respond_to_referral_invite(db, token, "yes")

        assert result is program
        assert program.status == referral_service.PROGRAM_STATUS_OPTED_IN
        assert program.responded_at is not None
        ensure_code.assert_called_once()
        assert db.commit_count == 1

    def test_no_response_opts_out_without_generating_code(self):
        program = make_program()
        token = referral_service.generate_response_token(program)
        db = FakeReferralDb()
        db.queries[ReferralProgram] = FakeQuery(first_row=program)

        with patch("referral_service.ensure_referral_code") as ensure_code:
            result = referral_service.respond_to_referral_invite(db, token, "no")

        assert result is program
        assert program.status == referral_service.PROGRAM_STATUS_OPTED_OUT
        ensure_code.assert_not_called()
        assert db.commit_count == 1

    def test_yes_after_no_remains_opted_out(self):
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_OUT)
        token = referral_service.generate_response_token(program)
        db = FakeReferralDb()
        db.queries[ReferralProgram] = FakeQuery(first_row=program)

        with patch("referral_service.ensure_referral_code") as ensure_code:
            result = referral_service.respond_to_referral_invite(db, token, "yes")

        assert result.status == referral_service.PROGRAM_STATUS_OPTED_OUT
        ensure_code.assert_not_called()
        assert db.commit_count == 0

    def test_no_after_yes_remains_opted_in(self):
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_IN)
        token = referral_service.generate_response_token(program)
        db = FakeReferralDb()
        db.queries[ReferralProgram] = FakeQuery(first_row=program)

        result = referral_service.respond_to_referral_invite(db, token, "no")

        assert result.status == referral_service.PROGRAM_STATUS_OPTED_IN
        assert db.commit_count == 0

    def test_tampered_token_fails_without_mutating(self):
        program = make_program()
        token = referral_service.generate_response_token(program) + "x"
        db = FakeReferralDb()
        db.queries[ReferralProgram] = FakeQuery(first_row=program)

        with pytest.raises(referral_service.ReferralTokenError):
            referral_service.respond_to_referral_invite(db, token, "yes")

        assert program.status == referral_service.PROGRAM_STATUS_INVITED
        assert db.commit_count == 0


class TestReferralCodes:
    def test_opted_in_customer_gets_unlimited_ten_percent_code(self):
        customer = make_customer()
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_IN, customer=customer)
        promotion = SimpleNamespace(id=50, total_codes=0, codes_sent=0)
        db = FakeReferralDb()
        db.queries[Promotion] = FakeQuery(first_row=promotion)
        db.queries[PromoCode] = FakeQuery(first_row=None)

        with patch("email_service.send_referral_code_email", return_value=True):
            code = referral_service.ensure_referral_code(
                db,
                program,
                now=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        assert code.code.startswith("REF-")
        assert code.max_uses == 0
        assert code.customer_id == customer.id
        assert code.email_sent is True
        assert program.referral_code_id == code.id
        assert promotion.total_codes == 1
        assert promotion.codes_sent == 1

    def test_existing_referral_code_is_reused(self):
        existing = SimpleNamespace(id=99, code="REF-ABCD-EFGH", email_sent=True)
        program = make_program()
        program.referral_code_id = existing.id
        db = FakeReferralDb()
        db.queries[PromoCode] = FakeQuery(first_row=existing)

        assert referral_service.ensure_referral_code(db, program) is existing
        assert db.added == []

    def test_existing_unsent_referral_code_is_resent_by_scheduler(self):
        customer = make_customer()
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_IN, customer=customer)
        program.referral_code_id = 99
        code = SimpleNamespace(
            id=99,
            promotion_id=50,
            code="REF-ABCD-EFGH",
            email_sent=False,
            email_sent_at=None,
            email_subject=None,
        )
        promotion = SimpleNamespace(id=50, codes_sent=0)
        db = FakeReferralDb()
        db.queries[ReferralProgram] = FakeQuery(all_rows=[program])
        db.queries[PromoCode] = FakeQuery(first_row=code)
        db.queries[Promotion] = FakeQuery(first_row=promotion)

        with patch("email_service.send_referral_code_email", return_value=True) as send:
            processed = referral_service.process_pending_referral_codes(
                db,
                now=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        assert processed == 1
        assert code.email_sent is True
        assert code.email_sent_at == datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert promotion.codes_sent == 1
        assert db.commit_count == 1
        send.assert_called_once_with(customer.first_name, customer.email, code.code)


class TestAttributionAndRewards:
    def test_friend_use_creates_pending_attribution(self):
        program = SimpleNamespace(id=10, customer_id=1)
        booking = SimpleNamespace(id=22, customer_id=2)
        promo_code = SimpleNamespace(id=5)
        db = FakeReferralDb()
        db.queries[ReferralProgram] = FakeQuery(first_row=program)
        db.queries[ReferralAttribution] = FakeQuery(first_row=None)

        attribution = referral_service.record_referral_attribution_for_booking(db, booking, promo_code)

        assert attribution.booking_id == booking.id
        assert attribution.referrer_customer_id == program.customer_id
        assert attribution.referred_customer_id == booking.customer_id
        assert attribution.is_self_use is False
        assert attribution.status == referral_service.ATTRIBUTION_STATUS_PENDING
        assert attribution in db.added

    def test_self_use_is_disqualified_but_recorded(self):
        program = SimpleNamespace(id=10, customer_id=1)
        booking = SimpleNamespace(id=22, customer_id=1)
        promo_code = SimpleNamespace(id=5)
        db = FakeReferralDb()
        db.queries[ReferralProgram] = FakeQuery(first_row=program)
        db.queries[ReferralAttribution] = FakeQuery(first_row=None)

        attribution = referral_service.record_referral_attribution_for_booking(db, booking, promo_code)

        assert attribution.is_self_use is True
        assert attribution.status == referral_service.ATTRIBUTION_STATUS_DISQUALIFIED

    def test_completed_friend_booking_qualifies_and_issues_reward_at_threshold(self):
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_IN)
        attribution = SimpleNamespace(
            booking_id=22,
            is_self_use=False,
            status=referral_service.ATTRIBUTION_STATUS_PENDING,
            qualified_at=None,
            program=program,
            referral_program_id=program.id,
        )
        booking = SimpleNamespace(id=22, status=BookingStatus.COMPLETED)
        db = FakeReferralDb()
        db.queries[ReferralAttribution] = FakeQuery(first_row=attribution, count_value=6)

        with patch("referral_service.ensure_reward_code") as ensure_reward:
            result = referral_service.qualify_referral_for_booking(
                db,
                booking,
                now=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        assert result is attribution
        assert attribution.status == referral_service.ATTRIBUTION_STATUS_QUALIFIED
        assert program.qualified_referral_count == 6
        ensure_reward.assert_called_once()

    def test_seventh_referral_does_not_duplicate_existing_reward(self):
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_IN)
        program.reward_code_id = 77
        attribution = SimpleNamespace(
            booking_id=23,
            is_self_use=False,
            status=referral_service.ATTRIBUTION_STATUS_PENDING,
            qualified_at=None,
            program=program,
            referral_program_id=program.id,
        )
        booking = SimpleNamespace(id=23, status=BookingStatus.COMPLETED)
        db = FakeReferralDb()
        db.queries[ReferralAttribution] = FakeQuery(first_row=attribution, count_value=7)

        with patch("referral_service.ensure_reward_code") as ensure_reward:
            referral_service.qualify_referral_for_booking(db, booking)

        assert program.qualified_referral_count == 7
        ensure_reward.assert_not_called()

    def test_cancelled_after_qualified_is_disqualified_and_recomputed(self):
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_IN)
        program.qualified_referral_count = 6
        attribution = SimpleNamespace(
            booking_id=22,
            is_self_use=False,
            status=referral_service.ATTRIBUTION_STATUS_QUALIFIED,
            qualified_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            program=program,
            referral_program_id=program.id,
        )
        booking = SimpleNamespace(id=22, status=BookingStatus.CANCELLED)
        db = FakeReferralDb()
        db.queries[ReferralAttribution] = FakeQuery(first_row=attribution, count_value=5)

        result = referral_service.disqualify_referral_for_booking(db, booking)

        assert result is attribution
        assert attribution.status == referral_service.ATTRIBUTION_STATUS_DISQUALIFIED
        assert attribution.qualified_at is None
        assert program.qualified_referral_count == 5


class TestRefundDisqualification:
    def test_full_refund_disqualifies_referral_progress(self):
        import db_service
        from db_models import Booking, Payment, PaymentStatus

        payment = SimpleNamespace(
            booking_id=22,
            amount_pence=10000,
            status=PaymentStatus.SUCCEEDED,
            refund_id=None,
            refund_amount_pence=None,
            refund_reason=None,
            refunded_at=None,
        )
        booking = SimpleNamespace(id=22, status=BookingStatus.COMPLETED)
        db = SequenceDb({
            Payment: [FakeQuery(first_row=payment)],
            Booking: [FakeQuery(first_row=booking)],
        })

        with patch("referral_service.disqualify_referral_for_booking") as disqualify:
            result = db_service.record_refund(db, "pi_1", "re_1", 10000, "requested_by_customer")

        assert result is payment
        assert payment.status == PaymentStatus.REFUNDED
        assert booking.status == BookingStatus.REFUNDED
        disqualify.assert_called_once_with(db, booking)
        assert db.commit_count == 1

    def test_partial_refund_does_not_disqualify_referral_progress(self):
        import db_service
        from db_models import Booking, Payment, PaymentStatus

        payment = SimpleNamespace(
            booking_id=22,
            amount_pence=10000,
            status=PaymentStatus.SUCCEEDED,
            refund_id=None,
            refund_amount_pence=None,
            refund_reason=None,
            refunded_at=None,
        )
        db = SequenceDb({
            Payment: [FakeQuery(first_row=payment)],
            Booking: [],
        })

        with patch("referral_service.disqualify_referral_for_booking") as disqualify:
            result = db_service.record_refund(db, "pi_1", "re_1", 2500, "requested_by_customer")

        assert result is payment
        assert payment.status == PaymentStatus.PARTIALLY_REFUNDED
        disqualify.assert_not_called()
        assert db.commit_count == 1


class TestReferralResponseEndpoint:
    def test_yes_response_returns_confirmation_page(self):
        from database import get_db
        from main import app

        app.dependency_overrides[get_db] = lambda: MagicMock()
        program = SimpleNamespace(status=referral_service.PROGRAM_STATUS_OPTED_IN)
        with patch("referral_service.respond_to_referral_invite", return_value=program):
            response = TestClient(app).get("/api/referrals/respond?token=abc&decision=yes")

        assert response.status_code == 200
        assert "You are opted in" in response.text
        app.dependency_overrides.clear()

    def test_invalid_token_returns_error_page(self):
        from database import get_db
        from main import app

        app.dependency_overrides[get_db] = lambda: MagicMock()
        with patch("referral_service.respond_to_referral_invite", side_effect=referral_service.ReferralTokenError("bad")):
            response = TestClient(app).get("/api/referrals/respond?token=bad&decision=yes")

        assert response.status_code == 400
        assert "Referral link expired" in response.text
        app.dependency_overrides.clear()

    def test_unexpected_response_error_is_not_reported_as_expired_token(self):
        from database import get_db
        from main import app

        app.dependency_overrides[get_db] = lambda: MagicMock()
        with patch("referral_service.respond_to_referral_invite", side_effect=RuntimeError("db down")):
            with pytest.raises(RuntimeError, match="db down"):
                TestClient(app).get("/api/referrals/respond?token=abc&decision=yes")

        app.dependency_overrides.clear()


class TestReferralPromoValidationIntegration:
    def test_referral_code_validates_through_existing_promo_endpoint(self):
        from database import get_db
        from main import app

        promo_code = SimpleNamespace(
            code="REF-ABCD-EFGH",
            promotion_id=50,
            expires_at=None,
            can_be_used=True,
            is_multi_use=True,
            uses_remaining=None,
            max_uses=0,
            use_count=0,
            is_used=False,
            email_sent=True,
            recipient_email="referrer@example.com",
        )
        promotion = SimpleNamespace(
            id=50,
            name=referral_service.FRIEND_PROMOTION_NAME,
            discount_percent=10,
            discount_type="percentage",
        )

        class PromoValidateDb(FakeReferralDb):
            def query(self, model):
                if model.__name__ == "PromoCode":
                    return FakeQuery(first_row=promo_code)
                if model.__name__ == "Promotion":
                    return FakeQuery(first_row=promotion)
                return FakeQuery()

        app.dependency_overrides[get_db] = lambda: PromoValidateDb()
        response = TestClient(app).post("/api/promo/validate", json={"code": "ref-abcd-efgh"})

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["discount_percent"] == 10
        assert data["discount_type"] == "percentage"
        app.dependency_overrides.clear()


class TestPromoUsageHook:
    def test_mark_promo_code_used_keeps_usage_and_records_referral_attribution(self):
        from main import mark_promo_code_used

        promo_code = MagicMock()
        promo_code.id = 5
        promo_code.code = "REF-ABCD-EFGH"
        promo_code.promotion_id = 9
        promo_code.can_be_used = True
        promo_code.max_uses = 0
        promo_code.use_count = 0
        promo_code.is_used = False
        promo_code.is_multi_use = True
        booking = SimpleNamespace(id=22)
        promotion = SimpleNamespace(id=9, codes_used=0)

        class MarkUsedDb(FakeReferralDb):
            def query(self, model):
                if model.__name__ == "Booking":
                    return FakeQuery(first_row=booking)
                if model.__name__ == "Promotion":
                    return FakeQuery(first_row=promotion)
                return FakeQuery()

        db = MarkUsedDb()
        with patch("referral_service.record_referral_attribution_for_booking") as record:
            result = mark_promo_code_used(db, promo_code, 22, 10, 500)

        assert result is True
        assert promo_code.use_count == 1
        assert promo_code.is_used is False
        assert promotion.codes_used == 1
        assert any(obj.__class__.__name__ == "PromoCodeUsage" for obj in db.added)
        record.assert_called_once_with(db, booking, promo_code)


class TestReferralAdminActions:
    def test_cancel_referral_code_expires_unlimited_code(self):
        now = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
        code = SimpleNamespace(
            id=5,
            code="REF-ABCD-EFGH",
            expires_at=None,
            is_used=False,
            used_at=None,
        )
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_IN)
        program.referral_code_id = code.id

        db = SequenceDb({PromoCode: [FakeQuery(first_row=code)]})
        result = referral_service.cancel_referral_code(db, program, now=now)

        assert result is code
        assert code.expires_at == now
        assert code.is_used is True
        assert code.used_at == now

    def test_generate_replacement_referral_code_cancels_old_and_unlinks_it(self):
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_IN)
        program.referral_code_id = 5
        new_code = SimpleNamespace(id=6, code="REF-NEWC-ODE2", email_sent=True)

        with patch("referral_service.cancel_referral_code") as cancel, \
             patch("referral_service.ensure_referral_code", return_value=new_code) as ensure:
            result = referral_service.generate_replacement_referral_code("db", program)

        assert result is new_code
        assert program.referral_code_id is None
        assert program.status == referral_service.PROGRAM_STATUS_OPTED_IN
        cancel.assert_called_once_with("db", program, now=None)
        ensure.assert_called_once_with("db", program, now=None)

    def test_generate_replacement_referral_code_fails_when_email_not_sent(self):
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_IN)
        program.referral_code_id = 5
        new_code = SimpleNamespace(id=6, code="REF-NEWC-ODE2", email_sent=False)

        with patch("referral_service.cancel_referral_code"), \
             patch("referral_service.ensure_referral_code", return_value=new_code):
            with pytest.raises(ValueError, match="replacement referral code email"):
                referral_service.generate_replacement_referral_code("db", program)

    def test_resend_referral_code_sends_current_active_code(self):
        now = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
        customer = make_customer(email="referrer@example.com")
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_IN, customer=customer)
        program.referral_code_id = 5
        code = SimpleNamespace(
            id=5,
            code="REF-ABCD-EFGH",
            expires_at=None,
            email_sent=False,
            email_sent_at=None,
            email_subject=None,
        )

        db = SequenceDb({PromoCode: [FakeQuery(first_row=code)]})
        with patch("email_service.send_referral_code_email", return_value=True) as send:
            result = referral_service.resend_referral_code(db, program, now=now)

        assert result is code
        assert code.email_sent is True
        assert code.email_sent_at == now
        assert code.email_subject == "Your Tag referral code"
        send.assert_called_once_with(customer.first_name, customer.email, code.code)

    def test_resend_referral_code_blocks_expired_code(self):
        now = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
        program = make_program(status=referral_service.PROGRAM_STATUS_OPTED_IN)
        program.referral_code_id = 5
        code = SimpleNamespace(
            id=5,
            code="REF-ABCD-EFGH",
            expires_at=now - timedelta(minutes=1),
        )

        db = SequenceDb({PromoCode: [FakeQuery(first_row=code)]})
        with pytest.raises(ValueError, match="cancelled or expired"):
            referral_service.resend_referral_code(db, program, now=now)


class TestReferralAdminEndpointProtection:
    def test_referral_code_actions_require_authentication(self):
        from main import app

        response = TestClient(app).post("/api/admin/customers/1/referral/generate-new-code")

        assert response.status_code == 401
