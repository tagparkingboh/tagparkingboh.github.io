"""
Watchdog tests for the airport quote worker (airport_quote_worker.py).

Regression for the 2026-07-08 flight-board outage: hung Chromium scrapes held
both BoundedSemaphore slots forever, so every request for two days got 429
"worker is busy" until a manual Railway restart. The watchdog now runs each
scrape on an abandonable thread with a hard deadline: a hang costs one 504,
the semaphore slot is always reclaimed, and once too many abandoned scrapes
accumulate the worker exits non-zero for Railway's ON_FAILURE clean restart.

All scrapes are monkeypatched — no Chromium, no network.
"""
import threading
import time as time_module
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import airport_quote_worker as worker

# Captured before any fixture patches the module attributes, so the env
# parsing tests exercise the real functions.
_ORIGINAL_TIMEOUT_SECONDS = worker._scrape_timeout_seconds
_ORIGINAL_MAX_STUCK = worker._max_stuck_scrapes


QUOTE_PAYLOAD = {
    "entryDate": "2026-07-23",
    "entryTime": "01:00",
    "exitDate": "2026-07-31",
    "exitTime": "23:30",
}

BOARD = {
    "arrivals": [{"date": "08/07", "place": "Malaga", "flight": "FR5945"}],
    "departures": [{"date": "08/07", "place": "Mahon", "flight": "TOM6310"}],
    "source_url": "https://example.test/board",
}


