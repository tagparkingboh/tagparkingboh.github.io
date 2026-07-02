"""BOH arrivals/departures flight board — parser, history rules, endpoints.

Fixture HTML is a REAL capture of https://www.bournemouthairport.com/
arrivals-departures/ taken 2026-07-02 (provided during the feature build), so
the parser is tested against the exact widget markup the airport serves,
including the mobile-only details-for-small span, trailing spaces in airline
names, and next-day departure rows.
"""
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from flight_board_scraper import (
    parse_board_hhmm,
    parse_boh_flight_board,
    resolve_board_date,
)
from flight_board_service import build_history_rows, process_flight_board_scrape


# =============================================================================
# Fixture: real widget HTML captured 2026-07-02
# =============================================================================

FIXTURE_HTML = """
<html><body>
<div id="widget-arrivals-content" class="animated fadeIn widget-arrivals-departures-content">
<table class="arrivals-table">
  <thead>
    <tr>
      <th class="place">From</th><th class="airline">Airline</th><th class="flight">Flight</th>
      <th class="time">Date</th><th class="time">Scheduled</th><th class="status">Status</th>
    </tr>
  </thead>
  <tbody>
    <tr>
<td class="place">Kefalonia<span class="details-for-small">TUI <br> TOM6457<br>Landed 14:41</span></td>
<td class="airline">TUI</td>
<td class="flight">TOM6457</td>
<td valign="top" class="time">02/07</td>
<td valign="top" class="time">14:25</td>
<td class="status">Landed 14:41</td>
</tr>
<tr>
<td class="place">Rhodes<span class="details-for-small">Ryanair  <br> FR8955<br>Landed 16:24</span></td>
<td class="airline">Ryanair </td>
<td class="flight">FR8955</td>
<td valign="top" class="time">02/07</td>
<td valign="top" class="time">16:05</td>
<td class="status">Landed 16:24</td>
</tr>
<tr>
<td class="place">Faro<span class="details-for-small">Ryanair  <br> FR3945<br>Expected 20:00</span></td>
<td class="airline">Ryanair </td>
<td class="flight">FR3945</td>
<td valign="top" class="time">02/07</td>
<td valign="top" class="time">20:20</td>
<td class="status">Expected 20:00</td>
</tr>
<tr>
<td class="place">Ibiza<span class="details-for-small">Jet2 <br> LS3628<br>As Scheduled</span></td>
<td class="airline">Jet2</td>
<td class="flight">LS3628</td>
<td valign="top" class="time">02/07</td>
<td valign="top" class="time">22:00</td>
<td class="status">As Scheduled</td>
</tr>
  </tbody>
</table></div>

<div id="widget-departures-content" class="animated fadeIn widget-arrivals-departures-content is-active">
<table class="arrivals-table">
  <thead>
    <tr>
      <th class="place">To</th><th class="airline">Airline</th><th class="flight">Flight</th>
      <th class="time">Date</th><th class="time">Scheduled</th><th class="status">Status</th>
    </tr>
  </thead>
  <tbody>
    <tr>
<td class="place">Heraklion<span class="details-for-small">TUI <br> TOM6472<br>Departed 13:47</span></td>
<td class="airline">TUI</td>
<td class="flight">TOM6472</td>
<td valign="top" class="time">02/07</td>
<td valign="top" class="time">13:45</td>
<td class="status">Departed 13:47</td>
</tr>
<tr>
<td class="place">Faro<span class="details-for-small">Ryanair  <br> FR3944<br>Wait In Lounge</span></td>
<td class="airline">Ryanair </td>
<td class="flight">FR3944</td>
<td valign="top" class="time">02/07</td>
<td valign="top" class="time">20:45</td>
<td class="status">Wait In Lounge</td>
</tr>
<tr>
<td class="place">Alicante<span class="details-for-small">Ryanair  <br> FR3961<br>As Scheduled</span></td>
<td class="airline">Ryanair </td>
<td class="flight">FR3961</td>
<td valign="top" class="time">03/07</td>
<td valign="top" class="time">06:25</td>
<td class="status">As Scheduled</td>
</tr>
  </tbody>
</table></div>
</body></html>
"""


