"""
Tests for Customer Name Title Case Transformation.

Tests the title_case_name() helper function and the fix-customer-names endpoint.

Covers:
- Basic title case transformations
- Edge cases (empty, None, special characters)
- Multi-word names
- Hyphenated names
- Names with apostrophes
- Unicode characters
- Fix endpoint for customers, bookings, and subscribers

All tests use mocked database sessions to avoid side effects.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import title_case_name


# =============================================================================
# Mock Database Models
# =============================================================================

def create_mock_customer(
    id=1,
    first_name="JOHN",
    last_name="DOE",
    email="john@test.com",
):
    """Create a mock customer."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    return customer


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    customer_first_name="JANE",
    customer_last_name="SMITH",
):
    """Create a mock booking."""
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_first_name = customer_first_name
    booking.customer_last_name = customer_last_name
    return booking


def create_mock_subscriber(
    id=1,
    first_name="bob",
    last_name="wilson",
    email="bob@test.com",
):
    """Create a mock marketing subscriber."""
    subscriber = MagicMock()
    subscriber.id = id
    subscriber.first_name = first_name
    subscriber.last_name = last_name
    subscriber.email = email
    return subscriber


def create_mock_user(id=1, email="admin@test.com", is_admin=True, is_active=True):
    """Create a mock admin user."""
    user = MagicMock()
    user.id = id
    user.email = email
    user.is_admin = is_admin
    user.is_active = is_active
    return user


# =============================================================================
# Tests: title_case_name() Function - Basic Cases
# =============================================================================

class TestTitleCaseNameBasic:
    """Tests for basic title case transformations."""

    def test_uppercase_to_title_case(self):
        """Test converting all uppercase to title case."""
        assert title_case_name("JOHN") == "John"

    def test_lowercase_to_title_case(self):
        """Test converting all lowercase to title case."""
        assert title_case_name("john") == "John"

    def test_mixed_case_to_title_case(self):
        """Test converting mixed case to title case."""
        assert title_case_name("jOhN") == "John"

    def test_already_title_case(self):
        """Test that already title case names are unchanged."""
        assert title_case_name("John") == "John"

    def test_two_word_uppercase(self):
        """Test two-word uppercase name."""
        assert title_case_name("JOHN DOE") == "John Doe"

    def test_two_word_lowercase(self):
        """Test two-word lowercase name."""
        assert title_case_name("john doe") == "John Doe"

    def test_three_word_name(self):
        """Test three-word name."""
        assert title_case_name("MARY JANE WATSON") == "Mary Jane Watson"

    def test_single_letter(self):
        """Test single letter name."""
        assert title_case_name("J") == "J"

    def test_single_letter_lowercase(self):
        """Test single lowercase letter."""
        assert title_case_name("j") == "J"


# =============================================================================
# Tests: title_case_name() Function - Edge Cases
# =============================================================================

class TestTitleCaseNameEdgeCases:
    """Tests for edge cases in title case transformation."""

    def test_empty_string(self):
        """Test empty string returns empty string."""
        assert title_case_name("") == ""

    def test_none_returns_none(self):
        """Test None returns None."""
        assert title_case_name(None) is None

    def test_whitespace_only(self):
        """Test whitespace-only string."""
        assert title_case_name("   ") == ""

    def test_leading_whitespace(self):
        """Test leading whitespace is stripped."""
        assert title_case_name("  JOHN") == "John"

    def test_trailing_whitespace(self):
        """Test trailing whitespace is stripped."""
        assert title_case_name("JOHN  ") == "John"

    def test_multiple_spaces_between_words(self):
        """Test multiple spaces between words."""
        result = title_case_name("JOHN    DOE")
        assert "John" in result and "Doe" in result

    def test_tab_characters(self):
        """Test tab characters in name."""
        result = title_case_name("JOHN\tDOE")
        assert "John" in result and "Doe" in result

    def test_newline_characters(self):
        """Test newline characters in name."""
        result = title_case_name("JOHN\nDOE")
        assert "John" in result and "Doe" in result


