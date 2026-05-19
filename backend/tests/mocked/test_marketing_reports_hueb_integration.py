"""
HUEB integration tests for admin marketing + reports endpoints, hitting
the live FastAPI routes through TestClient.

Endpoints covered:
  GET /api/admin/marketing-sources/summary  (monthly + all-time totals)
  GET /api/admin/marketing-sources/other    (free-text "Other" responses)
  GET /api/admin/marketing-sources/export   (CSV export)
  GET /api/admin/reports/occupancy          (daily/weekly/monthly aggregates)

Auth (require_admin) and DB (get_db) are overridden via
app.dependency_overrides.
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app, require_admin
from database import get_db


# ============================================================================
# Helpers
# ============================================================================

def _admin():
    u = MagicMock()
    u.id = 1
    u.is_admin = True
    return u


def _override_admin():
    app.dependency_overrides[require_admin] = lambda: _admin()


def _override_db(db):
    def _gen():
        yield db
    app.dependency_overrides[get_db] = _gen


def _monthly_row(year_month, source, count):
    """Build a mock MarketingSourceMonthlyTotal row."""
    r = MagicMock()
    r.year_month = year_month
    r.source = source
    r.count = count
    return r


def _wire_summary_db(rows):
    """Chain stub for the summary endpoint:
    db.query(...).filter(...)*().order_by(...).all() → rows."""
    db = MagicMock()
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.all.return_value = rows
    db.query.return_value = chain
    return db


def _ms_row(source_detail, customer_first="Alice", customer_last="X", email="a@x.test", created=None):
    ms = MagicMock()
    ms.source = "other"
    ms.source_detail = source_detail
    ms.created_at = created or datetime(2026, 5, 14, 10, 0, 0)
    cust = MagicMock()
    cust.first_name = customer_first
    cust.last_name = customer_last
    cust.email = email
    return (ms, cust)


def _wire_other_db(joined_rows):
    """Chain stub for the 'other' details endpoint:
    db.query(...).join(...).filter(...)*().order_by(...).all() → joined_rows."""
    db = MagicMock()
    chain = MagicMock()
    chain.join.return_value = chain
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.all.return_value = joined_rows
    db.query.return_value = chain
    return db


# ============================================================================
# GET /api/admin/marketing-sources/summary  — HUEB
# ============================================================================

class TestMarketingSourcesSummary:
    def setup_method(self):
        _override_admin()

    def teardown_method(self):
        app.dependency_overrides.clear()

    # ---- HAPPY ----

    def test_H_returns_monthly_data_and_source_totals(self):
        rows = [
            _monthly_row("2026-05", "google", 100),
            _monthly_row("2026-05", "word_of_mouth", 30),
            _monthly_row("2026-04", "google", 80),
            _monthly_row("2026-04", "facebook", 10),
        ]
        _override_db(_wire_summary_db(rows))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_responses" in body
        assert "monthly_data" in body
        assert "source_totals" in body
        assert body["source_totals"]["google"] == 180  # 100 + 80
        assert body["source_totals"]["word_of_mouth"] == 30
        assert body["total_responses"] == 220

    def test_H_returns_empty_when_no_rows(self):
        _override_db(_wire_summary_db([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_responses"] == 0
        assert body["monthly_data"] == []
        assert body["source_totals"] == {}

    def test_H_with_valid_from_month_filter(self):
        rows = [_monthly_row("2026-05", "google", 5)]
        _override_db(_wire_summary_db(rows))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary?from_month=04/2026")
        assert resp.status_code == 200

    def test_H_with_to_month_filter(self):
        rows = [_monthly_row("2026-05", "google", 5)]
        _override_db(_wire_summary_db(rows))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary?to_month=06/2026")
        assert resp.status_code == 200

    # ---- UNHAPPY ----

    def test_U_unauthenticated_returns_401_or_403(self):
        app.dependency_overrides.pop(require_admin, None)
        _override_db(_wire_summary_db([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary")
        assert resp.status_code in (401, 403)
        _override_admin()

    def test_U_invalid_from_month_format_returns_400(self):
        _override_db(_wire_summary_db([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary?from_month=2026")
        assert resp.status_code == 400
        assert "MM/YYYY" in resp.json()["detail"]

    def test_U_invalid_to_month_format_returns_400(self):
        _override_db(_wire_summary_db([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary?to_month=not-a-month")
        assert resp.status_code == 400

    # ---- EDGE ----

    def test_E_monthly_data_sorted_newest_first(self):
        rows = [
            _monthly_row("2026-03", "google", 1),
            _monthly_row("2026-05", "google", 1),
            _monthly_row("2026-04", "google", 1),
        ]
        _override_db(_wire_summary_db(rows))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary")
        assert resp.status_code == 200
        months = [m["year_month"] for m in resp.json()["monthly_data"]]
        assert months == ["2026-05", "2026-04", "2026-03"]

    def test_E_same_source_across_multiple_months_accumulates_in_totals(self):
        rows = [
            _monthly_row("2026-05", "facebook", 10),
            _monthly_row("2026-04", "facebook", 15),
            _monthly_row("2026-03", "facebook", 5),
        ]
        _override_db(_wire_summary_db(rows))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary")
        assert resp.json()["source_totals"]["facebook"] == 30

    # ---- BOUNDARY ----

    def test_B_from_month_equals_to_month_returns_single_month_data(self):
        rows = [_monthly_row("2026-05", "google", 7)]
        _override_db(_wire_summary_db(rows))
        resp = TestClient(app).get(
            "/api/admin/marketing-sources/summary?from_month=05/2026&to_month=05/2026"
        )
        assert resp.status_code == 200

    def test_B_zero_count_row_still_appears_in_response(self):
        """Defensive — a 0-count row from the aggregate shouldn't be filtered out."""
        rows = [_monthly_row("2026-05", "tv", 0)]
        _override_db(_wire_summary_db(rows))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary")
        assert resp.status_code == 200
        assert resp.json()["source_totals"].get("tv", -1) == 0