# =============================================================================
# Parser
# =============================================================================

class TestParser:
    def test_H_parses_both_boards_from_one_page(self):
        board = parse_boh_flight_board(FIXTURE_HTML)
        assert len(board["arrivals"]) == 4
        assert len(board["departures"]) == 3

    def test_H_first_arrival_row_fields(self):
        row = parse_boh_flight_board(FIXTURE_HTML)["arrivals"][0]
        assert row == {
            "place": "Kefalonia",
            "airline": "TUI",
            "flight": "TOM6457",
            "date": "02/07",
            "scheduled": "14:25",
            "status": "Landed 14:41",
        }

    def test_H_details_for_small_span_is_excluded_from_place(self):
        """The place cell nests a mobile-only copy of the whole row — it must
        not leak into the place text."""
        rows = parse_boh_flight_board(FIXTURE_HTML)["arrivals"]
        for row in rows:
            assert "Landed" not in row["place"]
            assert "TOM" not in row["place"]
            assert "FR" not in row["place"]

    def test_H_airline_trailing_whitespace_stripped(self):
        rows = parse_boh_flight_board(FIXTURE_HTML)["arrivals"]
        ryanair = [r for r in rows if r["flight"] == "FR8955"][0]
        assert ryanair["airline"] == "Ryanair"

    def test_H_next_day_departure_rows_kept(self):
        departures = parse_boh_flight_board(FIXTURE_HTML)["departures"]
        overnight = [r for r in departures if r["flight"] == "FR3961"][0]
        assert overnight["date"] == "03/07"
        assert overnight["scheduled"] == "06:25"

    def test_U_empty_or_missing_sections_yield_empty_lists(self):
        assert parse_boh_flight_board("") == {"arrivals": [], "departures": []}
        assert parse_boh_flight_board("<html><body>maintenance</body></html>") == {
            "arrivals": [],
            "departures": [],
        }

    def test_U_header_only_table_yields_no_rows(self):
        html = FIXTURE_HTML.split("<tbody>")[0] + "<tbody></tbody></table></div></body></html>"
        assert parse_boh_flight_board(html)["arrivals"] == []


# =============================================================================
# Date/time resolution — year boundary per the t-eps/t/t+eps convention
# =============================================================================

class TestResolveBoardDate:
    def test_H_same_day_mid_year(self):
        assert resolve_board_date("02/07", date(2026, 7, 2)) == date(2026, 7, 2)

    def test_H_next_day_mid_year(self):
        assert resolve_board_date("03/07", date(2026, 7, 2)) == date(2026, 7, 3)

    def test_H_new_year_row_seen_in_december(self):
        # t+eps across the boundary: 01/01 seen on 31/12 -> NEXT year
        assert resolve_board_date("01/01", date(2026, 12, 31)) == date(2027, 1, 1)

    def test_H_december_row_seen_in_january(self):
        # t-eps across the boundary: 31/12 seen on 01/01 -> PREVIOUS year
        assert resolve_board_date("31/12", date(2027, 1, 1)) == date(2026, 12, 31)

    def test_H_boundary_day_itself(self):
        # t: 31/12 seen on 31/12 -> same day, same year
        assert resolve_board_date("31/12", date(2026, 12, 31)) == date(2026, 12, 31)

    def test_H_leap_day_in_leap_year(self):
        assert resolve_board_date("29/02", date(2028, 2, 28)) == date(2028, 2, 29)

    def test_U_leap_day_in_non_leap_year_is_dropped(self):
        assert resolve_board_date("29/02", date(2026, 2, 28)) is None

    def test_U_garbage_dates_are_dropped(self):
        assert resolve_board_date("99/99", date(2026, 7, 2)) is None
        assert resolve_board_date("", date(2026, 7, 2)) is None
        assert resolve_board_date(None, date(2026, 7, 2)) is None
        assert resolve_board_date("TBA", date(2026, 7, 2)) is None


class TestParseBoardHhmm:
    def test_H_valid(self):
        assert parse_board_hhmm("14:25") == time(14, 25)
        assert parse_board_hhmm("00:00") == time(0, 0)
        assert parse_board_hhmm("23:59") == time(23, 59)

    def test_U_invalid(self):
        assert parse_board_hhmm("24:00") is None
        assert parse_board_hhmm("14:60") is None
        assert parse_board_hhmm("TBA") is None
        assert parse_board_hhmm(None) is None
        assert parse_board_hhmm("") is None