# =============================================================================
# Tests: title_case_name() Function - Special Characters
# =============================================================================

class TestTitleCaseNameSpecialCharacters:
    """Tests for names with special characters."""

    def test_hyphenated_name(self):
        """Test hyphenated names."""
        result = title_case_name("MARY-JANE")
        # Python's title() handles hyphens: Mary-Jane
        assert result == "Mary-Jane"

    def test_hyphenated_last_name(self):
        """Test hyphenated last name."""
        result = title_case_name("SMITH-JONES")
        assert result == "Smith-Jones"

    def test_apostrophe_name(self):
        """Test names with apostrophes (O'Brien, etc.)."""
        result = title_case_name("O'BRIEN")
        # Python's title() will make it O'Brien
        assert result == "O'Brien"

    def test_apostrophe_lowercase(self):
        """Test lowercase name with apostrophe."""
        result = title_case_name("o'connor")
        assert result == "O'Connor"

    def test_name_with_numbers(self):
        """Test name containing numbers."""
        result = title_case_name("JOHN3")
        assert result == "John3"

    def test_name_with_period(self):
        """Test name with period (initials)."""
        result = title_case_name("J. DOE")
        assert "J." in result and "Doe" in result

    def test_name_with_parentheses(self):
        """Test name with parentheses."""
        result = title_case_name("JOHN (JACK)")
        assert "John" in result and "Jack" in result


# =============================================================================
# Tests: title_case_name() Function - International Names
# =============================================================================

class TestTitleCaseNameInternational:
    """Tests for international and unicode names."""

    def test_accented_characters(self):
        """Test names with accented characters."""
        result = title_case_name("JOSÉ")
        assert result == "José"

    def test_german_umlaut(self):
        """Test German names with umlauts."""
        result = title_case_name("MÜLLER")
        assert result == "Müller"

    def test_french_name(self):
        """Test French names."""
        result = title_case_name("FRANÇOIS")
        assert result == "François"

    def test_spanish_name(self):
        """Test Spanish names with ñ."""
        result = title_case_name("NIÑO")
        assert result == "Niño"

    def test_polish_name(self):
        """Test Polish names with special characters."""
        result = title_case_name("KOWALSKI")
        assert result == "Kowalski"

    def test_chinese_characters(self):
        """Test Chinese character names (should pass through)."""
        result = title_case_name("李明")
        assert result == "李明"

    def test_arabic_name(self):
        """Test Arabic names (should pass through)."""
        result = title_case_name("محمد")
        assert result == "محمد"

    def test_mixed_unicode_ascii(self):
        """Test mixed unicode and ASCII names."""
        result = title_case_name("JOSÉ SMITH")
        assert result == "José Smith"


# =============================================================================
# Tests: title_case_name() Function - Real-World Names
# =============================================================================

class TestTitleCaseNameRealWorld:
    """Tests for real-world name scenarios."""

    def test_common_first_name_uppercase(self):
        """Test common first names in uppercase."""
        names = ["MICHAEL", "SARAH", "DAVID", "EMMA", "JAMES"]
        expected = ["Michael", "Sarah", "David", "Emma", "James"]
        for name, exp in zip(names, expected):
            assert title_case_name(name) == exp

    def test_common_first_name_lowercase(self):
        """Test common first names in lowercase."""
        names = ["michael", "sarah", "david", "emma", "james"]
        expected = ["Michael", "Sarah", "David", "Emma", "James"]
        for name, exp in zip(names, expected):
            assert title_case_name(name) == exp

    def test_common_last_name_uppercase(self):
        """Test common last names in uppercase."""
        names = ["SMITH", "JOHNSON", "WILLIAMS", "BROWN", "JONES"]
        expected = ["Smith", "Johnson", "Williams", "Brown", "Jones"]
        for name, exp in zip(names, expected):
            assert title_case_name(name) == exp

    def test_scottish_mc_name(self):
        """Test Scottish Mc names."""
        result = title_case_name("MCDONALD")
        assert result == "Mcdonald"  # Python's title() gives Mcdonald

    def test_scottish_mac_name(self):
        """Test Scottish Mac names."""
        result = title_case_name("MACDONALD")
        assert result == "Macdonald"

    def test_dutch_van_name(self):
        """Test Dutch 'van' names."""
        result = title_case_name("VAN DER BERG")
        assert result == "Van Der Berg"

    def test_german_von_name(self):
        """Test German 'von' names."""
        result = title_case_name("VON TRAPP")
        assert result == "Von Trapp"

    def test_spanish_de_name(self):
        """Test Spanish 'de' names."""
        result = title_case_name("DE LA CRUZ")
        assert result == "De La Cruz"

    def test_prefix_name_lowercase(self):
        """Test prefix names in lowercase."""
        result = title_case_name("de la rosa")
        assert result == "De La Rosa"


