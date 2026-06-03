"""
Static checks for the staging booking harness.

These tests validate e2e suite selection metadata without launching Playwright
or creating staging bookings.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import create_test_bookings


def test_referral_cases_are_last_three_and_selected_separately():
    referral_cases = create_test_bookings.get_referral_only_test_cases()

    assert len(create_test_bookings.TEST_CASES) == 25
    assert referral_cases == create_test_bookings.TEST_CASES[22:25]
    assert [case["promo_type"] for case in referral_cases] == ["referral", "referral", "referral"]
    assert [case["promo_code"] for case in referral_cases] == [
        create_test_bookings.TEST_REFERRAL_CODE,
        create_test_bookings.TEST_REFERRAL_CODE,
        create_test_bookings.TEST_REFERRAL_CODE,
    ]


def test_promo_only_excludes_referral_cases():
    promo_cases = create_test_bookings.get_promo_only_test_cases()

    assert promo_cases
    assert all(case.get("promo_code") for case in promo_cases)
    assert all(create_test_bookings.is_marketing_promo_test(case) for case in promo_cases)
    assert all(not create_test_bookings.is_referral_promo_test(case) for case in promo_cases)


def test_referral_referrees_use_london_date_anchor_and_distinct_emails():
    referral_cases = create_test_bookings.get_referral_only_test_cases()

    assert referral_cases[0]["days_from_now"] == 60
    assert referral_cases[1]["days_from_now"] == 60
    assert referral_cases[0]["date_timezone"] == "Europe/London"
    assert referral_cases[1]["date_timezone"] == "Europe/London"
    assert {
        referral_cases[0]["customer"]["email"],
        referral_cases[1]["customer"]["email"],
    } == {
        "qa.orca.contact+referral-friend1@gmail.com",
        "qa.orca.contact+referral-friend2@gmail.com",
    }
    assert "customer" not in referral_cases[2]