# =============================================================================
# History rows — scheduled-only, deduped, filtered
# =============================================================================

class TestBuildHistoryRows:
    TODAY = date(2026, 7, 2)
    NOW = datetime(2026, 7, 2, 18, 0, tzinfo=timezone.utc)

    def _board(self):
        return parse_boh_flight_board(FIXTURE_HTML)

    def test_H_scheduled_times_only_no_status(self):
        rows = build_history_rows(self._board(), today=self.TODAY, now=self.NOW)
        assert rows, "expected history rows from fixture"
        for row in rows:
            assert "status" not in row  # punctuality is deliberately not stored
        tom = [r for r in rows if r["flight_number"] == "TOM6457"][0]
        assert tom["scheduled_time"] == time(14, 25)  # scheduled, NOT the 14:41 landing
        assert tom["direction"] == "arrival"
        assert tom["flight_date"] == date(2026, 7, 2)
        assert tom["place"] == "Kefalonia"

    def test_H_next_day_departure_resolves_forward(self):
        rows = build_history_rows(self._board(), today=self.TODAY, now=self.NOW)
        fr3961 = [r for r in rows if r["flight_number"] == "FR3961"][0]
        assert fr3961["flight_date"] == date(2026, 7, 3)
        assert fr3961["direction"] == "departure"

    def test_H_duplicate_flight_in_one_board_keeps_last(self):
        """Postgres ON CONFLICT cannot update the same row twice in one
        statement, so in-batch duplicates must collapse to one row."""
        board = self._board()
        dupe = dict(board["arrivals"][0])
        dupe["scheduled"] = "15:00"
        board["arrivals"].append(dupe)
        rows = build_history_rows(board, today=self.TODAY, now=self.NOW)
        tom_rows = [r for r in rows if r["flight_number"] == "TOM6457"]
        assert len(tom_rows) == 1
        assert tom_rows[0]["scheduled_time"] == time(15, 0)

    def test_U_rows_missing_key_fields_are_dropped(self):
        board = {
            "arrivals": [
                {"place": "X", "airline": "Y", "flight": "", "date": "02/07", "scheduled": "10:00", "status": "s"},
                {"place": "X", "airline": "Y", "flight": "AB1", "date": None, "scheduled": "10:00", "status": "s"},
                {"place": "X", "airline": "Y", "flight": "AB2", "date": "02/07", "scheduled": "TBA", "status": "s"},
            ],
            "departures": [],
        }
        assert build_history_rows(board, today=self.TODAY, now=self.NOW) == []


# =============================================================================
# Scheduler job — worker failure never blanks the board
# =============================================================================

class TestProcessFlightBoardScrape:
    def _session_factory(self):
        db = MagicMock()
        return db, (lambda: db)

    def test_H_ok_scrape_stores_snapshot_and_history(self, monkeypatch):
        db, factory = self._session_factory()
        board = parse_boh_flight_board(FIXTURE_HTML)
        board["source_url"] = "https://www.bournemouthairport.com/arrivals-departures/"
        monkeypatch.setattr(
            "airport_quote_worker_client.get_airport_quote_worker_url",
            lambda: "http://worker",
        )
        monkeypatch.setattr(
            "airport_quote_worker_client.fetch_flight_board_via_worker",
            lambda url: board,
        )
        process_flight_board_scrape(factory)
        assert db.add.call_count == 1
        snapshot = db.add.call_args[0][0]
        assert snapshot.status == "ok"
        assert len(snapshot.arrivals_json) == 4
        assert db.execute.called  # history upsert issued
        assert db.commit.called

    def test_U_worker_failure_stores_error_snapshot_only(self, monkeypatch):
        db, factory = self._session_factory()
        monkeypatch.setattr(
            "airport_quote_worker_client.get_airport_quote_worker_url",
            lambda: "http://worker",
        )

        def _boom(url):
            raise RuntimeError("worker down")

        monkeypatch.setattr(
            "airport_quote_worker_client.fetch_flight_board_via_worker", _boom
        )
        process_flight_board_scrape(factory)
        snapshot = db.add.call_args[0][0]
        assert snapshot.status == "error"
        assert "worker down" in snapshot.error
        assert not db.execute.called  # no history writes on failure
        assert db.commit.called

    def test_U_missing_worker_url_skips_entirely(self, monkeypatch):
        db, factory = self._session_factory()
        monkeypatch.setattr(
            "airport_quote_worker_client.get_airport_quote_worker_url", lambda: None
        )
        process_flight_board_scrape(factory)
        assert not db.add.called


