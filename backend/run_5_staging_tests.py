#!/usr/bin/env python3
"""Run exactly 5 E2E tests: 3 normal + 2 overnight"""

from playwright.sync_api import sync_playwright
import sys
import os

# Add current dir to path
sys.path.insert(0, os.path.dirname(__file__))

# Import from create_test_bookings
from create_test_bookings import create_booking, STAGING_URL

# 5 specific tests: 3 normal + 2 overnight
TESTS = [
    {
        "name": "7-day standard trip",
        "days_from_now": 21,
        "duration": 7,
        "dropoff_time": "10:00",
        "airline": "Jet2",
        "overnight": False,
        "promo_code": None,
    },
    {
        "name": "14-day trip",
        "days_from_now": 10,
        "duration": 14,
        "dropoff_time": "08:30",
        "airline": "Ryanair",
        "overnight": False,
        "promo_code": None,
    },
    {
        "name": "1-day minimum duration",
        "days_from_now": 18,
        "duration": 1,
        "dropoff_time": "06:00",
        "airline": "TUI Airways",
        "overnight": False,
        "promo_code": None,
    },
    {
        "name": "Overnight flight 23:35 landing",
        "days_from_now": 20,
        "duration": 7,
        "dropoff_time": "16:00",
        "airline": "Jet2",
        "overnight": True,
        "overnight_arrival": "23:35",
        "promo_code": None,
    },
    {
        "name": "Overnight flight 23:45 landing",
        "days_from_now": 22,
        "duration": 7,
        "dropoff_time": "14:00",
        "airline": "Ryanair",
        "overnight": True,
        "overnight_arrival": "23:45",
        "promo_code": None,
    },
]

print("=" * 60)
print("Running 5 E2E Tests on Staging")
print("3 Normal + 2 Overnight")
print(f"URL: {STAGING_URL}")
print("=" * 60)

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=100)
    
    for i, test in enumerate(TESTS, 1):
        print(f"\n[{i}/5] {test['name']}")
        print("-" * 40)
        
        page = browser.new_page()
        
        try:
            success = create_booking(page, test, i)
            results.append((test['name'], success))
            status = "✓ PASSED" if success else "✗ FAILED"
            print(f"{status}")
        except Exception as e:
            results.append((test['name'], False))
            print(f"✗ ERROR: {e}")
        finally:
            page.close()
    
    browser.close()

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
passed = sum(1 for _, s in results if s)
print(f"Passed: {passed}/5")
for test, success in results:
    status = "✓" if success else "✗"
    print(f"  {status} {test}")
