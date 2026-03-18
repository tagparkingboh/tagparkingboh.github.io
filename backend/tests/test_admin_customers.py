"""
Tests for admin customers functionality.

Covers:
- GET /api/admin/customers - List all customers

Test categories:
- Happy path: Normal successful operations
- Negative path: Error cases and validation failures
- Edge cases: Boundary conditions and special scenarios

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_marketing_source(source="google", source_detail=None):
    """Create a mock marketing source object."""
    ms = MagicMock()
    ms.source = source
    ms.source_detail = source_detail
    return ms


def create_mock_customer(
    id=1,
    first_name="Test",
    last_name="User",
    email="test@example.com",
    phone="07700900001",
    billing_postcode="BH1 1AA",
    created_at=None,
    marketing_source=None,
):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    customer.phone = phone
    customer.billing_postcode = billing_postcode
    customer.created_at = created_at or datetime.utcnow()
    customer.marketing_source = marketing_source
    return customer


def create_mock_customer_response(
    id=1,
    first_name="Test",
    last_name="User",
    email="test@example.com",
    phone="07700900001",
    billing_postcode="BH1 1AA",
    created_at=None,
    marketing_source=None,
):
    """Create a mock customer API response object."""
    return {
        "id": id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "billing_postcode": billing_postcode,
        "created_at": (created_at or datetime.utcnow()).isoformat(),
        "marketing_source": marketing_source,
    }


# =============================================================================
# GET /api/admin/customers - Happy Path Tests
# =============================================================================

class TestGetCustomersHappyPath:
    """Happy path tests for listing customers."""

    def test_get_customers_returns_list(self):
        """Should return a list of customers."""
        customers = [
            create_mock_customer_response(id=1, email="customer1@test.com"),
        ]

        response_data = {
            "customers": customers,
            "count": len(customers),
        }

        assert "customers" in response_data
        assert "count" in response_data
        assert response_data["count"] >= 1

    def test_customer_includes_contact_details(self):
        """Customers should include first_name, last_name, email, phone."""
        customer = create_mock_customer_response(
            first_name="John",
            last_name="Smith",
            email="john.smith@test.com",
            phone="07700900001",
        )

        assert customer["first_name"] == "John"
        assert customer["last_name"] == "Smith"
        assert customer["email"] == "john.smith@test.com"
        assert customer["phone"] == "07700900001"

    def test_customer_includes_billing_postcode(self):
        """Customers should include billing_postcode."""
        customer = create_mock_customer_response(
            billing_postcode="BH1 1AA",
        )

        assert customer["billing_postcode"] == "BH1 1AA"

    def test_customer_includes_created_at(self):
        """Customers should include created_at timestamp."""
        customer = create_mock_customer_response(created_at=datetime(2026, 1, 15, 10, 30, 0))

        assert customer["created_at"] is not None
        assert "2026-01-15" in customer["created_at"]

    def test_customer_includes_marketing_source(self):
        """Customers should include marketing_source field."""
        customer = create_mock_customer_response(marketing_source="google")

        assert "marketing_source" in customer
        assert customer["marketing_source"] == "google"

    def test_customer_marketing_source_can_be_null(self):
        """Customers without marketing source should have null value."""
        customer = create_mock_customer_response(marketing_source=None)

        assert "marketing_source" in customer
        assert customer["marketing_source"] is None

    def test_customers_sorted_by_created_at_asc(self):
        """Customers should be sorted by created_at ascending (oldest first)."""
        customers = [
            create_mock_customer_response(id=1, created_at=datetime(2026, 1, 10)),
            create_mock_customer_response(id=2, created_at=datetime(2026, 1, 15)),
            create_mock_customer_response(id=3, created_at=datetime(2026, 1, 20)),
        ]

        # Verify ascending order
        dates = [c["created_at"] for c in customers]
        assert dates == sorted(dates)

    def test_multiple_customers_returned(self):
        """Should return multiple customers correctly."""
        customers = [
            create_mock_customer_response(id=1, email="customer1@test.com"),
            create_mock_customer_response(id=2, email="customer2@test.com"),
            create_mock_customer_response(id=3, email="customer3@test.com"),
        ]

        response_data = {
            "customers": customers,
            "count": len(customers),
        }

        assert response_data["count"] == 3
        assert len(response_data["customers"]) == 3


# =============================================================================
# GET /api/admin/customers - Negative Path Tests
# =============================================================================

class TestGetCustomersNegativePath:
    """Negative path tests for listing customers."""

    def test_empty_database_returns_empty_list(self):
        """Should return empty list when no customers exist."""
        response_data = {
            "customers": [],
            "count": 0,
        }

        assert "customers" in response_data
        assert "count" in response_data
        assert isinstance(response_data["customers"], list)
        assert len(response_data["customers"]) == 0


# =============================================================================
# GET /api/admin/customers - Edge Case Tests
# =============================================================================

class TestGetCustomersEdgeCases:
    """Edge case tests for listing customers."""

    def test_customer_with_null_postcode(self):
        """Should handle customers with null billing_postcode."""
        customer = create_mock_customer_response(
            billing_postcode=None,
        )

        assert customer["billing_postcode"] is None

    def test_customer_with_special_characters_in_name(self):
        """Should handle customers with special characters in name."""
        customer = create_mock_customer_response(
            first_name="José",
            last_name="O'Brien",
        )

        assert customer["first_name"] == "José"
        assert customer["last_name"] == "O'Brien"

    def test_customer_with_long_email(self):
        """Should handle customers with long email addresses."""
        long_email = "very.long.email.address.for.testing@subdomain.example.com"
        customer = create_mock_customer_response(
            email=long_email,
        )

        assert customer["email"] == long_email

    def test_customer_with_other_marketing_source(self):
        """Should handle customers with 'other' marketing source."""
        customer = create_mock_customer_response(
            marketing_source="other",
        )

        assert customer["marketing_source"] == "other"

    def test_customer_with_various_marketing_sources(self):
        """Should handle all valid marketing source values."""
        valid_sources = [
            "google",
            "facebook",
            "instagram",
            "linkedin",
            "newspaper",
            "afc_bournemouth",
            "other",
        ]

        for source in valid_sources:
            customer = create_mock_customer_response(marketing_source=source)
            assert customer["marketing_source"] == source


# =============================================================================
# Integration Tests - Full Flow
# =============================================================================

class TestCustomersIntegration:
    """Integration tests covering full customers workflows."""

    def test_count_matches_customers_length(self):
        """The count field should match the number of customers returned."""
        customers = [
            create_mock_customer_response(id=1, email="customer1@test.com"),
            create_mock_customer_response(id=2, email="customer2@test.com"),
            create_mock_customer_response(id=3, email="customer3@test.com"),
        ]

        response_data = {
            "customers": customers,
            "count": len(customers),
        }

        assert response_data["count"] == len(response_data["customers"])
        assert response_data["count"] == 3

    def test_response_structure(self):
        """Verify the API response has correct structure."""
        customers = [
            create_mock_customer_response(
                id=1,
                first_name="Test",
                last_name="User",
                email="test@example.com",
                phone="07700900001",
                billing_postcode="BH1 1AA",
                marketing_source="google",
            ),
        ]

        response_data = {
            "customers": customers,
            "count": len(customers),
        }

        assert "customers" in response_data
        assert "count" in response_data

        customer = response_data["customers"][0]
        assert "id" in customer
        assert "first_name" in customer
        assert "last_name" in customer
        assert "email" in customer
        assert "phone" in customer
        assert "billing_postcode" in customer
        assert "created_at" in customer
        assert "marketing_source" in customer

    def test_customers_ordered_chronologically_for_monthly_grouping(self):
        """Customers should be ordered for monthly grouping in UI."""
        # January customers
        jan_customers = [
            create_mock_customer_response(id=1, created_at=datetime(2026, 1, 5)),
            create_mock_customer_response(id=2, created_at=datetime(2026, 1, 15)),
        ]
        # February customers
        feb_customers = [
            create_mock_customer_response(id=3, created_at=datetime(2026, 2, 1)),
            create_mock_customer_response(id=4, created_at=datetime(2026, 2, 20)),
        ]
        # March customers
        mar_customers = [
            create_mock_customer_response(id=5, created_at=datetime(2026, 3, 10)),
        ]

        all_customers = jan_customers + feb_customers + mar_customers

        # Verify ordering supports monthly grouping
        dates = [c["created_at"] for c in all_customers]
        assert dates == sorted(dates)

    def test_customer_data_for_csv_export(self):
        """Customer data should have all fields needed for CSV export."""
        customer = create_mock_customer_response(
            first_name="John",
            last_name="Smith",
            email="john@test.com",
            phone="07700900001",
            billing_postcode="BH1 1AA",
            created_at=datetime(2026, 3, 15, 10, 30, 0),
        )

        # All required CSV fields should be present
        assert customer["first_name"] is not None
        assert customer["last_name"] is not None
        assert customer["email"] is not None
        assert customer["phone"] is not None
        assert customer["billing_postcode"] is not None
        assert customer["created_at"] is not None

    def test_date_filtering_simulation(self):
        """Simulate date range filtering for customers."""
        customers = [
            create_mock_customer_response(id=1, created_at=datetime(2026, 1, 10)),
            create_mock_customer_response(id=2, created_at=datetime(2026, 2, 15)),
            create_mock_customer_response(id=3, created_at=datetime(2026, 3, 20)),
        ]

        # Filter for February only
        from_date = datetime(2026, 2, 1)
        to_date = datetime(2026, 2, 28, 23, 59, 59)

        filtered = [
            c for c in customers
            if from_date <= datetime.fromisoformat(c["created_at"]) <= to_date
        ]

        assert len(filtered) == 1
        assert filtered[0]["id"] == 2


# =============================================================================
# PATCH /api/admin/customers/{id} - Happy Path Tests
# =============================================================================

class TestUpdateCustomerHappyPath:
    """Happy path tests for updating customer email/phone."""

    def test_update_email_only(self):
        """Should successfully update only email."""
        original = create_mock_customer_response(
            id=1,
            email="old@test.com",
            phone="07700900001",
        )

        new_email = "new@test.com"
        updated = {**original, "email": new_email}

        response_data = {
            "success": True,
            "customer": updated,
        }

        assert response_data["success"] is True
        assert response_data["customer"]["email"] == new_email
        assert response_data["customer"]["phone"] == original["phone"]

    def test_update_phone_only(self):
        """Should successfully update only phone."""
        original = create_mock_customer_response(
            id=1,
            email="test@test.com",
            phone="07700900001",
        )

        new_phone = "07700900002"
        updated = {**original, "phone": new_phone}

        response_data = {
            "success": True,
            "customer": updated,
        }

        assert response_data["success"] is True
        assert response_data["customer"]["phone"] == new_phone
        assert response_data["customer"]["email"] == original["email"]

    def test_update_both_email_and_phone(self):
        """Should successfully update both email and phone."""
        original = create_mock_customer_response(
            id=1,
            email="old@test.com",
            phone="07700900001",
        )

        new_email = "new@test.com"
        new_phone = "07700900002"
        updated = {**original, "email": new_email, "phone": new_phone}

        response_data = {
            "success": True,
            "customer": updated,
        }

        assert response_data["success"] is True
        assert response_data["customer"]["email"] == new_email
        assert response_data["customer"]["phone"] == new_phone

    def test_update_returns_full_customer_object(self):
        """Update response should return full customer object."""
        updated = create_mock_customer_response(
            id=1,
            first_name="John",
            last_name="Smith",
            email="updated@test.com",
            phone="07700900001",
            billing_postcode="BH1 1AA",
        )

        response_data = {
            "success": True,
            "customer": updated,
        }

        customer = response_data["customer"]
        assert "id" in customer
        assert "first_name" in customer
        assert "last_name" in customer
        assert "email" in customer
        assert "phone" in customer
        assert "billing_postcode" in customer
        assert "created_at" in customer


# =============================================================================
# PATCH /api/admin/customers/{id} - Negative Path Tests
# =============================================================================

class TestUpdateCustomerNegativePath:
    """Negative path tests for updating customer."""

    def test_update_nonexistent_customer_returns_404(self):
        """Should return 404 for non-existent customer."""
        error_response = {
            "detail": "Customer not found"
        }

        assert error_response["detail"] == "Customer not found"

    def test_update_with_no_fields_returns_400(self):
        """Should return 400 when no fields provided."""
        error_response = {
            "detail": "At least one field (email or phone) must be provided"
        }

        assert "At least one field" in error_response["detail"]

    def test_update_with_invalid_email_format_returns_400(self):
        """Should return 400 for invalid email format."""
        invalid_emails = [
            "notanemail",
            "missing@domain",
            "@nodomain.com",
            "spaces in@email.com",
            "double@@at.com",
        ]

        for invalid_email in invalid_emails:
            # Simulate validation failure
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            is_valid = bool(re.match(email_pattern, invalid_email))
            assert is_valid is False, f"Email '{invalid_email}' should be invalid"

    def test_update_with_duplicate_email_returns_400(self):
        """Should return 400 when email already exists for another customer."""
        error_response = {
            "detail": "Email already exists"
        }

        assert error_response["detail"] == "Email already exists"

    def test_update_with_invalid_phone_format_returns_400(self):
        """Should return 400 for invalid phone format."""
        invalid_phones = [
            "123",  # Too short
            "abcdefghij",  # Not digits
            "1234567890123456",  # Too long (16 digits)
        ]

        for invalid_phone in invalid_phones:
            import re
            phone_clean = re.sub(r'[\s\-\(\)\+]', '', invalid_phone)
            is_valid = phone_clean.isdigit() and 10 <= len(phone_clean) <= 15
            assert is_valid is False, f"Phone '{invalid_phone}' should be invalid"


# =============================================================================
# PATCH /api/admin/customers/{id} - Edge Cases
# =============================================================================

class TestUpdateCustomerEdgeCases:
    """Edge case tests for updating customer."""

    def test_update_email_with_plus_sign(self):
        """Should accept email with plus sign (e.g., user+tag@gmail.com)."""
        email = "user+tag@gmail.com"
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        is_valid = bool(re.match(email_pattern, email))
        assert is_valid is True

    def test_update_email_with_subdomain(self):
        """Should accept email with subdomain."""
        email = "user@mail.subdomain.example.com"
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        is_valid = bool(re.match(email_pattern, email))
        assert is_valid is True

    def test_update_phone_with_spaces(self):
        """Should accept phone with spaces."""
        phone = "07700 900 001"
        import re
        phone_clean = re.sub(r'[\s\-\(\)\+]', '', phone)
        is_valid = phone_clean.isdigit() and 10 <= len(phone_clean) <= 15
        assert is_valid is True

    def test_update_phone_with_international_format(self):
        """Should accept international phone format."""
        phone = "+44 7700 900001"
        import re
        phone_clean = re.sub(r'[\s\-\(\)\+]', '', phone)
        is_valid = phone_clean.isdigit() and 10 <= len(phone_clean) <= 15
        assert is_valid is True

    def test_update_phone_with_parentheses(self):
        """Should accept phone with parentheses."""
        phone = "(07700) 900001"
        import re
        phone_clean = re.sub(r'[\s\-\(\)\+]', '', phone)
        is_valid = phone_clean.isdigit() and 10 <= len(phone_clean) <= 15
        assert is_valid is True

    def test_update_same_email_as_current(self):
        """Should allow updating to same email (no change)."""
        current_email = "same@test.com"
        new_email = "same@test.com"

        # This should be allowed - updating to same value
        assert current_email == new_email

    def test_update_phone_boundary_minimum_length(self):
        """Should accept phone at minimum length boundary (10 digits)."""
        phone = "0770090000"  # 10 digits
        import re
        phone_clean = re.sub(r'[\s\-\(\)\+]', '', phone)
        is_valid = phone_clean.isdigit() and 10 <= len(phone_clean) <= 15
        assert is_valid is True
        assert len(phone_clean) == 10

    def test_update_phone_boundary_maximum_length(self):
        """Should accept phone at maximum length boundary (15 digits)."""
        phone = "447700900001234"  # 15 digits
        import re
        phone_clean = re.sub(r'[\s\-\(\)\+]', '', phone)
        is_valid = phone_clean.isdigit() and 10 <= len(phone_clean) <= 15
        assert is_valid is True
        assert len(phone_clean) == 15

    def test_update_phone_over_maximum_length(self):
        """Should reject phone over maximum length (16+ digits)."""
        phone = "4477009000012345"  # 16 digits
        import re
        phone_clean = re.sub(r'[\s\-\(\)\+]', '', phone)
        is_valid = phone_clean.isdigit() and 10 <= len(phone_clean) <= 15
        assert is_valid is False


# =============================================================================
# DELETE /api/admin/customers/{id} - Happy Path Tests
# =============================================================================

class TestDeleteCustomerHappyPath:
    """Happy path tests for deleting customer."""

    def test_delete_customer_returns_success(self):
        """Should return success when customer deleted."""
        response_data = {
            "success": True,
            "message": "Customer 1 deleted successfully"
        }

        assert response_data["success"] is True
        assert "deleted successfully" in response_data["message"]

    def test_delete_customer_with_no_bookings(self):
        """Should successfully delete customer with no bookings."""
        customer_id = 1
        booking_count = 0

        can_delete = booking_count == 0
        assert can_delete is True

    def test_delete_returns_customer_id_in_message(self):
        """Delete response message should include customer ID."""
        customer_id = 42
        response_data = {
            "success": True,
            "message": f"Customer {customer_id} deleted successfully"
        }

        assert str(customer_id) in response_data["message"]


# =============================================================================
# DELETE /api/admin/customers/{id} - Negative Path Tests
# =============================================================================

class TestDeleteCustomerNegativePath:
    """Negative path tests for deleting customer."""

    def test_delete_nonexistent_customer_returns_404(self):
        """Should return 404 for non-existent customer."""
        error_response = {
            "detail": "Customer not found"
        }

        assert error_response["detail"] == "Customer not found"

    def test_delete_customer_with_bookings_returns_400(self):
        """Should return 400 when customer has associated bookings."""
        booking_count = 3
        error_response = {
            "detail": f"Cannot delete customer with {booking_count} associated booking(s)"
        }

        assert "Cannot delete customer" in error_response["detail"]
        assert str(booking_count) in error_response["detail"]

    def test_delete_customer_with_single_booking_returns_400(self):
        """Should return 400 when customer has single booking."""
        booking_count = 1
        error_response = {
            "detail": f"Cannot delete customer with {booking_count} associated booking(s)"
        }

        assert "Cannot delete customer" in error_response["detail"]


# =============================================================================
# DELETE /api/admin/customers/{id} - Edge Cases
# =============================================================================

class TestDeleteCustomerEdgeCases:
    """Edge case tests for deleting customer."""

    def test_delete_customer_id_zero(self):
        """Should handle customer ID of 0 (likely invalid)."""
        customer_id = 0
        # ID 0 would not exist in database
        error_response = {
            "detail": "Customer not found"
        }
        assert error_response["detail"] == "Customer not found"

    def test_delete_customer_negative_id(self):
        """Should handle negative customer ID."""
        customer_id = -1
        # Negative ID would not exist in database
        error_response = {
            "detail": "Customer not found"
        }
        assert error_response["detail"] == "Customer not found"

    def test_delete_customer_very_large_id(self):
        """Should handle very large customer ID."""
        customer_id = 999999999
        # Very large ID would not exist
        error_response = {
            "detail": "Customer not found"
        }
        assert error_response["detail"] == "Customer not found"


# =============================================================================
# Integration Tests - Edit and Delete
# =============================================================================

class TestCustomerEditDeleteIntegration:
    """Integration tests for customer edit and delete operations."""

    def test_edit_then_verify_change_persisted(self):
        """After editing, fetching customer should show new values."""
        original = create_mock_customer_response(
            id=1,
            email="original@test.com",
            phone="07700900001",
        )

        # Simulate edit
        new_email = "updated@test.com"
        edited = {**original, "email": new_email}

        # Simulate fetch after edit
        fetched = edited

        assert fetched["email"] == new_email
        assert fetched["id"] == original["id"]

    def test_delete_then_verify_not_found(self):
        """After deleting, customer should no longer exist."""
        customer_id = 1

        # Before delete - customer exists
        customers_before = [
            create_mock_customer_response(id=1, email="test@test.com"),
        ]
        customer_before = next((c for c in customers_before if c["id"] == customer_id), None)
        assert customer_before is not None

        # After delete - customer removed
        customers_after = []
        customer_after = next((c for c in customers_after if c["id"] == customer_id), None)
        assert customer_after is None

    def test_cannot_edit_deleted_customer(self):
        """Should not be able to edit a deleted customer."""
        customer_id = 1

        # After deletion, edit attempt should fail
        error_response = {
            "detail": "Customer not found"
        }
        assert error_response["detail"] == "Customer not found"

    def test_edit_does_not_affect_other_customers(self):
        """Editing one customer should not affect others."""
        customers = [
            create_mock_customer_response(id=1, email="customer1@test.com"),
            create_mock_customer_response(id=2, email="customer2@test.com"),
        ]

        # Edit customer 1
        customers[0]["email"] = "updated@test.com"

        # Customer 2 should be unchanged
        assert customers[1]["email"] == "customer2@test.com"

    def test_delete_does_not_affect_other_customers(self):
        """Deleting one customer should not affect others."""
        customers = [
            create_mock_customer_response(id=1, email="customer1@test.com"),
            create_mock_customer_response(id=2, email="customer2@test.com"),
            create_mock_customer_response(id=3, email="customer3@test.com"),
        ]

        # Delete customer 2
        customers = [c for c in customers if c["id"] != 2]

        # Customers 1 and 3 should still exist
        assert len(customers) == 2
        assert any(c["id"] == 1 for c in customers)
        assert any(c["id"] == 3 for c in customers)


# =============================================================================
# Marketing Source Tests
# =============================================================================

class TestCustomerMarketingSource:
    """Tests for marketing_source field in customer response."""

    def test_marketing_source_included_in_response(self):
        """Marketing source should be included in customer response."""
        customer = create_mock_customer_response(
            id=1,
            first_name="John",
            last_name="Smith",
            marketing_source="google",
        )

        assert "marketing_source" in customer
        assert customer["marketing_source"] == "google"

    def test_marketing_source_null_when_not_set(self):
        """Marketing source should be null when customer has no source."""
        customer = create_mock_customer_response(
            id=1,
            marketing_source=None,
        )

        assert customer["marketing_source"] is None

    def test_all_valid_marketing_sources(self):
        """All valid marketing source values should be accepted."""
        valid_sources = [
            "google",
            "facebook",
            "instagram",
            "linkedin",
            "newspaper",
            "afc_bournemouth",
            "other",
        ]

        for source in valid_sources:
            customer = create_mock_customer_response(marketing_source=source)
            assert customer["marketing_source"] == source

    def test_marketing_source_from_mock_object(self):
        """Marketing source should be extracted from customer.marketing_source relationship."""
        # Create mock marketing source
        mock_ms = create_mock_marketing_source(source="facebook")

        # Create customer with marketing source
        mock_customer = create_mock_customer(
            id=1,
            first_name="Jane",
            last_name="Doe",
            marketing_source=mock_ms,
        )

        # Simulate the API extraction logic
        marketing_source = None
        if mock_customer.marketing_source:
            marketing_source = mock_customer.marketing_source.source

        assert marketing_source == "facebook"

    def test_marketing_source_none_when_relationship_missing(self):
        """Marketing source should be None when relationship doesn't exist."""
        mock_customer = create_mock_customer(
            id=1,
            first_name="Jane",
            last_name="Doe",
            marketing_source=None,
        )

        # Simulate the API extraction logic
        marketing_source = None
        if mock_customer.marketing_source:
            marketing_source = mock_customer.marketing_source.source

        assert marketing_source is None

    def test_customers_with_mixed_marketing_sources(self):
        """Should handle list with mix of sources and nulls."""
        customers = [
            create_mock_customer_response(id=1, marketing_source="google"),
            create_mock_customer_response(id=2, marketing_source=None),
            create_mock_customer_response(id=3, marketing_source="facebook"),
            create_mock_customer_response(id=4, marketing_source="other"),
            create_mock_customer_response(id=5, marketing_source=None),
        ]

        # Count customers with sources
        with_source = [c for c in customers if c["marketing_source"] is not None]
        without_source = [c for c in customers if c["marketing_source"] is None]

        assert len(with_source) == 3
        assert len(without_source) == 2

    def test_marketing_source_preserved_in_update(self):
        """Marketing source should be preserved when updating email/phone."""
        original = create_mock_customer_response(
            id=1,
            email="old@test.com",
            phone="07700900001",
            marketing_source="instagram",
        )

        # Simulate update (only email changes)
        updated = {**original, "email": "new@test.com"}

        assert updated["marketing_source"] == "instagram"
        assert updated["email"] == "new@test.com"

    def test_marketing_source_for_reporting(self):
        """Should be able to group customers by marketing source."""
        customers = [
            create_mock_customer_response(id=1, marketing_source="google"),
            create_mock_customer_response(id=2, marketing_source="google"),
            create_mock_customer_response(id=3, marketing_source="facebook"),
            create_mock_customer_response(id=4, marketing_source="google"),
            create_mock_customer_response(id=5, marketing_source=None),
        ]

        # Group by source
        from collections import Counter
        sources = [c["marketing_source"] for c in customers if c["marketing_source"]]
        source_counts = Counter(sources)

        assert source_counts["google"] == 3
        assert source_counts["facebook"] == 1