# =============================================================================
# Employee endpoint — served from the latest ok snapshot
# =============================================================================

class TestEmployeeFlightBoardEndpoint:
    def _client_with_snapshot(self, snapshot):
        import main
        from database import get_db
        from main import app

        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.first.return_value = snapshot
        db.query.return_value = chain

        def _get_db():
            yield db

        user = MagicMock()
        user.id = 7
        user.is_admin = False
        app.dependency_overrides[get_db] = _get_db
        app.dependency_overrides[main.get_current_user] = lambda: user
        return TestClient(app), app

    def _teardown(self, app):
        app.dependency_overrides.clear()

    def _mk_snapshot(self, *, age_minutes):
        snapshot = MagicMock()
        snapshot.status = "ok"
        snapshot.arrivals_json = [{"flight": "TOM6457"}]
        snapshot.departures_json = [{"flight": "TOM6472"}]
        snapshot.created_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
        return snapshot

    def test_H_returns_latest_snapshot(self):
        client, app = self._client_with_snapshot(self._mk_snapshot(age_minutes=10))
        try:
            resp = client.get("/api/employee/flight-board")
            assert resp.status_code == 200, resp.json()
            body = resp.json()
            assert body["available"] is True
            assert body["arrivals"] == [{"flight": "TOM6457"}]
            assert body["departures"] == [{"flight": "TOM6472"}]
            assert body["age_minutes"] == 10
            assert body["stale"] is False
        finally:
            self._teardown(app)

    def test_H_stale_boundary_at_45_minutes(self):
        # t: exactly 45 -> not stale; t+eps: 46 -> stale
        for age, expected_stale in ((44, False), (45, False), (46, True)):
            client, app = self._client_with_snapshot(self._mk_snapshot(age_minutes=age))
            try:
                body = client.get("/api/employee/flight-board").json()
                assert body["stale"] is expected_stale, f"age={age}"
            finally:
                self._teardown(app)

    def test_U_no_snapshot_yet(self):
        client, app = self._client_with_snapshot(None)
        try:
            body = client.get("/api/employee/flight-board").json()
            assert body["available"] is False
            assert body["arrivals"] == []
            assert body["stale"] is True
        finally:
            self._teardown(app)

    def test_U_requires_auth(self):
        import main
        from main import app

        app.dependency_overrides.clear()
        resp = TestClient(app).get("/api/employee/flight-board")
        assert resp.status_code in (401, 403)


# =============================================================================
# Worker endpoint
# =============================================================================

class TestWorkerFlightBoardEndpoint:
    def test_H_returns_parsed_board(self):
        import airport_quote_worker

        board = parse_boh_flight_board(FIXTURE_HTML)
        board["source_url"] = "https://www.bournemouthairport.com/arrivals-departures/"
        with patch.object(
            airport_quote_worker, "fetch_bournemouth_flight_board", return_value=board
        ):
            resp = TestClient(airport_quote_worker.app).post(
                "/internal/flight-board/scrape"
            )
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload["arrivals"]) == 4
        assert len(payload["departures"]) == 3
        assert payload["sourceUrl"].endswith("/arrivals-departures/")

    def test_U_scrape_failure_propagates_as_500(self):
        import airport_quote_worker

        with patch.object(
            airport_quote_worker,
            "fetch_bournemouth_flight_board",
            side_effect=RuntimeError("flight board parsed empty"),
        ):
            resp = TestClient(airport_quote_worker.app, raise_server_exceptions=False).post(
                "/internal/flight-board/scrape"
            )
        assert resp.status_code == 500
