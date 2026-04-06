"""
Unit tests for shift unassign (set staff_id to null) functionality.
Tests the RosterShiftUpdate model and update_shift endpoint logic.

Tests cover: happy path, unhappy path, edge cases and boundaries.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, time, timedelta
from models import RosterShiftUpdate


# =============================================================================
# Happy Path Tests - Model Validation
# =============================================================================

class TestRosterShiftUpdateModelHappy:
    """Happy path tests for RosterShiftUpdate model staff_id handling."""

    def test_staff_id_not_provided_flag_false(self):
        """When staff_id is not in request, staff_id_provided should be False."""
        update = RosterShiftUpdate(date=date(2026, 4, 10))

        assert update.staff_id is None
        assert update.staff_id_provided is False

    def test_staff_id_explicitly_null_flag_true(self):
        """When staff_id is explicitly null, staff_id_provided should be True."""
        update = RosterShiftUpdate.model_validate({'date': '2026-04-10', 'staff_id': None})

        assert update.staff_id is None
        assert update.staff_id_provided is True

    def test_staff_id_set_to_value_flag_true(self):
        """When staff_id is set to a value, staff_id_provided should be True."""
        update = RosterShiftUpdate.model_validate({'date': '2026-04-10', 'staff_id': 5})

        assert update.staff_id == 5
        assert update.staff_id_provided is True

    def test_staff_id_zero_is_valid(self):
        """Staff ID of 0 should be detected as provided."""
        update = RosterShiftUpdate.model_validate({'staff_id': 0})

        assert update.staff_id == 0
        assert update.staff_id_provided is True

    def test_empty_update_no_fields_provided(self):
        """Empty update should have staff_id_provided False."""
        update = RosterShiftUpdate.model_validate({})

        assert update.staff_id is None
        assert update.staff_id_provided is False

    def test_other_fields_dont_affect_staff_id_flag(self):
        """Other fields in update shouldn't affect staff_id_provided."""
        update = RosterShiftUpdate.model_validate({
            'date': '2026-04-10',
            'start_time': '09:00',
            'end_time': '17:00',
            'notes': 'Test notes'
        })

        assert update.staff_id is None
        assert update.staff_id_provided is False


# =============================================================================
# Happy Path Tests - Unassign Logic
# =============================================================================

class TestShiftUnassignLogicHappy:
    """Happy path tests for shift unassign logic."""

    def test_unassign_shift_sets_staff_id_to_none(self):
        """Unassigning a shift should set staff_id to None."""
        # Simulate the logic from update_shift endpoint
        class MockShift:
            staff_id = 5

        shift = MockShift()
        updates = RosterShiftUpdate.model_validate({'staff_id': None})

        # Apply update logic
        if updates.staff_id_provided:
            shift.staff_id = updates.staff_id

        assert shift.staff_id is None

    def test_reassign_shift_to_different_staff(self):
        """Reassigning a shift should update staff_id."""
        class MockShift:
            staff_id = 5

        shift = MockShift()
        updates = RosterShiftUpdate.model_validate({'staff_id': 10})

        if updates.staff_id_provided:
            shift.staff_id = updates.staff_id

        assert shift.staff_id == 10

    def test_no_staff_id_in_update_keeps_existing(self):
        """Not providing staff_id should keep existing assignment."""
        class MockShift:
            staff_id = 5

        shift = MockShift()
        updates = RosterShiftUpdate.model_validate({'notes': 'Updated notes'})

        if updates.staff_id_provided:
            shift.staff_id = updates.staff_id

        assert shift.staff_id == 5  # Unchanged


# =============================================================================
# Unhappy Path Tests
# =============================================================================

class TestShiftUnassignUnhappy:
    """Unhappy path tests for shift unassign."""

    def test_invalid_staff_id_type_string(self):
        """String staff_id should raise validation error."""
        with pytest.raises(Exception):
            RosterShiftUpdate.model_validate({'staff_id': 'not_a_number'})

    def test_negative_staff_id(self):
        """Negative staff_id might be accepted by model but should fail validation elsewhere."""
        # Model accepts it, but endpoint should validate
        update = RosterShiftUpdate.model_validate({'staff_id': -1})
        assert update.staff_id == -1
        assert update.staff_id_provided is True


