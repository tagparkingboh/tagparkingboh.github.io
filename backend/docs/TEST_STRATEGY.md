# Test Strategy Plan: Smoke Testing + CI Automation (Commits, Staging, Releases)

## Summary
We need a clear plan to incorporate **smoke testing** and **automated test execution** into our workflow:
- **Automated smoke tests on every commit/PR**
- **Automated test suite on every push to staging**
- Optional: **release gate** for production deployments

This document defines:
- What smoke tests are
- What to run where (local, PR, staging, nightly)
- A practical CI/CD pipeline approach
- How to keep it fast, reliable, and actionable

---

## Goals
1. Catch obvious breakages early via **fast smoke tests**
2. Prevent unstable builds from entering **staging**
3. Provide confidence signals before **release**
4. Keep pipeline runtimes short enough to be used consistently
5. Make failures easy to debug (logs, artifacts, clear ownership)

---

## Non-Goals
- Building a perfect/complete test suite immediately
- End-to-end tests that rely on production services
- Flaky tests tolerated as "normal" (we should quarantine or fix)

---

## Definitions

### Smoke Tests
A small set of high-signal tests that confirm:
- App can start
- Core paths work
- No critical regressions

**Traits:**
- Fast (target: < 5 minutes total)
- Stable (low flake rate)
- Minimal dependencies (mock where possible)
- Focused on "can we ship this build at all?"

### Full Test Suite
Broader coverage including:
- Unit tests (mocked)
- Integration tests (mocked / local DB container if needed)
- Contract tests (API schema)
- UI component tests
- Optional: E2E tests (ideally against a disposable environment)

---

## Test Buckets (Recommended)

### 1) Lint + Typecheck (Fast)
- Runs everywhere (local, PR)
- Fails fast

### 2) Unit Tests (Mocked)
- Runs on PR and staging
- High coverage, low runtime

### 3) Integration Tests (Mocked)
- Runs on PR and staging
- Validates routing/API handlers/service wiring without real external calls

### 4) Smoke Tests (Targeted)
- Runs on every PR commit (or PR update)
- Runs on staging deployments (post-deploy)
- Optionally runs on production release candidate

### 5) Nightly Regression (Optional)
- Runs once daily
- Includes heavier tests, performance checks, longer suites

---

## What Exactly Is In Our Smoke Suite?

### Backend Smoke
- Server boots successfully
- Health endpoint returns 200 (`/health` or `/api/health`)
- Key API endpoints respond with correct status (can be mocked data):
  - Example: `GET /admin/flights`
  - Example: `GET /admin/reports/popular`
- Basic auth/permissions sanity check if applicable

### Frontend Smoke
- App builds successfully
- Admin page loads and primary navigation renders
- Key admin tabs render without crashing:
  - Flights
  - Reports
- Basic UI checks:
  - "no blank screen"
  - "no uncaught exceptions"
  - critical components mount

### Data & Contracts
- Contract/schema validation between frontend expectations and API response shape
- Basic "shape tests" on mocked fixtures

**Key rule:** Smoke tests should not depend on volatile external services.

---

## CI/CD Plan (Practical)

### A) On Every Commit / PR Update
**Purpose:** fast feedback before code merges

Run:
1. Lint + typecheck
2. Unit tests (mocked)
3. Smoke tests (fast, targeted)

**Pass/fail gate:**
- Required checks to merge: lint/typecheck + unit + smoke

**Notes**
- Keep smoke suite extremely stable.
- If smoke fails, treat as high priority.

---

### B) On Every Push to Staging (Pre-Deploy)
**Purpose:** stop broken builds from deploying

Run:
1. Lint + typecheck (optional if already done in PR)
2. Unit tests (mocked)
3. Integration tests (mocked)
4. Build artifacts (frontend build + backend build)

**Gate:**
- Must pass before deploy to staging

---

### C) After Staging Deploy (Post-Deploy)
**Purpose:** confirm deployed environment is healthy

Run:
1. Staging smoke suite against real staging URL:
   - health check
   - key pages respond
   - key admin flows load

**Gate:**
- If post-deploy smoke fails:
  - mark deployment failed
  - alert team
  - optionally auto-rollback (if supported)

---

### D) Production Release Gate (Recommended)
Run:
1. Same staging post-deploy smoke suite (or a slightly larger "release smoke")
2. Optional: short E2E pass on the most critical user journey(s)

---

## Tooling / Implementation Notes

### Where Tests Live
- `/tests/unit/**` (mocked unit)
- `/tests/integration/**` (mocked integration)
- `/tests/smoke/**` (smoke suite)

### Test Tags / Selection
Use a tagging or naming convention:
- `*.smoke.test.*` for smoke suite
- `*.int.test.*` for integration suite
- `*.unit.test.*` for unit suite

Or use runner tags:
- Jest/Vitest: `describe.concurrent`, file patterns, or custom env flags
- Playwright/Cypress (if used): `@smoke` tags

---

## Automation Triggers (High Level)

### Pull Requests
- Trigger CI on:
  - opened
  - synchronize (new commits)
  - reopened
- Required checks:
  - lint/typecheck
  - unit
  - smoke

### Staging
- Trigger on:
  - merge to `main` (or `develop`)
  - or push to `staging` branch (depending on flow)
- Pipeline:
  - pre-deploy tests
  - deploy to staging
  - post-deploy smoke tests

### Nightly (Optional)
- Scheduled run:
  - full integration suite
  - optional performance checks
  - report flaky tests

---

## Flakiness Policy (Important)
- Any smoke test that flakes gets:
  1. quarantined immediately (removed from smoke bucket)
  2. fixed before re-added
- Track:
  - failure rate
  - runtime
  - top recurring failures

---

## Reporting & Visibility
- CI should publish:
  - junit results
  - screenshots/logs if UI tests exist
  - test timing breakdown
- Failures should clearly indicate:
  - which bucket failed (smoke vs unit vs integration)
  - what commit introduced it
  - link to logs/artifacts

---

## Rollout Plan (Step-by-Step)
1. Define smoke suite scope (5-15 tests max)
2. Implement tags/patterns so smoke tests run separately
3. Add PR checks:
   - lint/typecheck + unit + smoke
4. Add staging pipeline:
   - pre-deploy full mocked suite
   - deploy
   - post-deploy smoke against staging URL
5. Add nightly job (optional)
6. Iterate:
   - expand coverage carefully
   - eliminate flake
   - keep runtime targets

---

## Acceptance Criteria
- Every PR runs smoke tests automatically and blocks merge on failure
- Every staging deployment runs:
  - pre-deploy tests
  - post-deploy smoke tests
- Smoke suite consistently completes fast and reliably
- Failures are visible with actionable logs

---

## Current State (TAG Parking)

### Existing Test Infrastructure
- **Backend:** pytest with ~244 tests covering:
  - Unit tests (mocked)
  - Integration tests (mocked DB queries)
  - API endpoint tests
  - Email service tests
  - Booking flow tests

- **Frontend:** Vitest with component tests
  - Pricing tests
  - Admin component tests

- **E2E:** Playwright script (`create_test_bookings.py`)
  - Full booking flow automation
  - Stripe test card integration
  - Screenshot artifacts on failure

### Next Steps for TAG
1. Categorize existing tests into smoke/unit/integration buckets
2. Add pytest markers: `@pytest.mark.smoke`, `@pytest.mark.integration`
3. Create GitHub Actions workflow for PR checks
4. Set up post-deploy smoke tests against staging URL
5. Track and fix any flaky tests identified
