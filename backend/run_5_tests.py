#!/usr/bin/env python3
"""Run 5 specific tests: 3 normal + 2 overnight"""

import subprocess
import sys

TESTS = [
    "7-day standard trip",
    "14-day trip", 
    "1-day minimum duration",
    "Overnight flight 23:35 landing",
    "Overnight flight 23:45 landing",
]

print("=" * 60)
print("Running 5 E2E Tests on Staging")
print("3 Normal + 2 Overnight")
print("=" * 60)

results = []

for i, test in enumerate(TESTS, 1):
    print(f"\n[{i}/5] Running: {test}")
    print("-" * 40)
    
    result = subprocess.run(
        ["python3", "create_test_bookings.py"],
        env={**__import__('os').environ, "TEST_FILTER": test, "HEADLESS": "true"},
        capture_output=True,
        text=True,
        timeout=300
    )
    
    success = "PASSED" in result.stdout or "successful" in result.stdout.lower()
    results.append((test, success, result.stdout[-500:] if len(result.stdout) > 500 else result.stdout))
    
    if success:
        print(f"✓ PASSED: {test}")
    else:
        print(f"✗ FAILED: {test}")
        print(result.stdout[-300:])

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
passed = sum(1 for _, s, _ in results if s)
print(f"Passed: {passed}/5")
for test, success, _ in results:
    status = "✓" if success else "✗"
    print(f"  {status} {test}")

sys.exit(0 if passed == 5 else 1)
