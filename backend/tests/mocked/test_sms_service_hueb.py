"""
HUEB tests for sms_service.py — Happy / Unhappy / Edge / Boundary.

Targets the previously-uncovered async send paths (lines 208-295, 314-359),
the templated wrappers (375-518), and the webhook handlers
(handle_delivery_report 521-571, handle_incoming_sms 669-715).

All HTTP I/O is mocked through `email_service.httpx.AsyncClient` so no
network is touched. The module's `SMS_ENABLED` / `SMS_JWT_TOKEN` module
constants are monkeypatched per test.
"""
import asyncio
from datetime import date as date_type, time
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sms_service


# ============================================================================
# Helpers
# ============================================================================

class _FakeResp:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text

    def json(self):
        return self._json


def _enable_sms(monkeypatch, token="jwt-stub"):
    monkeypatch.setattr(sms_service, "SMS_ENABLED", True)
    monkeypatch.setattr(sms_service, "SMS_JWT_TOKEN", token)


def _disable_sms(monkeypatch):
    monkeypatch.setattr(sms_service, "SMS_ENABLED", False)
    monkeypatch.setattr(sms_service, "SMS_JWT_TOKEN", "")


def _patch_httpx(monkeypatch, resp=None, raise_exc=None, method="post"):
    """Patch httpx.AsyncClient so .post/.get returns a FakeResp."""
    client = MagicMock()
    if raise_exc:
        if method == "post":
            client.post = AsyncMock(side_effect=raise_exc)
        else:
            client.get = AsyncMock(side_effect=raise_exc)
    else:
        if method == "post":
            client.post = AsyncMock(return_value=resp or _FakeResp(200, {"messageid": "msg-1"}))
        else:
            client.get = AsyncMock(return_value=resp or _FakeResp(200, {"status": "delivered"}))

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)

    cls = MagicMock(return_value=cm)
    monkeypatch.setattr("sms_service.httpx.AsyncClient", cls)
    return client


def _booking(phone="07123456789", reference="TAG-1"):
    """Minimal booking object that satisfies get_booking_variables + send paths."""
    customer = SimpleNamespace(
        id=11, phone=phone, first_name="Jo", last_name="K",
    )
    vehicle = SimpleNamespace(registration="AB12CDE")
    payment = SimpleNamespace(amount_pence=9900)
    return SimpleNamespace(
        id=42,
        reference=reference,
        customer=customer,
        customer_first_name="Jo",
        customer_last_name="K",
        dropoff_date=date_type(2026, 6, 1),
        pickup_date=date_type(2026, 6, 8),
        dropoff_time=time(10, 0),
        pickup_time=time(11, 30),
        dropoff_destination="Tenerife",
        vehicle=vehicle,
        payment=payment,
    )


# ============================================================================
# is_sms_enabled / get_jwt_token / format_phone / validate_phone
# ============================================================================

class TestIsSmsEnabled:
    def test_H_enabled_with_token(self, monkeypatch):
        _enable_sms(monkeypatch)
        assert sms_service.is_sms_enabled() is True

    def test_U_disabled_flag(self, monkeypatch):
        monkeypatch.setattr(sms_service, "SMS_ENABLED", False)
        monkeypatch.setattr(sms_service, "SMS_JWT_TOKEN", "tok")
        assert sms_service.is_sms_enabled() is False

    def test_U_no_token(self, monkeypatch):
        monkeypatch.setattr(sms_service, "SMS_ENABLED", True)
        monkeypatch.setattr(sms_service, "SMS_JWT_TOKEN", "")
        assert sms_service.is_sms_enabled() is False


class TestGetJwtToken:
    def test_H_returns_token(self, monkeypatch):
        monkeypatch.setattr(sms_service, "SMS_JWT_TOKEN", "abc")
        assert sms_service.get_jwt_token() == "abc"

    def test_U_no_token_returns_none(self, monkeypatch):
        monkeypatch.setattr(sms_service, "SMS_JWT_TOKEN", "")
        assert sms_service.get_jwt_token() is None


