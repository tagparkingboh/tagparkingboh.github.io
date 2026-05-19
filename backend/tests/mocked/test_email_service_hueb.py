"""
HUEB tests for email_service.py — Happy / Unhappy / Edge / Boundary.

All SendGrid I/O is monkeypatched. Each test class targets a specific
function. The template-load family (welcome / promo / booking / refund /
reminder / thank-you / manual / founder / marketing) share the same
shape, so we cover them via a parameterized "happy + template-missing"
suite plus targeted HUEB variants per branch.

Why this matters: the file is 434 statements at ~53% coverage. The
uncovered ranges are the template-load + send branches and the
staging-guard / promo-section conditionals — all reachable from pure
unit calls with no DB or HTTP needed.
"""
import os
import string
from datetime import date as date_type
from unittest.mock import MagicMock, patch

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import email_service


# ============================================================================
# Helpers
# ============================================================================

class _FakeResp:
    def __init__(self, status_code):
        self.status_code = status_code


def _patch_sendgrid(monkeypatch, status_code=202):
    """Patch the SendGridAPIClient used by email_service so .send() returns
    a controllable status without touching the network."""
    sg_class = MagicMock()
    instance = MagicMock()
    instance.send.return_value = _FakeResp(status_code)
    sg_class.return_value = instance
    monkeypatch.setattr("email_service.SendGridAPIClient", sg_class)
    return instance


def _set_api_key(monkeypatch, key="sg-test-key"):
    monkeypatch.setattr(email_service, "SENDGRID_API_KEY", key)


def _clear_api_key(monkeypatch):
    monkeypatch.setattr(email_service, "SENDGRID_API_KEY", None)


# ============================================================================
# is_email_enabled / generate_promo_code
# ============================================================================

class TestIsEmailEnabled:
    def test_H_returns_true_with_key(self, monkeypatch):
        _set_api_key(monkeypatch, "anything")
        assert email_service.is_email_enabled() is True

    def test_U_returns_false_without_key(self, monkeypatch):
        _clear_api_key(monkeypatch)
        assert email_service.is_email_enabled() is False

    def test_E_empty_string_is_false(self, monkeypatch):
        monkeypatch.setattr(email_service, "SENDGRID_API_KEY", "")
        assert email_service.is_email_enabled() is False


class TestGeneratePromoCode:
    def test_H_format_is_tag_dash_4_dash_4(self):
        code = email_service.generate_promo_code()
        assert code.startswith("TAG-")
        parts = code.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4

    def test_E_no_confusing_chars(self):
        """0, O, I, 1, L are excluded for readability."""
        forbidden = set("0OIL1")
        for _ in range(100):
            code = email_service.generate_promo_code()
            body = code.replace("TAG-", "").replace("-", "")
            assert forbidden.isdisjoint(body), f"Generated code has confusing char: {code}"

    def test_E_only_uppercase_and_digits(self):
        allowed = set(string.ascii_uppercase + string.digits) - set("0OIL1")
        for _ in range(20):
            code = email_service.generate_promo_code()
            body = code.replace("TAG-", "").replace("-", "")
            assert set(body).issubset(allowed)

    def test_B_codes_vary(self):
        codes = {email_service.generate_promo_code() for _ in range(50)}
        # cryptographic randomness — collision in 50 from 30^8 space ~ 0
        assert len(codes) == 50


# ============================================================================
# send_email — the core sender
# ============================================================================