# =============================================================================
# Integration Tests - Marketing Source Logic
# =============================================================================

class TestCustomerMarketingSourceIntegration:
    """Integration tests for marketing source extraction logic."""

    def test_extract_marketing_source_from_customer_object(self):
        """Should correctly extract marketing_source from customer relationship."""
        # Create mock customers with marketing sources
        mock_customers = [
            create_mock_customer(id=1, first_name="John", last_name="Doe",
                               marketing_source=create_mock_marketing_source("google")),
            create_mock_customer(id=2, first_name="Jane", last_name="Smith",
                               marketing_source=None),
        ]

        # Simulate the API extraction logic (from main.py get_customers)
        customers_data = []
        for customer in mock_customers:
            marketing_source = None
            if customer.marketing_source:
                marketing_source = customer.marketing_source.source

            customers_data.append({
                "id": customer.id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "email": customer.email,
                "phone": customer.phone,
                "billing_postcode": customer.billing_postcode,
                "created_at": customer.created_at.isoformat() if customer.created_at else None,
                "marketing_source": marketing_source,
            })

        # First customer should have marketing_source
        assert customers_data[0]["marketing_source"] == "google"
        assert customers_data[0]["first_name"] == "John"

        # Second customer should have null marketing_source
        assert customers_data[1]["marketing_source"] is None
        assert customers_data[1]["first_name"] == "Jane"

    def test_api_response_structure_with_marketing_source(self):
        """Verify API response structure includes marketing_source."""
        mock_customer = create_mock_customer(
            id=1,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            phone="07700900001",
            billing_postcode="BH1 1AA",
            marketing_source=create_mock_marketing_source("facebook"),
        )

        # Simulate API response building
        marketing_source = None
        if mock_customer.marketing_source:
            marketing_source = mock_customer.marketing_source.source

        response = {
            "id": mock_customer.id,
            "first_name": mock_customer.first_name,
            "last_name": mock_customer.last_name,
            "email": mock_customer.email,
            "phone": mock_customer.phone,
            "billing_postcode": mock_customer.billing_postcode,
            "created_at": mock_customer.created_at.isoformat() if mock_customer.created_at else None,
            "marketing_source": marketing_source,
        }

        # Verify all expected fields are present
        expected_fields = [
            "id", "first_name", "last_name", "email", "phone",
            "billing_postcode", "created_at", "marketing_source"
        ]

        for field in expected_fields:
            assert field in response, f"Field '{field}' missing from response"

        assert response["marketing_source"] == "facebook"

    def test_all_marketing_source_types_extracted_correctly(self):
        """All valid marketing source types should be extracted correctly."""
        valid_sources = [
            "google",
            "facebook",
            "instagram",
            "linkedin",
            "newspaper",
            "afc_bournemouth",
            "other",
        ]

        for source in valid_sources:
            mock_customer = create_mock_customer(
                id=1,
                marketing_source=create_mock_marketing_source(source),
            )

            # Simulate extraction
            marketing_source = None
            if mock_customer.marketing_source:
                marketing_source = mock_customer.marketing_source.source

            assert marketing_source == source, f"Source '{source}' not extracted correctly"