class TestFormatPhoneNumber:
    @pytest.mark.parametrize("inp,expected", [
        ("07123456789", "447123456789"),       # UK national
        ("+447123456789", "447123456789"),     # +44 prefix
        ("+44 7123 456 789", "447123456789"),  # spaces
        ("00447123456789", "447123456789"),    # 00 international
        ("447123456789", "447123456789"),      # already international
        ("7123456789", "447123456789"),        # missing leading 0
    ])
    def test_H_various_uk_formats(self, inp, expected):
        assert sms_service.format_phone_number(inp) == expected

    def test_E_with_dashes_and_brackets(self):
        assert sms_service.format_phone_number("(07123) 456-789") == "447123456789"


class TestValidatePhoneNumber:
    def test_H_valid_mobile(self):
        assert sms_service.validate_phone_number("07123456789") is True

    def test_U_too_short(self):
        assert sms_service.validate_phone_number("0712") is False

    def test_B_min_length(self):
        # 44 + 9 digits = 11 chars (minimum accepted)
        assert sms_service.validate_phone_number("447" + "1" * 8) is True

    def test_B_max_length_plus_one(self):
        # > 13 chars rejected
        assert sms_service.validate_phone_number("44" + "1" * 12) is False


# ============================================================================
# render_template
# ============================================================================

class TestRenderTemplate:
    def test_H_substitutes_double_brace(self):
        out = sms_service.render_template("Hi {{first_name}}", {"first_name": "Jo"})
        assert out == "Hi Jo"

    def test_H_substitutes_spaced_format(self):
        out = sms_service.render_template("Hi {{ first_name }}", {"first_name": "Jo"})
        assert out == "Hi Jo"

    def test_E_missing_value_becomes_empty(self):
        out = sms_service.render_template("Hi {{first_name}}", {"first_name": None})
        assert out == "Hi "

    def test_E_unrecognised_placeholder_preserved(self):
        out = sms_service.render_template("Hi {{first_name}} {{unknown}}", {"first_name": "Jo"})
        assert out == "Hi Jo {{unknown}}"


# ============================================================================
# get_booking_variables
# ============================================================================

class TestGetBookingVariables:
    def test_H_full_booking(self):
        b = _booking()
        v = sms_service.get_booking_variables(b)
        assert v["first_name"] == "Jo"
        assert v["booking_reference"] == "TAG-1"
        assert v["dropoff_date"] == "01/06/2026"
        assert v["dropoff_time"] == "10:00"
        assert v["pickup_date"] == "08/06/2026"
        assert v["days"] == "7"
        assert v["total_price"] == "£99.00"
        assert v["vehicle_reg"] == "AB12CDE"

    def test_E_no_customer_uses_snapshot(self):
        b = _booking()
        b.customer = None  # but snapshot fields remain
        v = sms_service.get_booking_variables(b)
        assert v["first_name"] == "Jo"
        assert v["vehicle_reg"] == "AB12CDE"  # vehicle still there

    def test_E_no_vehicle(self):
        b = _booking()
        b.vehicle = None
        v = sms_service.get_booking_variables(b)
        assert v["vehicle_reg"] == ""

    def test_E_no_payment(self):
        b = _booking()
        b.payment = None
        v = sms_service.get_booking_variables(b)
        assert v["total_price"] == ""

    def test_E_no_dates(self):
        b = _booking()
        b.dropoff_date = None
        b.pickup_date = None
        v = sms_service.get_booking_variables(b)
        assert v["dropoff_date"] == ""
        assert v["pickup_date"] == ""
        assert v["days"] == "0"


# ============================================================================
# send_sms — the async core
# ============================================================================