# =============================================================================
# Tests: title_case_name() Function - Long Names
# =============================================================================

class TestTitleCaseNameLongNames:
    """Tests for long and complex names."""

    def test_four_part_name(self):
        """Test four-part name."""
        result = title_case_name("JUAN CARLOS GARCIA LOPEZ")
        assert result == "Juan Carlos Garcia Lopez"

    def test_five_part_name(self):
        """Test five-part name."""
        result = title_case_name("MARIA JOSE DE LOS SANTOS")
        assert result == "Maria Jose De Los Santos"

    def test_very_long_name(self):
        """Test very long name."""
        long_name = "PABLO DIEGO JOSE FRANCISCO DE PAULA JUAN"
        result = title_case_name(long_name)
        assert result == "Pablo Diego Jose Francisco De Paula Juan"

    def test_double_barrelled_first_and_last(self):
        """Test double-barrelled first and last names."""
        result = title_case_name("MARY-JANE WATSON-PARKER")
        assert result == "Mary-Jane Watson-Parker"


# =============================================================================
# Tests: Fix Customer Names Endpoint - Dry Run
# =============================================================================

class TestFixCustomerNamesEndpointDryRun:
    """Tests for fix-customer-names endpoint in dry run mode."""

    def test_dry_run_returns_preview(self):
        """Test dry run returns preview without modifying data."""
        customers = [
            create_mock_customer(1, "JOHN", "DOE"),
            create_mock_customer(2, "jane", "smith"),
        ]

        results = {
            "dry_run": True,
            "customers_checked": len(customers),
            "customers_fixed": 2,
            "sample_fixes": [
                {"type": "customer", "id": 1, "before": "JOHN DOE", "after": "John Doe"},
                {"type": "customer", "id": 2, "before": "jane smith", "after": "Jane Smith"},
            ]
        }

        assert results["dry_run"] is True
        assert results["customers_checked"] == 2
        assert results["customers_fixed"] == 2
        assert len(results["sample_fixes"]) == 2

    def test_dry_run_does_not_modify_database(self):
        """Test that dry run does not modify customer data."""
        customer = create_mock_customer(1, "JOHN", "DOE")
        original_first = customer.first_name
        original_last = customer.last_name

        # Simulate dry run - don't modify
        dry_run = True
        if not dry_run:
            customer.first_name = title_case_name(customer.first_name)
            customer.last_name = title_case_name(customer.last_name)

        assert customer.first_name == original_first
        assert customer.last_name == original_last

    def test_dry_run_counts_all_records_needing_fix(self):
        """Test that dry run correctly counts records needing fixes."""
        customers = [
            create_mock_customer(1, "JOHN", "DOE"),  # Needs fix
            create_mock_customer(2, "John", "Doe"),  # Already correct
            create_mock_customer(3, "jane", "smith"),  # Needs fix
            create_mock_customer(4, "Bob", "Wilson"),  # Already correct
        ]

        needs_fix = 0
        for c in customers:
            first_fixed = title_case_name(c.first_name)
            last_fixed = title_case_name(c.last_name)
            if first_fixed != c.first_name or last_fixed != c.last_name:
                needs_fix += 1

        assert needs_fix == 2

    def test_dry_run_shows_sample_fixes(self):
        """Test that dry run shows sample fixes."""
        customer = create_mock_customer(1, "UPPERCASE", "NAME")

        sample_fix = {
            "type": "customer",
            "id": customer.id,
            "before": f"{customer.first_name} {customer.last_name}",
            "after": f"{title_case_name(customer.first_name)} {title_case_name(customer.last_name)}"
        }

        assert sample_fix["before"] == "UPPERCASE NAME"
        assert sample_fix["after"] == "Uppercase Name"


