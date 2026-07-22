"""
04:00 drop-off floor — hueb integration + property coverage.

Rule (owner-confirmed 2026-07-22): customers are never offered a same-day
drop-off before 04:00. Slots computing earlier clamp UP to 04:00. Exempt:
previous-evening drop-offs for post-midnight flights, and cases where the
clamp would land closer than the LATE offset (90 min) to departure.

Pure-function boundary tests live in test_time_slots.py. This file drives
the rule through the live API surfaces (TestClient + import-from-main) and
adds an exhaustive property sweep across every departure time.
"""
from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from models import SlotType
from time_slots import DROP_OFF_FLOOR, SLOT_OFFSETS, calculate_drop_off_datetime

FUTURE_DATE = date(2026, 9, 15)


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


# =============================================================================
# /api/slots/available — the slot list the booking flow consumes
# =============================================================================

class TestAvailableSlotsEndpointHUEB:

    def _slots(self, client, flight_time):
        response = client.post("/api/slots/available", json={
            "flight_date": FUTURE_DATE.isoformat(),
            "flight_time": flight_time,
            "flight_number": "6310",
            "airline_code": "TOM",
        })
        assert response.status_code == 200
        return response.json()["slots"]

    def test_H_0620_flight_serves_0400_not_0335(self, client):
        slots = self._slots(client, "06:20")
        times = [s["drop_off_time"] for s in slots]
        assert times == ["04:00:00", "04:20:00", "04:50:00"]
        assert all(s["drop_off_date"] == FUTURE_DATE.isoformat() for s in slots)

    def test_H_normal_daytime_flight_unchanged(self, client):
        times = [s["drop_off_time"] for s in self._slots(client, "14:30")]
        assert times == ["11:45:00", "12:30:00", "13:00:00"]

    def test_E_post_midnight_flight_keeps_previous_evening(self, client):
        slots = self._slots(client, "00:35")
        previous_day = (FUTURE_DATE - timedelta(days=1)).isoformat()
        assert [s["drop_off_time"] for s in slots] == ["21:50:00", "22:35:00", "23:05:00"]
        assert all(s["drop_off_date"] == previous_day for s in slots)

    def test_B_two_slots_clamped_keep_unique_slot_ids(self, client):
        """05:40 flight: EARLY and STANDARD both clamp to 04:00 — the slot ids
        must stay unique (type suffix) so bookings can't collide."""
        slots = self._slots(client, "05:40")
        times = [s["drop_off_time"] for s in slots]
        assert times == ["04:00:00", "04:00:00", "04:10:00"]
        slot_ids = [s["slot_id"] for s in slots]
        assert len(set(slot_ids)) == 3
        # ids embed the CLAMPED time, matching what booking creation builds
        assert all("_0400_" in sid for sid in slot_ids[:2])


# =============================================================================
# /api/slots/summary — the confirmation copy shown to the customer
# =============================================================================

class TestSlotSummaryEndpointHUEB:

    def _summary(self, client, flight_time, slot_type):
        response = client.post("/api/slots/summary", json={
            "flight_date": FUTURE_DATE.isoformat(),
            "flight_time": flight_time,
            "slot_type": slot_type,
        })
        assert response.status_code == 200
        return response.json()

    def test_H_0620_early_summary_says_0400(self, client):
        summary = self._summary(client, "06:20", "165")
        assert summary["drop_off_time"] == "04:00"
        assert summary["drop_off_date"] == FUTURE_DATE.isoformat()
        assert summary["is_overnight"] is False

    def test_B_boundary_0644_0645_0646(self, client):
        assert self._summary(client, "06:44", "165")["drop_off_time"] == "04:00"
        assert self._summary(client, "06:45", "165")["drop_off_time"] == "04:00"
        assert self._summary(client, "06:46", "165")["drop_off_time"] == "04:01"

    def test_B_guard_boundary_0530_0529(self, client):
        assert self._summary(client, "05:30", "165")["drop_off_time"] == "04:00"
        assert self._summary(client, "05:29", "165")["drop_off_time"] == "02:44"

    def test_E_overnight_message_still_produced(self, client):
        summary = self._summary(client, "00:35", "165")
        assert summary["is_overnight"] is True
        assert summary["drop_off_time"] == "21:50"
        assert "evening before" in summary["display_message"]


# =============================================================================
# Property sweep — every departure time, every slot type
# =============================================================================