class TestSendSms:
    async def test_H_returns_success_on_200(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(200, {"messageid": "msg-42"}))
        result = await sms_service.send_sms(phone="07123456789", content="Hi")
        assert result["success"] is True
        assert result["message_id"] == "msg-42"
        assert result["phone"] == "447123456789"

    async def test_H_returns_success_on_201(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(201, {"messageid": "msg-2"}))
        result = await sms_service.send_sms(phone="07123456789", content="Hi")
        assert result["success"] is True

    async def test_U_sms_disabled(self, monkeypatch):
        _disable_sms(monkeypatch)
        result = await sms_service.send_sms(phone="07123456789", content="Hi")
        assert result["success"] is False
        assert "disabled" in result["error"].lower()

    async def test_U_invalid_phone(self, monkeypatch):
        _enable_sms(monkeypatch)
        result = await sms_service.send_sms(phone="abc", content="Hi")
        assert result["success"] is False
        assert "invalid uk phone" in result["error"].lower()

    async def test_U_no_token(self, monkeypatch):
        monkeypatch.setattr(sms_service, "SMS_ENABLED", True)
        monkeypatch.setattr(sms_service, "SMS_JWT_TOKEN", "")
        # is_sms_enabled false because token empty — covers earlier branch
        result = await sms_service.send_sms(phone="07123456789", content="Hi")
        assert result["success"] is False

    async def test_U_api_non_2xx(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(500, text="Server boom"))
        result = await sms_service.send_sms(phone="07123456789", content="Hi")
        assert result["success"] is False
        assert "500" in result["error"]

    async def test_U_exception_caught(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, raise_exc=RuntimeError("network down"))
        result = await sms_service.send_sms(phone="07123456789", content="Hi")
        assert result["success"] is False
        assert "network down" in result["error"]

    async def test_E_with_db_session_records_message(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(200, {"messageid": "msg-9"}))

        db = MagicMock()
        added = []
        def add(obj):
            obj.id = 999
            added.append(obj)
        db.add.side_effect = add

        result = await sms_service.send_sms(
            phone="07123456789", content="Hi", booking_id=1, db_session=db
        )
        assert result["success"] is True
        assert result["sms_record_id"] == 999
        assert len(added) == 1
        assert added[0].provider_message_id == "msg-9"

    async def test_E_db_session_marks_failed_on_non_2xx(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(500, text="Boom"))

        db = MagicMock()
        def add(obj):
            obj.id = 100
        db.add.side_effect = add

        result = await sms_service.send_sms(
            phone="07123456789", content="Hi", db_session=db
        )
        assert result["success"] is False
        # DB write should have happened (status -> FAILED + commit)
        assert db.commit.called

    async def test_E_db_session_marks_failed_on_exception(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, raise_exc=RuntimeError("boom"))

        db = MagicMock()
        def add(obj):
            obj.id = 200
        db.add.side_effect = add

        result = await sms_service.send_sms(
            phone="07123456789", content="Hi", db_session=db
        )
        assert result["success"] is False
        assert db.commit.called


# ============================================================================
# send_bulk_sms
# ============================================================================

class TestSendBulkSms:
    async def test_H_all_succeed(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(200, {"messageid": "m"}))
        messages = [
            {"phone": "07123456789", "content": "Hi 1"},
            {"phone": "07123456788", "content": "Hi 2"},
        ]
        result = await sms_service.send_bulk_sms(messages)
        assert result["sent"] == 2
        assert result["failed"] == 0
        assert result["success"] is True

    async def test_U_disabled_returns_failure_envelope(self, monkeypatch):
        _disable_sms(monkeypatch)
        result = await sms_service.send_bulk_sms([{"phone": "07123456789", "content": "x"}])
        assert result["success"] is False
        assert result["sent"] == 0

    async def test_E_partial_failure_still_success(self, monkeypatch):
        """If at least one sent, success stays True."""
        _enable_sms(monkeypatch)
        # Alternate good/bad: first 200, second 500
        responses = [_FakeResp(200, {"messageid": "m1"}), _FakeResp(500, text="x")]
        idx = {"n": 0}
        async def fake_post(*a, **kw):
            r = responses[idx["n"] % len(responses)]
            idx["n"] += 1
            return r

        client = MagicMock()
        client.post = AsyncMock(side_effect=fake_post)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr("sms_service.httpx.AsyncClient", MagicMock(return_value=cm))

        result = await sms_service.send_bulk_sms([
            {"phone": "07123456789", "content": "Hi 1"},
            {"phone": "07123456788", "content": "Hi 2"},
        ])
        assert result["sent"] == 1
        assert result["failed"] == 1
        assert result["success"] is True  # any success keeps envelope True

    async def test_B_all_fail_flips_success_to_false(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(500, text="Boom"))
        result = await sms_service.send_bulk_sms([
            {"phone": "07123456789", "content": "Hi 1"},
            {"phone": "07123456788", "content": "Hi 2"},
        ])
        assert result["sent"] == 0
        assert result["failed"] == 2
        assert result["success"] is False

    async def test_B_empty_message_list(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch)  # not actually called
        result = await sms_service.send_bulk_sms([])
        assert result["sent"] == 0
        assert result["failed"] == 0
        assert result["success"] is True


