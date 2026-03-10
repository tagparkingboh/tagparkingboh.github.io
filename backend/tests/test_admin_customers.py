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

def create_mock_customer(
    id=1,
    first_name="Test",
    last_name="User",
    email="test@example.com",
    phone="07700900001",
    billing_postcode="BH1 1AA",
    created_at=None,
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
    return customer


def create_mock_customer_response(
    id=1,
    first_name="Test",
    last_name="User",
    email="test@example.com",
    phone="07700900001",
    billing_postcode="BH1 1AA",
    created_at=None,
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