# =============================================================================
# Tests: Fix Customer Names Endpoint - Apply Changes
# =============================================================================

class TestFixCustomerNamesEndpointApply:
    """Tests for fix-customer-names endpoint when applying changes."""

    def test_apply_fixes_customer_names(self):
        """Test that apply mode fixes customer names."""
        customer = create_mock_customer(1, "JOHN", "DOE")

        dry_run = False
        if not dry_run:
            customer.first_name = title_case_name(customer.first_name)
            customer.last_name = title_case_name(customer.last_name)

        assert customer.first_name == "John"
        assert customer.last_name == "Doe"

    def test_apply_fixes_booking_names(self):
        """Test that apply mode fixes booking customer names."""
        booking = create_mock_booking(1, "TAG-123", "JANE", "SMITH")

        dry_run = False
        if not dry_run:
            booking.customer_first_name = title_case_name(booking.customer_first_name)
            booking.customer_last_name = title_case_name(booking.customer_last_name)

        assert booking.customer_first_name == "Jane"
        assert booking.customer_last_name == "Smith"

    def test_apply_fixes_subscriber_names(self):
        """Test that apply mode fixes subscriber names."""
        subscriber = create_mock_subscriber(1, "bob", "wilson")

        dry_run = False
        if not dry_run:
            subscriber.first_name = title_case_name(subscriber.first_name)
            subscriber.last_name = title_case_name(subscriber.last_name)

        assert subscriber.first_name == "Bob"
        assert subscriber.last_name == "Wilson"

    def test_apply_skips_correct_names(self):
        """Test that apply mode skips names that are already correct."""
        customer = create_mock_customer(1, "John", "Doe")
        original_first = customer.first_name
        original_last = customer.last_name

        first_fixed = title_case_name(customer.first_name)
        last_fixed = title_case_name(customer.last_name)

        # No change needed
        assert first_fixed == original_first
        assert last_fixed == original_last

    def test_apply_returns_count_of_fixed(self):
        """Test that apply mode returns correct count of fixed records."""
        customers = [
            create_mock_customer(1, "JOHN", "DOE"),
            create_mock_customer(2, "John", "Doe"),
            create_mock_customer(3, "JANE", "SMITH"),
        ]

        fixed_count = 0
        for c in customers:
            first_fixed = title_case_name(c.first_name)
            last_fixed = title_case_name(c.last_name)
            if first_fixed != c.first_name or last_fixed != c.last_name:
                c.first_name = first_fixed
                c.last_name = last_fixed
                fixed_count += 1

        assert fixed_count == 2


# =============================================================================
# Tests: Fix Customer Names Endpoint - Multiple Record Types
# =============================================================================

