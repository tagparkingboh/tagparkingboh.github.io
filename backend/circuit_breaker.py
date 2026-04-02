"""
Circuit breaker for database connection pool protection.

When the connection pool is under stress, this middleware will:
1. Return 503 for non-critical endpoints to preserve connections
2. Allow critical endpoints (health checks, admin monitoring) through
3. Record pool snapshots when thresholds are crossed
"""
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable, Set
import time

logger = logging.getLogger(__name__)

# Thresholds for circuit breaker
POOL_SOFT_LIMIT = 70   # Start warning, continue serving
POOL_HARD_LIMIT = 85   # Start rejecting non-critical requests
POOL_CRITICAL = 95     # Reject most requests, only allow monitoring

# Endpoints that should always be allowed through (for monitoring/recovery)
CRITICAL_ENDPOINTS: Set[str] = {
    "/api/health",
    "/api/admin/db-health",
    "/api/admin/db-health/history",
    "/docs",
    "/openapi.json",
}

# Endpoints that are high-priority but can be rejected at critical levels
HIGH_PRIORITY_ENDPOINTS: Set[str] = {
    "/api/admin/",  # Admin operations (prefix match)
    "/api/auth/",   # Auth operations
}


def is_critical_endpoint(path: str) -> bool:
    """Check if endpoint should always be allowed through."""
    return path in CRITICAL_ENDPOINTS


def is_high_priority_endpoint(path: str) -> bool:
    """Check if endpoint is high priority (allowed until critical)."""
    if path in CRITICAL_ENDPOINTS:
        return True
    for prefix in HIGH_PRIORITY_ENDPOINTS:
        if path.startswith(prefix):
            return True
    return False


class PoolCircuitBreaker:
    """
    Circuit breaker that monitors pool usage and rejects requests when stressed.

    States:
    - CLOSED: Normal operation, all requests allowed
    - HALF_OPEN: Pool stressed, non-critical requests may be delayed/rejected
    - OPEN: Pool critical, most requests rejected
    """

    def __init__(self):
        self.state = "CLOSED"
        self.last_state_change = time.time()
        self.rejected_count = 0
        self.total_requests = 0

    def get_pool_usage(self) -> float:
        """Get current pool usage percentage."""
        try:
            from database import get_pool_status
            status = get_pool_status()
            return status.get("usage_percent", 0)
        except Exception as e:
            logger.error(f"Failed to get pool status: {e}")
            # If we can't check, assume healthy to avoid blocking everything
            return 0

    def update_state(self, usage_percent: float) -> str:
        """Update circuit breaker state based on pool usage."""
        old_state = self.state

        if usage_percent >= POOL_CRITICAL:
            self.state = "OPEN"
        elif usage_percent >= POOL_HARD_LIMIT:
            self.state = "HALF_OPEN"
        else:
            self.state = "CLOSED"

        if old_state != self.state:
            self.last_state_change = time.time()
            logger.warning(
                f"[CIRCUIT BREAKER] State changed: {old_state} -> {self.state} "
                f"(pool usage: {usage_percent}%)"
            )
            # Trigger a snapshot when state changes
            self._record_snapshot(usage_percent)

        return self.state

    def _record_snapshot(self, usage_percent: float):
        """Record a pool snapshot when circuit breaker state changes."""
        try:
            from database import SessionLocal, get_pool_status
            from db_models import DbPoolSnapshot, PoolHealthStatus

            status = get_pool_status()

            # Determine health status
            if usage_percent >= 90:
                health = PoolHealthStatus.CRITICAL
                trigger = "critical"
            elif usage_percent >= 70:
                health = PoolHealthStatus.WARNING
                trigger = "warning"
            else:
                health = PoolHealthStatus.HEALTHY
                trigger = "recovery"

            db = SessionLocal()
            try:
                snapshot = DbPoolSnapshot(
                    pool_size=status["pool_size"],
                    max_overflow=status["max_overflow"],
                    checked_out=status["checked_out"],
                    overflow=status["overflow"],
                    checked_in=status["checked_in"],
                    usage_percent=usage_percent,
                    health_status=health,
                    trigger=trigger,
                )
                db.add(snapshot)
                db.commit()
                logger.info(f"[CIRCUIT BREAKER] Recorded snapshot: {trigger} at {usage_percent}%")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[CIRCUIT BREAKER] Failed to record snapshot: {e}")

    def should_allow_request(self, path: str) -> tuple[bool, str]:
        """
        Determine if a request should be allowed through.

        Returns:
            (allowed, reason) - whether to allow and explanation
        """
        self.total_requests += 1
        usage_percent = self.get_pool_usage()
        self.update_state(usage_percent)

        # Critical endpoints always allowed
        if is_critical_endpoint(path):
            return True, "critical_endpoint"

        # Check based on circuit state
        if self.state == "CLOSED":
            return True, "circuit_closed"

        if self.state == "HALF_OPEN":
            # Allow high-priority, reject others
            if is_high_priority_endpoint(path):
                return True, "high_priority"
            self.rejected_count += 1
            return False, f"circuit_half_open (pool at {usage_percent}%)"

        if self.state == "OPEN":
            # Only allow critical endpoints (already checked above)
            if is_high_priority_endpoint(path):
                # Allow some high-priority through even when open
                # but log a warning
                logger.warning(f"[CIRCUIT BREAKER] Allowing high-priority request during OPEN: {path}")
                return True, "high_priority_emergency"
            self.rejected_count += 1
            return False, f"circuit_open (pool at {usage_percent}%)"

        return True, "unknown_state"

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            "state": self.state,
            "last_state_change": self.last_state_change,
            "rejected_count": self.rejected_count,
            "total_requests": self.total_requests,
            "rejection_rate": (
                self.rejected_count / self.total_requests * 100
                if self.total_requests > 0 else 0
            ),
        }


# Global circuit breaker instance
circuit_breaker = PoolCircuitBreaker()


class CircuitBreakerMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that applies circuit breaker logic."""

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path

        # Skip non-API paths (static files, etc.)
        if not path.startswith("/api"):
            return await call_next(request)

        allowed, reason = circuit_breaker.should_allow_request(path)

        if not allowed:
            logger.warning(f"[CIRCUIT BREAKER] Rejected request to {path}: {reason}")
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily unavailable due to high load. Please try again shortly.",
                    "reason": reason,
                    "retry_after": 5,
                },
                headers={"Retry-After": "5"}
            )

        return await call_next(request)


def get_circuit_breaker_stats() -> dict:
    """Get current circuit breaker statistics for monitoring."""
    stats = circuit_breaker.get_stats()
    stats["pool_usage"] = circuit_breaker.get_pool_usage()
    return stats