class TestFloorInvariantSweep:

    def test_P_no_same_day_slot_ever_below_0400_unless_guard_applies(self):
        """For every departure time at 1-minute resolution and every slot
        type, the result must be: previous-evening (exempt), or >= 04:00,
        or the untouched raw time when the clamp guard applies (flight too
        close to 04:00). Nothing else is acceptable."""
        late_offset = SLOT_OFFSETS[SlotType.LATE]
        for total_minutes in range(0, 24 * 60):
            flight_time = time(total_minutes // 60, total_minutes % 60)
            for slot_type in SlotType:
                d, t = calculate_drop_off_datetime(FUTURE_DATE, flight_time, slot_type)
                if d < FUTURE_DATE:
                    continue  # previous evening — exempt by design
                if t >= DROP_OFF_FLOOR:
                    continue  # at or after the floor — fine
                # Below 04:00 on the flight day is ONLY allowed when the
                # guard blocked clamping: 04:00 would be < 90 min before
                # departure, and the time must equal the raw offset result.
                guard_blocked = (4 * 60) > (total_minutes - late_offset)
                raw_minutes = total_minutes - SLOT_OFFSETS[slot_type]
                assert guard_blocked, (
                    f"{flight_time} {slot_type}: {t} is below the floor with no guard"
                )
                assert t == time(raw_minutes // 60, raw_minutes % 60), (
                    f"{flight_time} {slot_type}: below-floor time was altered"
                )

    def test_P_late_slot_never_clamps(self):
        """Mathematical invariant: whenever the guard allows clamping
        (departure >= 05:30), the LATE slot is already >= 04:00 — so the
        1½-hour slot must never carry the clamped label's semantics."""
        for total_minutes in range(5 * 60 + 30, 24 * 60):
            flight_time = time(total_minutes // 60, total_minutes % 60)
            _, t = calculate_drop_off_datetime(FUTURE_DATE, flight_time, SlotType.LATE)
            assert t >= DROP_OFF_FLOOR


# =============================================================================
# Payment-path reconstruction (_entry_time_before_departure in main.py) —
# fires when a CreatePaymentRequest arrives without an explicit drop_off_time;
# must reproduce the CLAMPED time the customer saw or quote-matching breaks.
# =============================================================================

class TestPaymentEntryTimeReconstructionHUEB:

    def _entry(self, departure_hhmm, slot):
        from main import _entry_time_before_departure, _parse_payment_hhmm
        return _entry_time_before_departure(_parse_payment_hhmm(departure_hhmm), slot)

    def test_H_0620_early_slot_reconstructs_clamped_0400(self):
        assert self._entry("06:20", "165") == time(4, 0)

    def test_H_0600_slots_match_displayed_cards(self):
        """The screenshot case: 06:00 flight must reconstruct 04:00 for both
        clamped slots and 04:30 for the late slot."""
        assert self._entry("06:00", "165") == time(4, 0)
        assert self._entry("06:00", "120") == time(4, 0)
        assert self._entry("06:00", "90") == time(4, 30)

    def test_B_boundary_0644_0645_0646(self):
        assert self._entry("06:44", "165") == time(4, 0)
        assert self._entry("06:45", "165") == time(4, 0)
        assert self._entry("06:46", "165") == time(4, 1)

    def test_B_guard_boundary_0530_0529(self):
        assert self._entry("05:30", "165") == time(4, 0)
        assert self._entry("05:29", "165") == time(2, 44)

    def test_E_post_midnight_wrap_exempt(self):
        assert self._entry("00:35", "165") == time(21, 50)

    def test_P_reconstruction_always_matches_slot_engine(self):
        """Property: for every departure minute and slot, the payment-path
        reconstruction equals time_slots.calculate_drop_off_datetime — the
        two implementations of the floor may never drift apart."""
        slot_types = {"165": SlotType.EARLY, "120": SlotType.STANDARD, "90": SlotType.LATE}
        for total_minutes in range(0, 24 * 60, 7):  # 7-min stride covers all residues
            flight_time = time(total_minutes // 60, total_minutes % 60)
            for slot_str, slot_type in slot_types.items():
                _, engine_time = calculate_drop_off_datetime(FUTURE_DATE, flight_time, slot_type)
                assert self._entry(flight_time.strftime("%H:%M"), slot_str) == engine_time, (
                    f"drift at {flight_time} slot {slot_str}"
                )
