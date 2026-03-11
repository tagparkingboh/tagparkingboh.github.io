#!/usr/bin/env python3
"""Run exactly 5 tests using the original create_test_bookings infrastructure."""

import sys
sys.path.insert(0, '.')

# Patch TEST_CASES to only include 5 tests before importing
import create_test_bookings

# Get just 5 tests: 3 normal + 2 overnight  
selected_tests = []
overnight_count = 0
normal_count = 0

for test in create_test_bookings.TEST_CASES:
    if overnight_count >= 2 and normal_count >= 3:
        break
    if test.get("overnight") and overnight_count < 2:
        selected_tests.append(test)
        overnight_count += 1
    elif not test.get("overnight") and normal_count < 3:
        selected_tests.append(test)
        normal_count += 1

# Replace the original TEST_CASES
create_test_bookings.TEST_CASES = selected_tests

print(f"Running {len(selected_tests)} tests:")
for t in selected_tests:
    print(f"  - {t['name']}")
print()

# Now run the main function  
if __name__ == "__main__":
    create_test_bookings.main()