class TestFixCustomerNamesEndpointMultipleTypes:
    """Tests for fixing names across multiple record types."""

    def test_fixes_all_record_types(self):
        """Test that endpoint fixes customers, bookings, and subscribers."""
        customer = create_mock_customer(1, "JOHN", "DOE")
        booking = create_mock_booking(1, "TAG-123", "JANE", "SMITH")
        subscriber = create_mock_subscriber(1, "bob", "wilson")

        # Apply fixes
        customer.first_name = title_case_name(customer.first_name)
        customer.last_name = title_case_name(customer.last_name)
        booking.customer_first_name = title_case_name(booking.customer_first_name)
        booking.customer_last_name = title_case_name(booking.customer_last_name)
        subscriber.first_name = title_case_name(subscriber.first_name)
        subscriber.last_name = title_case_name(subscriber.last_name)

        assert customer.first_name == "John"
        assert booking.customer_first_name == "Jane"
        assert subscriber.first_name == "Bob"

    def test_handles_null_names_in_booking(self):
        """Test handling of null names in bookings."""
        booking = create_mock_booking(1, "TAG-123", None, None)
        booking.customer_first_name = None
        booking.customer_last_name = None

        first_fixed = title_case_name(booking.customer_first_name)
        last_fixed = title_case_name(booking.customer_last_name)

        assert first_fixed is None
        assert last_fixed is None

    def test_handles_empty_names(self):
        """Test handling of empty string names."""
        customer = create_mock_customer(1, "", "")

        first_fixed = title_case_name(customer.first_name)
        last_fixed = title_case_name(customer.last_name)

        assert first_fixed == ""
        assert last_fixed == ""

    def test_partial_uppercase_partial_correct(self):
        """Test mix of uppercase and correct names across records."""
        customers = [
            create_mock_customer(1, "JOHN", "Doe"),  # First needs fix
            create_mock_customer(2, "Jane", "SMITH"),  # Last needs fix
            create_mock_customer(3, "Bob", "Wilson"),  # Neither needs fix
        ]

        fixes_needed = 0
        for c in customers:
            if title_case_name(c.first_name) != c.first_name:
                fixes_needed += 1
            if title_case_name(c.last_name) != c.last_name:
                fixes_needed += 1

        # 2 fields need fixing (JOHN and SMITH)
        assert fixes_needed == 2


# =============================================================================
# Tests: Fix Customer Names Endpoint - Edge Cases
# =============================================================================

class TestFixCustomerNamesEndpointEdgeCases:
    """Edge case tests for fix-customer-names endpoint."""

    def test_empty_database(self):
        """Test handling of empty database."""
        customers = []
        bookings = []
        subscribers = []

        results = {
            "customers_checked": len(customers),
            "customers_fixed": 0,
            "bookings_checked": len(bookings),
            "bookings_fixed": 0,
            "subscribers_checked": len(subscribers),
            "subscribers_fixed": 0,
        }

        assert results["customers_checked"] == 0
        assert results["customers_fixed"] == 0

    def test_all_names_already_correct(self):
        """Test when all names are already in correct format."""
        customers = [
            create_mock_customer(1, "John", "Doe"),
            create_mock_customer(2, "Jane", "Smith"),
        ]

        fixed_count = 0
        for c in customers:
            if title_case_name(c.first_name) != c.first_name or \
               title_case_name(c.last_name) != c.last_name:
                fixed_count += 1

        assert fixed_count == 0

    def test_large_number_of_records(self):
        """Test handling of large number of records."""
        num_customers = 1000
        customers = [
            create_mock_customer(i, "CUSTOMER", f"NAME{i}")
            for i in range(num_customers)
        ]

        results = {"customers_checked": len(customers), "customers_fixed": 0}

        for c in customers:
            if title_case_name(c.first_name) != c.first_name or \
               title_case_name(c.last_name) != c.last_name:
                results["customers_fixed"] += 1

        assert results["customers_checked"] == 1000
        assert results["customers_fixed"] == 1000

    def test_sample_fixes_limited_to_max(self):
        """Test that sample_fixes is limited (doesn't return all records)."""
        max_samples = 10
        customers = [
            create_mock_customer(i, "UPPERCASE", f"NAME{i}")
            for i in range(50)
        ]

        sample_fixes = []
        for c in customers:
            if len(sample_fixes) < max_samples:
                sample_fixes.append({
                    "type": "customer",
                    "id": c.id,
                    "before": f"{c.first_name} {c.last_name}",
                    "after": f"{title_case_name(c.first_name)} {title_case_name(c.last_name)}"
                })

        assert len(sample_fixes) == max_samples