# ============================================================================
# Templated wrappers: confirmation / reminder / thank_you
# ============================================================================

def _make_db_with_template(template_content="Hi {{first_name}} — ref {{booking_reference}}"):
    db = MagicMock()
    template = SimpleNamespace(content=template_content, id=7)
    db.query.return_value.filter.return_value.first.return_value = template
    return db


class TestSendBookingConfirmationSms:
    async def test_H_sends(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(200, {"messageid": "m"}))
        db = _make_db_with_template()
        b = _booking()
        ok = await sms_service.send_booking_confirmation_sms(b, db)
        assert ok is True

    async def test_U_sms_disabled(self, monkeypatch):
        _disable_sms(monkeypatch)
        db = _make_db_with_template()
        ok = await sms_service.send_booking_confirmation_sms(_booking(), db)
        assert ok is False

    async def test_U_no_customer_phone(self, monkeypatch):
        _enable_sms(monkeypatch)
        b = _booking()
        b.customer = None
        ok = await sms_service.send_booking_confirmation_sms(b, _make_db_with_template())
        assert ok is False

    async def test_U_no_template_in_db(self, monkeypatch):
        _enable_sms(monkeypatch)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        ok = await sms_service.send_booking_confirmation_sms(_booking(), db)
        assert ok is False


class TestSendReminder2DaySms:
    async def test_H_sends(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(200, {"messageid": "m"}))
        ok = await sms_service.send_reminder_2day_sms(_booking(), _make_db_with_template())
        assert ok is True

    async def test_U_disabled(self, monkeypatch):
        _disable_sms(monkeypatch)
        ok = await sms_service.send_reminder_2day_sms(_booking(), _make_db_with_template())
        assert ok is False

    async def test_U_no_phone(self, monkeypatch):
        _enable_sms(monkeypatch)
        b = _booking()
        b.customer = None
        ok = await sms_service.send_reminder_2day_sms(b, _make_db_with_template())
        assert ok is False

    async def test_U_no_template(self, monkeypatch):
        _enable_sms(monkeypatch)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        ok = await sms_service.send_reminder_2day_sms(_booking(), db)
        assert ok is False


class TestSendParkingUpdateSms:
    async def test_H_uses_parking_update_trigger_template(self, monkeypatch):
        _enable_sms(monkeypatch)
        sent = {}

        async def fake_send_sms(**kw):
            sent.update(kw)
            return {"success": True}

        monkeypatch.setattr(sms_service, "send_sms", fake_send_sms)
        db = _make_db_with_template("Hi {{first_name}}, parking update for {{booking_reference}}")
        ok = await sms_service.send_parking_update_sms(_booking(), db)

        assert ok is True
        assert sent["content"] == "Hi Jo, parking update for TAG-1"
        assert sent["template_id"] == 7
        assert sent["tag"] == "parking-update"

    async def test_H_falls_back_to_car_parking_charges_template_name(self, monkeypatch):
        _enable_sms(monkeypatch)
        sent = {}

        async def fake_send_sms(**kw):
            sent.update(kw)
            return {"success": True}

        template = SimpleNamespace(content="Car charges {{booking_reference}}", id=44)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [None, template]
        monkeypatch.setattr(sms_service, "send_sms", fake_send_sms)

        ok = await sms_service.send_parking_update_sms(_booking(), db)

        assert ok is True
        assert sent["content"] == "Car charges TAG-1"
        assert sent["template_id"] == 44

    async def test_H_uses_default_copy_when_template_missing(self, monkeypatch):
        _enable_sms(monkeypatch)
        sent = {}

        async def fake_send_sms(**kw):
            sent.update(kw)
            return {"success": True}

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        monkeypatch.setattr(sms_service, "send_sms", fake_send_sms)

        ok = await sms_service.send_parking_update_sms(_booking(reference="TAG-XYZ"), db)

        assert ok is True
        assert "TAG-XYZ" in sent["content"]
        assert sent["template_id"] is None