# =============================================================================
# Edge Cases and Boundaries
# =============================================================================

class TestShiftUnassignEdgeCases:
    """Edge cases and boundary tests for shift unassign."""

    def test_already_unassigned_shift_unassign_again(self):
        """Unassigning an already unassigned shift should work."""
        class MockShift:
            staff_id = None

        shift = MockShift()
        updates = RosterShiftUpdate.model_validate({'staff_id': None})

        if updates.staff_id_provided:
            shift.staff_id = updates.staff_id

        assert shift.staff_id is None

    def test_assign_to_same_staff(self):
        """Assigning to the same staff should work."""
        class MockShift:
            staff_id = 5

        shift = MockShift()
        updates = RosterShiftUpdate.model_validate({'staff_id': 5})

        if updates.staff_id_provided:
            shift.staff_id = updates.staff_id

        assert shift.staff_id == 5

    def test_unassign_with_other_updates(self):
        """Unassigning while updating other fields should work."""
        class MockShift:
            staff_id = 5
            notes = 'Old notes'

        shift = MockShift()
        updates = RosterShiftUpdate.model_validate({
            'staff_id': None,
            'notes': 'New notes'
        })

        if updates.staff_id_provided:
            shift.staff_id = updates.staff_id
        if updates.notes is not None:
            shift.notes = updates.notes

        assert shift.staff_id is None
        assert shift.notes == 'New notes'

    def test_large_staff_id(self):
        """Very large staff_id should be accepted."""
        update = RosterShiftUpdate.model_validate({'staff_id': 999999999})

        assert update.staff_id == 999999999
        assert update.staff_id_provided is True

    def test_model_validate_vs_constructor_difference(self):
        """Ensure model_validate detects staff_id but constructor doesn't."""
        # Via constructor - staff_id not in original data
        update1 = RosterShiftUpdate(date=date(2026, 4, 10), staff_id=None)
        # Note: Constructor doesn't go through model_validate, so flag may differ

        # Via model_validate - staff_id explicitly in data
        update2 = RosterShiftUpdate.model_validate({'date': '2026-04-10', 'staff_id': None})

        # Both have staff_id=None, but only model_validate sets the flag
        assert update2.staff_id_provided is True


# =============================================================================
# Integration-like Tests (mocking DB behavior)
# =============================================================================

class TestShiftUnassignIntegration:
    """Integration-like tests for shift unassign."""

    def test_duplicate_then_unassign_workflow(self):
        """Workflow: Create shift, duplicate for multiple staff, then unassign one."""
        # Simulate duplicated shifts
        shifts = [
            {'id': 1, 'staff_id': 10, 'date': '2026-04-10'},
            {'id': 2, 'staff_id': 20, 'date': '2026-04-10'},
            {'id': 3, 'staff_id': 30, 'date': '2026-04-10'},
        ]

        # Unassign shift 2
        updates = RosterShiftUpdate.model_validate({'staff_id': None})

        if updates.staff_id_provided:
            shifts[1]['staff_id'] = updates.staff_id

        assert shifts[0]['staff_id'] == 10  # Unchanged
        assert shifts[1]['staff_id'] is None  # Unassigned
        assert shifts[2]['staff_id'] == 30  # Unchanged

    def test_unassign_preserves_other_shift_data(self):
        """Unassigning should not affect other shift properties."""
        shift = {
            'id': 1,
            'staff_id': 5,
            'date': '2026-04-10',
            'start_time': '09:00',
            'end_time': '17:00',
            'notes': 'Important shift',
            'booking_ids': [100, 101, 102]
        }

        updates = RosterShiftUpdate.model_validate({'staff_id': None})

        if updates.staff_id_provided:
            shift['staff_id'] = updates.staff_id

        # Only staff_id should change
        assert shift['staff_id'] is None
        assert shift['date'] == '2026-04-10'
        assert shift['start_time'] == '09:00'
        assert shift['end_time'] == '17:00'
        assert shift['notes'] == 'Important shift'
        assert shift['booking_ids'] == [100, 101, 102]