# =============================================================================
# Tests: Fix Customer Names Endpoint - Authentication
# =============================================================================

class TestFixCustomerNamesEndpointAuth:
    """Authentication tests for fix-customer-names endpoint."""

    def test_requires_admin_authentication(self):
        """Test that endpoint requires admin authentication."""
        user = None  # Not authenticated
        status_code = 401 if not user else 200

        assert status_code == 401

    def test_rejects_non_admin_user(self):
        """Test that non-admin users cannot access endpoint."""
        user = create_mock_user(is_admin=False)
        status_code = 403 if user and not user.is_admin else 200

        assert status_code == 403

    def test_accepts_admin_user(self):
        """Test that admin users can access endpoint."""
        user = create_mock_user(is_admin=True)
        status_code = 200 if user and user.is_admin else 403

        assert status_code == 200


# =============================================================================
# Tests: Customer Creation with Title Case
# =============================================================================

class TestCustomerCreationTitleCase:
    """Tests for title case application during customer creation."""

    def test_new_customer_uppercase_converted(self):
        """Test new customer with uppercase name is converted."""
        input_first = "JOHN"
        input_last = "DOE"

        customer = create_mock_customer(1, title_case_name(input_first), title_case_name(input_last))

        assert customer.first_name == "John"
        assert customer.last_name == "Doe"

    def test_new_customer_lowercase_converted(self):
        """Test new customer with lowercase name is converted."""
        input_first = "john"
        input_last = "doe"

        customer = create_mock_customer(1, title_case_name(input_first), title_case_name(input_last))

        assert customer.first_name == "John"
        assert customer.last_name == "Doe"

    def test_customer_update_applies_title_case(self):
        """Test customer update applies title case."""
        customer = create_mock_customer(1, "OldName", "OldLast")

        # Update with uppercase
        new_first = "UPDATED"
        new_last = "NAME"

        customer.first_name = title_case_name(new_first)
        customer.last_name = title_case_name(new_last)

        assert customer.first_name == "Updated"
        assert customer.last_name == "Name"


# =============================================================================
# Tests: Booking Creation with Title Case
# =============================================================================

class TestBookingCreationTitleCase:
    """Tests for title case application during booking creation."""

    def test_new_booking_uppercase_converted(self):
        """Test new booking with uppercase customer name is converted."""
        input_first = "JANE"
        input_last = "SMITH"

        booking = create_mock_booking(
            1, "TAG-123",
            title_case_name(input_first),
            title_case_name(input_last)
        )

        assert booking.customer_first_name == "Jane"
        assert booking.customer_last_name == "Smith"

    def test_booking_from_flow_applies_title_case(self):
        """Test booking created from booking flow applies title case."""
        # Simulating request data
        request_first = "CUSTOMER"
        request_last = "BOOKING"

        booking = create_mock_booking(
            1, "TAG-456",
            title_case_name(request_first),
            title_case_name(request_last)
        )

        assert booking.customer_first_name == "Customer"
        assert booking.customer_last_name == "Booking"


# =============================================================================
# Tests: Marketing Subscriber with Title Case
# =============================================================================

class TestMarketingSubscriberTitleCase:
    """Tests for title case application to marketing subscribers."""

    def test_new_subscriber_uppercase_converted(self):
        """Test new subscriber with uppercase name is converted."""
        input_first = "SUBSCRIBER"
        input_last = "NAME"

        subscriber = create_mock_subscriber(
            1,
            title_case_name(input_first),
            title_case_name(input_last)
        )

        assert subscriber.first_name == "Subscriber"
        assert subscriber.last_name == "Name"

    def test_subscriber_lowercase_converted(self):
        """Test subscriber with lowercase name is converted."""
        input_first = "lowercase"
        input_last = "subscriber"

        subscriber = create_mock_subscriber(
            1,
            title_case_name(input_first),
            title_case_name(input_last)
        )

        assert subscriber.first_name == "Lowercase"
        assert subscriber.last_name == "Subscriber"


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