class TestSendThankYouSms:
    async def test_H_sends(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(200, {"messageid": "m"}))
        ok = await sms_service.send_thank_you_sms(_booking(), _make_db_with_template())
        assert ok is True

    async def test_U_disabled(self, monkeypatch):
        _disable_sms(monkeypatch)
        ok = await sms_service.send_thank_you_sms(_booking(), _make_db_with_template())
        assert ok is False

    async def test_U_no_phone(self, monkeypatch):
        _enable_sms(monkeypatch)
        b = _booking()
        b.customer = None
        ok = await sms_service.send_thank_you_sms(b, _make_db_with_template())
        assert ok is False

    async def test_U_no_template(self, monkeypatch):
        _enable_sms(monkeypatch)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        ok = await sms_service.send_thank_you_sms(_booking(), db)
        assert ok is False


# ============================================================================
# handle_delivery_report
# ============================================================================

class TestHandleDeliveryReport:
    def _db_with_record(self, record):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = record
        return db

    def test_H_delivered_updates_status(self):
        rec = MagicMock()
        rec.status = None
        rec.delivered_at = None
        db = self._db_with_record(rec)
        ok = sms_service.handle_delivery_report(
            {"messageid": "m1", "status": "delivered"}, db
        )
        assert ok is True
        assert rec.delivered_at is not None
        assert db.commit.called

    def test_H_failed_sets_detail(self):
        rec = MagicMock()
        db = self._db_with_record(rec)
        ok = sms_service.handle_delivery_report(
            {"messageid": "m1", "status": "failed", "failurereason": "Number invalid"}, db
        )
        assert ok is True
        assert "Number invalid" in (rec.status_detail or "")

    def test_H_rejected_maps_to_failed(self):
        rec = MagicMock()
        db = self._db_with_record(rec)
        ok = sms_service.handle_delivery_report(
            {"messageid": "m1", "status": "rejected"}, db
        )
        assert ok is True

    def test_U_missing_message_id(self):
        ok = sms_service.handle_delivery_report({"status": "delivered"}, MagicMock())
        assert ok is False

    def test_U_record_not_found(self):
        db = self._db_with_record(None)
        ok = sms_service.handle_delivery_report(
            {"messageid": "missing", "status": "delivered"}, db
        )
        assert ok is False

    def test_E_unknown_status_returns_false(self):
        rec = MagicMock()
        db = self._db_with_record(rec)
        ok = sms_service.handle_delivery_report(
            {"messageid": "m1", "status": "unknown_value"}, db
        )
        assert ok is False


# ============================================================================
# check_message_status / refresh_message_statuses
# ============================================================================

class TestCheckMessageStatus:
    async def test_H_returns_json(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(200, {"status": "delivered"}), method="get")
        result = await sms_service.check_message_status("m1")
        assert result == {"status": "delivered"}

    async def test_U_disabled(self, monkeypatch):
        _disable_sms(monkeypatch)
        assert await sms_service.check_message_status("m1") is None

    async def test_U_non_200(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(500), method="get")
        assert await sms_service.check_message_status("m1") is None

    async def test_U_exception(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, raise_exc=RuntimeError("boom"), method="get")
        assert await sms_service.check_message_status("m1") is None