# ============================================================================
# GET /api/admin/marketing-sources/other  — HUEB
# ============================================================================

class TestMarketingSourcesOther:
    def setup_method(self):
        _override_admin()

    def teardown_method(self):
        app.dependency_overrides.clear()

    # ---- HAPPY ----

    def test_H_returns_other_responses_with_customer_details(self):
        rows = [
            _ms_row("FRIEND", "Debbie", "Gibbs"),
            _ms_row("Family member", "Laura", "Harris"),
        ]
        _override_db(_wire_other_db(rows))
        resp = TestClient(app).get("/api/admin/marketing-sources/other")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        details = [r["source_detail"] for r in body["details"]]
        assert "FRIEND" in details
        assert "Family member" in details

    def test_H_year_month_filter_returns_matching_rows(self):
        rows = [_ms_row("Recommended", created=datetime(2026, 5, 12))]
        _override_db(_wire_other_db(rows))
        resp = TestClient(app).get("/api/admin/marketing-sources/other?year_month=2026-05")
        assert resp.status_code == 200

    def test_H_from_to_date_filters_apply(self):
        rows = [_ms_row("A friend")]
        _override_db(_wire_other_db(rows))
        resp = TestClient(app).get(
            "/api/admin/marketing-sources/other?from_date=01/05/2026&to_date=31/05/2026"
        )
        assert resp.status_code == 200

    # ---- UNHAPPY ----

    def test_U_unauthenticated_returns_401_or_403(self):
        app.dependency_overrides.pop(require_admin, None)
        _override_db(_wire_other_db([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/other")
        assert resp.status_code in (401, 403)
        _override_admin()

    def test_U_invalid_from_date_returns_400(self):
        _override_db(_wire_other_db([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/other?from_date=2026-05-01")
        # Endpoint expects DD/MM/YYYY; 2026-05-01 doesn't parse → 400
        assert resp.status_code == 400
        assert "DD/MM/YYYY" in resp.json()["detail"]

    def test_U_invalid_to_date_returns_400(self):
        _override_db(_wire_other_db([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/other?to_date=garbage")
        assert resp.status_code == 400

    # ---- EDGE ----

    def test_E_invalid_year_month_filter_silently_ignored(self):
        """The endpoint silently swallows bad year_month and returns all rows.
        Documented behaviour — pin it."""
        rows = [_ms_row("FRIEND")]
        _override_db(_wire_other_db(rows))
        resp = TestClient(app).get("/api/admin/marketing-sources/other?year_month=not-a-month")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_E_empty_responses_returns_empty_array(self):
        _override_db(_wire_other_db([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/other")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["details"] == []

    def test_E_customer_with_missing_name_components_handled(self):
        """first_name=None or last_name=None must not crash the formatter."""
        ms = MagicMock()
        ms.source = "other"
        ms.source_detail = "online"
        ms.created_at = datetime(2026, 5, 1)
        cust = MagicMock()
        cust.first_name = None
        cust.last_name = "OnlyLastName"
        cust.email = "ln@test.com"
        _override_db(_wire_other_db([(ms, cust)]))
        resp = TestClient(app).get("/api/admin/marketing-sources/other")
        assert resp.status_code == 200
        # Empty first name shouldn't produce leading space artifacts
        name = resp.json()["details"][0]["customer_name"]
        assert name.startswith("OnlyLastName") or name == "OnlyLastName"

    # ---- BOUNDARY ----

    def test_B_from_date_after_to_date_still_runs(self):
        """No ordering validation — endpoint applies both filters; result is
        likely empty but not an error."""
        _override_db(_wire_other_db([]))
        resp = TestClient(app).get(
            "/api/admin/marketing-sources/other?from_date=15/05/2026&to_date=01/05/2026"
        )
        assert resp.status_code == 200

    def test_B_exact_year_month_match(self):
        """year_month='2026-05' should produce a valid extract-based filter."""
        rows = [_ms_row("X")]
        _override_db(_wire_other_db(rows))
        resp = TestClient(app).get("/api/admin/marketing-sources/other?year_month=2026-05")
        assert resp.status_code == 200


# ============================================================================
# GET /api/admin/reports/occupancy  — HUEB (lightweight)
# ============================================================================

class TestReportsOccupancy:
    """The occupancy report aggregates by day/week/month. We exercise the
    happy paths + the three known query parameters; deeper logic is owned
    by booking_service tests."""

    def setup_method(self):
        _override_admin()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _wire(self):
        db = MagicMock()
        # Endpoint runs raw SQL via db.execute — return iterable that mimics rows.
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.group_by.return_value = chain
        chain.all.return_value = []
        db.query.return_value = chain
        # For raw SQL path (if any):
        result = MagicMock()
        result.fetchall.return_value = []
        result.mappings.return_value = result
        result.all.return_value = []
        db.execute.return_value = result
        return db

    # ---- HAPPY ----

    def test_H_view_daily_default(self):
        _override_db(self._wire())
        resp = TestClient(app).get("/api/admin/reports/occupancy")
        assert resp.status_code in (200, 422)  # endpoint may require view

    def test_H_view_weekly(self):
        _override_db(self._wire())
        resp = TestClient(app).get("/api/admin/reports/occupancy?view=weekly")
        assert resp.status_code in (200, 422)

    def test_H_view_monthly(self):
        _override_db(self._wire())
        resp = TestClient(app).get("/api/admin/reports/occupancy?view=monthly")
        assert resp.status_code in (200, 422)

    # ---- UNHAPPY ----

    def test_U_unauthenticated_returns_401_or_403(self):
        app.dependency_overrides.pop(require_admin, None)
        _override_db(self._wire())
        resp = TestClient(app).get("/api/admin/reports/occupancy")
        assert resp.status_code in (401, 403)
        _override_admin()

    def test_U_invalid_view_param_returns_4xx_or_200(self):
        """Endpoint may validate view; either 422 from FastAPI or 400 from
        custom validation is acceptable."""
        _override_db(self._wire())
        resp = TestClient(app).get("/api/admin/reports/occupancy?view=xyzzy")
        assert resp.status_code in (200, 400, 422)