def _client():
    # raise_server_exceptions=False so scrape exceptions surface as the 500
    # the real service returns, not as a test-side raise.
    return TestClient(worker.app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def reset_worker_state(monkeypatch):
    """Fast deadline for tests + clean stuck counter either side."""
    monkeypatch.setattr(worker, "_scrape_timeout_seconds", lambda: 0.05)
    worker._stuck_scrapes = 0
    yield
    worker._stuck_scrapes = 0


@pytest.fixture
def hang_gate():
    """Event a fake scrape blocks on; always released so no thread outlives the test."""
    gate = threading.Event()
    yield gate
    gate.set()
    # Give the abandoned thread a beat to finish and run its done-callback.
    deadline = time_module.time() + 2.0
    while worker._stuck_scrapes > 0 and time_module.time() < deadline:
        time_module.sleep(0.01)


def _wait_for(predicate, timeout=2.0):
    deadline = time_module.time() + timeout
    while time_module.time() < deadline:
        if predicate():
            return True
        time_module.sleep(0.01)
    return predicate()


# =============================================================================
# Happy paths — watchdog is transparent for healthy scrapes
# =============================================================================

class TestHealthyScrapes:

    def test_H_flight_board_scrape_returns_board(self, monkeypatch):
        monkeypatch.setattr(worker, "fetch_bournemouth_flight_board", lambda: BOARD)

        response = _client().post("/internal/flight-board/scrape")

        assert response.status_code == 200
        payload = response.json()
        assert payload["arrivals"] == BOARD["arrivals"]
        assert payload["departures"] == BOARD["departures"]
        assert payload["sourceUrl"] == BOARD["source_url"]

    def test_H_airport_quote_scrape_returns_products(self, monkeypatch):
        scrape = SimpleNamespace(
            products=[SimpleNamespace(to_api=lambda: {"name": "Car Park 1", "pricePence": 15376})],
            source_url="https://example.test/quote",
        )
        monkeypatch.setattr(worker, "fetch_bournemouth_airport_quote", lambda _input: scrape)

        response = _client().post("/internal/airport-parking/scrape", json=QUOTE_PAYLOAD)

        assert response.status_code == 200
        payload = response.json()
        assert payload["products"] == [{"name": "Car Park 1", "pricePence": 15376}]
        assert payload["sourceUrl"] == "https://example.test/quote"

    def test_H_scrape_exception_returns_clean_502(self, monkeypatch):
        """A failed (not hung) scrape answers 502, not a raw traceback 500."""
        def _boom():
            raise RuntimeError("Timeout 15000ms exceeded.\nCall log:\n  - waiting for locator")

        monkeypatch.setattr(worker, "fetch_bournemouth_flight_board", _boom)

        response = _client().post("/internal/flight-board/scrape")

        assert response.status_code == 502
        assert response.json()["detail"] == "flight-board scrape failed"

    def test_H_airport_quote_scrape_exception_returns_clean_502(self, monkeypatch):
        def _boom(_input):
            raise RuntimeError("BOH bounced to the landing page")

        monkeypatch.setattr(worker, "fetch_bournemouth_airport_quote", _boom)

        response = _client().post("/internal/airport-parking/scrape", json=QUOTE_PAYLOAD)

        assert response.status_code == 502
        assert response.json()["detail"] == "airport-parking scrape failed"

    def test_H_failed_scrape_does_not_count_as_stuck_and_frees_slot(self, monkeypatch):
        """Clean failure ≠ hang: no stuck increment, and the very next scrape runs."""
        def _boom():
            raise RuntimeError("scrape blew up")

        monkeypatch.setattr(worker, "fetch_bournemouth_flight_board", _boom)

        client = _client()
        assert client.post("/internal/flight-board/scrape").status_code == 502
        assert client.get("/").json()["stuck_scrapes"] == 0

        monkeypatch.setattr(worker, "fetch_bournemouth_flight_board", lambda: BOARD)
        response = client.post("/internal/flight-board/scrape")

        assert response.status_code == 200
        assert response.json()["arrivals"] == BOARD["arrivals"]

    def test_H_healthcheck_reports_stuck_count(self):
        response = _client().get("/")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["stuck_scrapes"] == 0


# =============================================================================
# The incident: hung scrape must not wedge the worker
# =============================================================================

class TestHungScrapeRecovery:

    def test_U_hung_scrape_times_out_with_504(self, monkeypatch, hang_gate):
        monkeypatch.setattr(worker, "_max_stuck_scrapes", lambda: 10)
        monkeypatch.setattr(worker, "fetch_bournemouth_flight_board", hang_gate.wait)

        response = _client().post("/internal/flight-board/scrape")

        assert response.status_code == 504
        assert "timed out" in response.json()["detail"]

    def test_U_slot_is_reclaimed_after_hang_so_next_scrape_succeeds(self, monkeypatch, hang_gate):
        """The 2026-07-08 wedge: before the watchdog, one hang held a slot
        forever. Now the very next request must scrape normally."""
        monkeypatch.setattr(worker, "_max_stuck_scrapes", lambda: 10)
        monkeypatch.setattr(worker, "fetch_bournemouth_flight_board", hang_gate.wait)

        client = _client()
        assert client.post("/internal/flight-board/scrape").status_code == 504

        monkeypatch.setattr(worker, "fetch_bournemouth_flight_board", lambda: BOARD)
        response = client.post("/internal/flight-board/scrape")

        assert response.status_code == 200
        assert response.json()["arrivals"] == BOARD["arrivals"]

    def test_U_stuck_counter_increments_and_decrements_when_zombie_finishes(self, monkeypatch, hang_gate):
        monkeypatch.setattr(worker, "_max_stuck_scrapes", lambda: 10)
        monkeypatch.setattr(worker, "fetch_bournemouth_flight_board", hang_gate.wait)

        client = _client()
        assert client.post("/internal/flight-board/scrape").status_code == 504
        assert client.get("/").json()["stuck_scrapes"] == 1

        # The zombie finishes late — it must stop counting as stuck.
        hang_gate.set()
        assert _wait_for(lambda: worker._stuck_scrapes == 0)
        assert client.get("/").json()["stuck_scrapes"] == 0

    def test_B_still_429_when_all_slots_genuinely_busy(self, monkeypatch):
        """Concurrency guard unchanged: no free slot -> 429 before any scrape."""
        held = 0
        try:
            while worker.SCRAPE_SEMAPHORE.acquire(blocking=False):
                held += 1

            response = _client().post("/internal/flight-board/scrape")

            assert response.status_code == 429
            assert response.json()["detail"] == "Airport quote worker is busy"
        finally:
            for _ in range(held):
                worker.SCRAPE_SEMAPHORE.release()


# =============================================================================
# Self-restart backstop
# =============================================================================

class TestSelfRestartBackstop:

    def test_U_terminates_when_stuck_limit_reached(self, monkeypatch, hang_gate):
        terminated = []
        monkeypatch.setattr(worker, "_terminate_process", lambda: terminated.append(True))
        monkeypatch.setattr(worker, "_max_stuck_scrapes", lambda: 1)
        monkeypatch.setattr(worker, "fetch_bournemouth_flight_board", hang_gate.wait)

        response = _client().post("/internal/flight-board/scrape")

        assert terminated == [True]
        # Test double returns instead of exiting, so the request falls through
        # to the 504 (the real process is gone before this point).
        assert response.status_code == 504

    def test_B_one_hang_below_limit_does_not_terminate(self, monkeypatch, hang_gate):
        terminated = []
        monkeypatch.setattr(worker, "_terminate_process", lambda: terminated.append(True))
        monkeypatch.setattr(worker, "_max_stuck_scrapes", lambda: 2)
        monkeypatch.setattr(worker, "fetch_bournemouth_flight_board", hang_gate.wait)

        response = _client().post("/internal/flight-board/scrape")

        assert response.status_code == 504
        assert terminated == []

    def test_B_limit_zero_disables_backstop(self, monkeypatch, hang_gate):
        terminated = []
        monkeypatch.setattr(worker, "_terminate_process", lambda: terminated.append(True))
        monkeypatch.setattr(worker, "_max_stuck_scrapes", lambda: 0)
        monkeypatch.setattr(worker, "fetch_bournemouth_flight_board", hang_gate.wait)

        response = _client().post("/internal/flight-board/scrape")

        assert response.status_code == 504
        assert terminated == []


# =============================================================================
# Env parsing boundaries
# =============================================================================

class TestEnvParsing:

    def test_B_timeout_default_is_90s(self, monkeypatch):
        monkeypatch.delenv("AIRPORT_QUOTE_WORKER_SCRAPE_TIMEOUT_SECONDS", raising=False)
        assert _ORIGINAL_TIMEOUT_SECONDS() == 90.0

    def test_B_timeout_clamps_to_minimum_1s(self, monkeypatch):
        monkeypatch.setenv("AIRPORT_QUOTE_WORKER_SCRAPE_TIMEOUT_SECONDS", "0.001")
        assert _ORIGINAL_TIMEOUT_SECONDS() == 1.0

    def test_U_timeout_invalid_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("AIRPORT_QUOTE_WORKER_SCRAPE_TIMEOUT_SECONDS", "ninety")
        assert _ORIGINAL_TIMEOUT_SECONDS() == 90.0

    def test_B_max_stuck_defaults_to_max_concurrency(self, monkeypatch):
        monkeypatch.delenv("AIRPORT_QUOTE_WORKER_MAX_STUCK_SCRAPES", raising=False)
        monkeypatch.setenv("AIRPORT_QUOTE_WORKER_MAX_CONCURRENCY", "3")
        assert _ORIGINAL_MAX_STUCK() == 3

    def test_B_max_stuck_zero_allowed(self, monkeypatch):
        monkeypatch.setenv("AIRPORT_QUOTE_WORKER_MAX_STUCK_SCRAPES", "0")
        assert _ORIGINAL_MAX_STUCK() == 0

    def test_U_max_stuck_invalid_falls_back_to_concurrency(self, monkeypatch):
        monkeypatch.setenv("AIRPORT_QUOTE_WORKER_MAX_STUCK_SCRAPES", "lots")
        monkeypatch.delenv("AIRPORT_QUOTE_WORKER_MAX_CONCURRENCY", raising=False)
        assert _ORIGINAL_MAX_STUCK() == 2