class TestRefreshMessageStatuses:
    async def test_H_updates_delivered(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(200, {"status": "delivered"}), method="get")

        msg = MagicMock()
        msg.provider_message_id = "m1"
        msg.status = None  # so new_status != msg.status
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [msg]

        result = await sms_service.refresh_message_statuses(db)
        assert result["success"] is True
        assert result["updated"] == 1
        assert result["total"] == 1

    async def test_U_disabled(self, monkeypatch):
        _disable_sms(monkeypatch)
        result = await sms_service.refresh_message_statuses(MagicMock())
        assert result["success"] is False

    async def test_E_no_pending_messages(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(monkeypatch, resp=_FakeResp(200, {"status": "delivered"}), method="get")
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        result = await sms_service.refresh_message_statuses(db)
        assert result["total"] == 0
        assert result["updated"] == 0

    async def test_E_failed_lookup_increments_failed_counter(self, monkeypatch):
        _enable_sms(monkeypatch)
        # check_message_status returns None when API non-200
        _patch_httpx(monkeypatch, resp=_FakeResp(500), method="get")
        msg = MagicMock()
        msg.provider_message_id = "m1"
        msg.status = None
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [msg]
        result = await sms_service.refresh_message_statuses(db)
        assert result["failed"] == 1

    async def test_E_failed_status_with_dict_failurereason(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(
            monkeypatch,
            resp=_FakeResp(200, {"status": "failed", "failurereason": {"details": "carrier blocked"}}),
            method="get",
        )
        msg = MagicMock()
        msg.provider_message_id = "m1"
        msg.status = None
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [msg]
        result = await sms_service.refresh_message_statuses(db)
        assert result["updated"] == 1
        assert "carrier blocked" in (msg.status_detail or "")

    async def test_E_failed_status_with_string_failurereason(self, monkeypatch):
        _enable_sms(monkeypatch)
        _patch_httpx(
            monkeypatch,
            resp=_FakeResp(200, {"status": "failed", "failurereason": "Number invalid"}),
            method="get",
        )
        msg = MagicMock()
        msg.provider_message_id = "m1"
        msg.status = None
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [msg]
        result = await sms_service.refresh_message_statuses(db)
        assert result["updated"] == 1


# ============================================================================
# handle_incoming_sms
# ============================================================================

class TestHandleIncomingSms:
    def test_H_creates_inbound_record_with_known_customer(self):
        customer = SimpleNamespace(id=42)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = customer
        added = []
        db.add.side_effect = added.append
        ok = sms_service.handle_incoming_sms(
            {"from": "07123456789", "content": "Hello", "messageid": "in-1"}, db
        )
        assert ok is True
        assert added and added[0].customer_id == 42
        assert added[0].content == "Hello"
        assert db.commit.called

    def test_H_creates_record_when_no_customer_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        added = []
        db.add.side_effect = added.append
        ok = sms_service.handle_incoming_sms(
            {"sender": "07123456789", "content": "Hi", "messageid": "in-2"}, db
        )
        assert ok is True
        assert added and added[0].customer_id is None

    def test_U_missing_sender(self):
        ok = sms_service.handle_incoming_sms({"content": "no sender"}, MagicMock())
        assert ok is False

    def test_E_sender_fallback_field(self):
        """When 'from' missing, 'sender' is the fallback."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        added = []
        db.add.side_effect = added.append
        ok = sms_service.handle_incoming_sms(
            {"sender": "07999000000", "content": "x", "messageid": "in-3"}, db
        )
        assert ok is True


# ============================================================================
# get_template_variables_list
# ============================================================================

class TestGetTemplateVariablesList:
    def test_H_returns_full_list(self):
        out = sms_service.get_template_variables_list()
        names = {item["name"] for item in out}
        assert "first_name" in names
        assert "booking_reference" in names
        assert "google_review_link" in names
        for item in out:
            assert "description" in item