class TestSendEmail:
    def test_H_returns_true_on_202(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        assert email_service.send_email("a@b.test", "Hi", "<p>hi</p>") is True

    def test_H_returns_true_on_200(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 200)
        assert email_service.send_email("a@b.test", "Hi", "<p>hi</p>") is True

    def test_H_returns_true_on_201(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 201)
        assert email_service.send_email("a@b.test", "Hi", "<p>hi</p>") is True

    def test_U_no_api_key_returns_false(self, monkeypatch):
        _clear_api_key(monkeypatch)
        # Should not even attempt to call SendGrid
        called = {"n": 0}
        def fake_sg(*a, **kw):
            called["n"] += 1
            return MagicMock()
        monkeypatch.setattr("email_service.SendGridAPIClient", fake_sg)
        assert email_service.send_email("a@b.test", "Hi", "<p>hi</p>") is False
        assert called["n"] == 0

    def test_U_non_2xx_returns_false(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 500)
        assert email_service.send_email("a@b.test", "Hi", "<p>hi</p>") is False

    def test_U_exception_returns_false(self, monkeypatch):
        _set_api_key(monkeypatch)
        sg_class = MagicMock()
        instance = MagicMock()
        instance.send.side_effect = RuntimeError("network down")
        sg_class.return_value = instance
        monkeypatch.setattr("email_service.SendGridAPIClient", sg_class)
        assert email_service.send_email("a@b.test", "Hi", "<p>hi</p>") is False

    def test_B_boundary_status_199_is_false(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 199)
        assert email_service.send_email("a@b.test", "Hi", "<p>hi</p>") is False

    def test_B_boundary_status_203_is_false(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 203)
        assert email_service.send_email("a@b.test", "Hi", "<p>hi</p>") is False


# ============================================================================
# Template-loading family — happy + template-missing per wrapper
# ============================================================================

TEMPLATE_FUNCS = [
    # (callable, kwargs)
    (email_service.send_welcome_email, {"first_name": "Jo", "email": "j@x.test"}),
    (email_service.send_promo_code_email, {"first_name": "Jo", "email": "j@x.test"}),
    (email_service.send_cancellation_email, {
        "email": "j@x.test", "first_name": "Jo",
        "booking_reference": "TAG-1", "dropoff_date": "Mon",
    }),
    (email_service.send_refund_email, {
        "email": "j@x.test", "first_name": "Jo",
        "booking_reference": "TAG-1", "refund_amount": "£10",
    }),
    (email_service.send_2_day_reminder_email, {
        "email": "j@x.test", "first_name": "Jo", "last_name": "K",
        "booking_reference": "TAG-1", "dropoff_date": "Mon",
        "dropoff_time": "10:00", "flight_departure_time": "12:00",
    }),
    (email_service.send_thank_you_email, {"email": "j@x.test", "first_name": "Jo"}),
    (email_service.send_manual_booking_payment_email, {
        "email": "j@x.test", "first_name": "Jo",
        "dropoff_date": "Mon", "dropoff_time": "10:00",
        "pickup_date": "Tue", "pickup_time": "11:00",
        "vehicle_make": "Ford", "vehicle_colour": "Blue",
        "vehicle_registration": "AB12CDE", "amount": "£99",
        "payment_link": "https://stripe/pay/abc",
    }),
    (email_service.send_promo_10_reminder_email, {
        "email": "j@x.test", "first_name": "Jo", "promo_code": "TAG10",
    }),
    (email_service.send_promo_free_reminder_email, {
        "email": "j@x.test", "first_name": "Jo", "promo_code": "TAGFREE",
    }),
    (email_service.send_founder_thank_you_email, {
        "email": "j@x.test", "first_name": "Jo", "promo_code": "TAGTHANKS",
    }),
]


@pytest.mark.parametrize("fn,kwargs", TEMPLATE_FUNCS)
def test_H_template_funcs_send_when_key_set(monkeypatch, fn, kwargs):
    _set_api_key(monkeypatch)
    _patch_sendgrid(monkeypatch, 202)
    # Force open() to return a usable template stub regardless of which file
    monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html>{{FIRST_NAME}}</html>"))
    assert fn(**kwargs) is True


@pytest.mark.parametrize("fn,kwargs", TEMPLATE_FUNCS)
def test_U_template_missing_returns_false(monkeypatch, fn, kwargs):
    _set_api_key(monkeypatch)
    def boom(*a, **kw):
        raise FileNotFoundError("missing")
    monkeypatch.setattr("builtins.open", boom)
    assert fn(**kwargs) is False


@pytest.mark.parametrize("fn,kwargs", TEMPLATE_FUNCS)
def test_U_template_read_error_returns_false(monkeypatch, fn, kwargs):
    _set_api_key(monkeypatch)
    def boom(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr("builtins.open", boom)
    assert fn(**kwargs) is False


class _FakeFile:
    """Minimal context-manager file replacement."""
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *a, **kw):
        return False

    def read(self):
        return self.content


# ============================================================================
# send_login_code_email — inline template (no file)
# ============================================================================

class TestSendLoginCodeEmail:
    def test_H_sends_with_code(self, monkeypatch):
        _set_api_key(monkeypatch)
        sg = _patch_sendgrid(monkeypatch, 202)
        assert email_service.send_login_code_email("a@b.test", "Jo", "123456") is True
        # Verify the code made it into the body
        call_args = sg.send.call_args
        # Mail's html_content holds the body
        sent_mail = call_args[0][0]
        # We can't easily inspect — but we can confirm send was called once.
        assert sg.send.call_count == 1

    def test_U_no_key_returns_false(self, monkeypatch):
        _clear_api_key(monkeypatch)
        assert email_service.send_login_code_email("a@b.test", "Jo", "123456") is False


# ============================================================================
# send_booking_confirmation_email — discount section variants
# ============================================================================

class TestBookingConfirmationDiscount:
    _kwargs = dict(
        email="j@x.test",
        first_name="Jo",
        booking_reference="TAG-1",
        dropoff_date="Mon",
        dropoff_time="10:00",
        pickup_date="Tue",
        pickup_time="11:00",
        flight_arrival_time="11:30",
        flight_departure_time="12:30",
        departure_flight="TOM1",
        return_flight="TOM2",
        vehicle_make="Ford",
        vehicle_colour="Blue",
        vehicle_registration="AB12CDE",
        package_name="1 Week",
        amount_paid="£100",
    )

    def test_H_no_discount(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html>{{DISCOUNT_SECTION}}</html>"))
        assert email_service.send_booking_confirmation_email(**self._kwargs) is True

    def test_E_promo_with_discount_only(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html>{{DISCOUNT_SECTION}}</html>"))
        assert email_service.send_booking_confirmation_email(
            promo_code="TAG10", discount_amount="£10", **self._kwargs
        ) is True

    def test_E_promo_with_subtotal_branch(self, monkeypatch):
        """original_amount triggers the subtotal_row branch."""
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html>{{DISCOUNT_SECTION}}</html>"))
        assert email_service.send_booking_confirmation_email(
            promo_code="TAG10",
            discount_amount="£10",
            original_amount="£110",
            **self._kwargs,
        ) is True

    def test_U_template_missing(self, monkeypatch):
        _set_api_key(monkeypatch)
        def boom(*a, **kw):
            raise FileNotFoundError()
        monkeypatch.setattr("builtins.open", boom)
        assert email_service.send_booking_confirmation_email(**self._kwargs) is False


# ============================================================================
# send_welcome_email — unsubscribe_token branches
# ============================================================================

class TestWelcomeEmailUnsubscribe:
    def test_H_with_token_builds_url(self, monkeypatch):
        _set_api_key(monkeypatch)
        captured = {}
        def fake_send_email(to, subject, html):
            captured["html"] = html
            return True
        monkeypatch.setattr(email_service, "send_email", fake_send_email)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("[{{UNSUBSCRIBE_URL}}]"))
        assert email_service.send_welcome_email("Jo", "j@x.test", unsubscribe_token="tok123") is True
        assert "/api/marketing/unsubscribe/tok123" in captured["html"]

    def test_E_without_token_uses_fallback(self, monkeypatch):
        _set_api_key(monkeypatch)
        captured = {}
        def fake_send_email(to, subject, html):
            captured["html"] = html
            return True
        monkeypatch.setattr(email_service, "send_email", fake_send_email)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("[{{UNSUBSCRIBE_URL}}]"))
        assert email_service.send_welcome_email("Jo", "j@x.test") is True
        assert "tagparking.co.uk" in captured["html"]


# ============================================================================
# send_marketing_campaign_email — promo section + unsubscribe branches
# ============================================================================

class TestMarketingCampaign:
    def test_H_with_promo_code(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html>{{PROMO_CODE_SECTION}}</html>"))
        assert email_service.send_marketing_campaign_email(
            email="j@x.test", first_name="Jo", subject="Summer Deal",
            message="Hi {{first_name}}, from {{founder_name}}",
            promo_code="SUMMER10", unsubscribe_token="tok1",
        ) is True

    def test_E_without_promo_or_unsubscribe(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_marketing_campaign_email(
            email="j@x.test", first_name="Jo", subject="Hello",
            message="text",
        ) is True

    def test_E_empty_first_name_uses_fallback(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        # first_name="" — should fall back to "there"
        assert email_service.send_marketing_campaign_email(
            email="j@x.test", first_name="", subject="Hi", message="x",
        ) is True

    def test_U_no_key_returns_false(self, monkeypatch):
        _clear_api_key(monkeypatch)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_marketing_campaign_email(
            email="j@x.test", first_name="Jo", subject="Hi", message="x",
        ) is False

    def test_U_non_2xx_returns_false(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 500)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_marketing_campaign_email(
            email="j@x.test", first_name="Jo", subject="Hi", message="x",
        ) is False

    def test_U_exception_returns_false(self, monkeypatch):
        _set_api_key(monkeypatch)
        sg_class = MagicMock()
        instance = MagicMock()
        instance.send.side_effect = RuntimeError("boom")
        sg_class.return_value = instance
        monkeypatch.setattr("email_service.SendGridAPIClient", sg_class)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_marketing_campaign_email(
            email="j@x.test", first_name="Jo", subject="Hi", message="x",
        ) is False


# ============================================================================
# Founder direct-send paths (non-send_email): exception + non-2xx branches
# ============================================================================

class TestFounderThankYouDirect:
    _kwargs = {"email": "j@x.test", "first_name": "Jo", "promo_code": "TAGOK"}

    def test_H_sends(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_founder_thank_you_email(**self._kwargs) is True

    def test_U_no_key_returns_false_after_template_load(self, monkeypatch):
        _clear_api_key(monkeypatch)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_founder_thank_you_email(**self._kwargs) is False

    def test_U_non_2xx(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 502)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_founder_thank_you_email(**self._kwargs) is False

    def test_U_exception(self, monkeypatch):
        _set_api_key(monkeypatch)
        sg_class = MagicMock()
        instance = MagicMock()
        instance.send.side_effect = RuntimeError("boom")
        sg_class.return_value = instance
        monkeypatch.setattr("email_service.SendGridAPIClient", sg_class)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_founder_thank_you_email(**self._kwargs) is False


class TestPromoFreeReminderDirect:
    _kwargs = {"email": "j@x.test", "first_name": "Jo", "promo_code": "FREE"}

    def test_U_non_2xx(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 500)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_promo_free_reminder_email(**self._kwargs) is False

    def test_U_exception(self, monkeypatch):
        _set_api_key(monkeypatch)
        sg_class = MagicMock()
        instance = MagicMock()
        instance.send.side_effect = RuntimeError("boom")
        sg_class.return_value = instance
        monkeypatch.setattr("email_service.SendGridAPIClient", sg_class)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_promo_free_reminder_email(**self._kwargs) is False


class TestPromo10ReminderDirect:
    _kwargs = {"email": "j@x.test", "first_name": "Jo", "promo_code": "TAG10"}

    def test_U_non_2xx(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 500)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_promo_10_reminder_email(**self._kwargs) is False


class TestFounderFollowup:
    _kwargs = {"email": "j@x.test", "first_name": "Jo"}

    def test_H_sends(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html>{{first_name}}</html>"))
        assert email_service.send_founder_followup_email(**self._kwargs) is True

    def test_U_no_key(self, monkeypatch):
        _clear_api_key(monkeypatch)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_founder_followup_email(**self._kwargs) is False

    def test_U_non_2xx(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 503)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_founder_followup_email(**self._kwargs) is False

    def test_U_exception(self, monkeypatch):
        _set_api_key(monkeypatch)
        sg_class = MagicMock()
        instance = MagicMock()
        instance.send.side_effect = RuntimeError("boom")
        sg_class.return_value = instance
        monkeypatch.setattr("email_service.SendGridAPIClient", sg_class)
        monkeypatch.setattr("builtins.open", lambda *a, **kw: _FakeFile("<html></html>"))
        assert email_service.send_founder_followup_email(**self._kwargs) is False


# ============================================================================
# send_vehicle_compliance_alert — staging guard + happy + non-prod
# ============================================================================

class TestVehicleComplianceAlert:
    _kwargs = dict(
        booking_reference="TAG-1",
        customer_name="Jo K",
        registration="AB12CDE",
        dropoff_date="Mon",
        dropoff_time="10:00",
        tax_status="TAXED",
        mot_status="EXPIRED",
    )

    def test_H_sends_in_production(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        settings = MagicMock()
        settings.environment = "production"
        monkeypatch.setattr("config.get_settings", lambda: settings)
        assert email_service.send_vehicle_compliance_alert(**self._kwargs) is True

    def test_U_staging_blocks_send(self, monkeypatch):
        settings = MagicMock()
        settings.environment = "staging"
        monkeypatch.setattr("config.get_settings", lambda: settings)
        # If guard fails, send would try; we deliberately leave SG unpatched
        # to ensure the guard intercepts first.
        assert email_service.send_vehicle_compliance_alert(**self._kwargs) is False

    def test_E_none_tax_status_uses_dash(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        settings = MagicMock()
        settings.environment = "production"
        monkeypatch.setattr("config.get_settings", lambda: settings)
        kw = dict(self._kwargs, tax_status=None, mot_status=None)
        assert email_service.send_vehicle_compliance_alert(**kw) is True


# ============================================================================
# send_compliance_conflict_report — staging guard + empty + happy
# ============================================================================

class TestComplianceConflictReport:
    def _conflict(self):
        return {
            "reference": "TAG-1",
            "dropoff_date": date_type(2026, 8, 1),
            "pickup_date": date_type(2026, 8, 7),
            "customer": "Jo K",
            "vehicle_label": "Ford (AB12CDE)",
            "tax_conflict_date": date_type(2026, 8, 3),
            "mot_conflict_date": None,
            "registration": "AB12CDE",
        }

    def test_H_single_conflict_sends(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        settings = MagicMock()
        settings.environment = "production"
        monkeypatch.setattr("config.get_settings", lambda: settings)
        assert email_service.send_compliance_conflict_report([self._conflict()]) is True

    def test_H_multiple_conflicts_sends(self, monkeypatch):
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        settings = MagicMock()
        settings.environment = "production"
        monkeypatch.setattr("config.get_settings", lambda: settings)
        c = self._conflict()
        assert email_service.send_compliance_conflict_report([c, c, c]) is True

    def test_H_mot_only_conflict_branch(self, monkeypatch):
        """Exercise the mot_conflict_date branch."""
        _set_api_key(monkeypatch)
        _patch_sendgrid(monkeypatch, 202)
        settings = MagicMock()
        settings.environment = "production"
        monkeypatch.setattr("config.get_settings", lambda: settings)
        c = self._conflict()
        c["tax_conflict_date"] = None
        c["mot_conflict_date"] = date_type(2026, 8, 4)
        assert email_service.send_compliance_conflict_report([c]) is True

    def test_E_empty_list_does_not_send(self, monkeypatch):
        settings = MagicMock()
        settings.environment = "production"
        monkeypatch.setattr("config.get_settings", lambda: settings)
        # No SG patch — would explode if guard didn't catch it
        assert email_service.send_compliance_conflict_report([]) is False

    def test_U_staging_blocks(self, monkeypatch):
        settings = MagicMock()
        settings.environment = "staging"
        monkeypatch.setattr("config.get_settings", lambda: settings)
        assert email_service.send_compliance_conflict_report([self._conflict()]) is False


# ============================================================================
# send_bounce_alert_email
# ============================================================================

class TestBounceAlertEmail:
    def test_H_sends_with_reference(self, monkeypatch):
        _set_api_key(monkeypatch)
        captured = {}
        def fake_send_email(to, subject, html):
            captured["to"] = to
            captured["subject"] = subject
            captured["html"] = html
            return True
        monkeypatch.setattr(email_service, "send_email", fake_send_email)
        assert email_service.send_bounce_alert_email(
            customer_email="bounce@x.test",
            event_type="bounce",
            reason="550 user unknown",
            booking_reference="TAG-42",
            raw_event='{"event":"bounce"}',
        ) is True
        assert "bounce@x.test" in captured["subject"]
        assert "TAG-42" in captured["html"]
        assert "Raw event" in captured["html"]

    def test_E_without_reference_uses_fallback_copy(self, monkeypatch):
        _set_api_key(monkeypatch)
        captured = {}
        def fake_send_email(to, subject, html):
            captured["html"] = html
            return True
        monkeypatch.setattr(email_service, "send_email", fake_send_email)
        assert email_service.send_bounce_alert_email(
            customer_email="bounce@x.test",
            event_type="dropped",
            reason="content blocked",
        ) is True
        assert "No matching booking" in captured["html"]

    def test_E_without_reason_shows_none_provided(self, monkeypatch):
        _set_api_key(monkeypatch)
        captured = {}
        def fake_send_email(to, subject, html):
            captured["html"] = html
            return True
        monkeypatch.setattr(email_service, "send_email", fake_send_email)
        assert email_service.send_bounce_alert_email(
            customer_email="bounce@x.test",
            event_type="blocked",
            reason="",
        ) is True
        assert "(none provided)" in captured["html"]

    def test_U_send_email_fails_returns_false(self, monkeypatch):
        monkeypatch.setattr(email_service, "send_email", lambda *a, **kw: False)
        assert email_service.send_bounce_alert_email(
            customer_email="bounce@x.test",
            event_type="bounce",
            reason="why",
        ) is False
