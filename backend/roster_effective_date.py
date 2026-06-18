"""Runtime effective-date switch for template roster behavior."""
from __future__ import annotations

import logging
import os
from datetime import date as date_type

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_ROSTER_EFFECTIVE_DATE = date_type(2026, 7, 1)
TEMPLATE_ROSTER_EFFECTIVE_DATE_ENV = "TEMPLATE_ROSTER_EFFECTIVE_DATE"


def get_roster_effective_date() -> date_type:
    """Return the template roster cutover date, read from env per call."""
    raw = os.environ.get(TEMPLATE_ROSTER_EFFECTIVE_DATE_ENV, "").strip()
    if not raw:
        return DEFAULT_TEMPLATE_ROSTER_EFFECTIVE_DATE
    try:
        return date_type.fromisoformat(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r; using default %s",
            TEMPLATE_ROSTER_EFFECTIVE_DATE_ENV,
            raw,
            DEFAULT_TEMPLATE_ROSTER_EFFECTIVE_DATE.isoformat(),
        )
        return DEFAULT_TEMPLATE_ROSTER_EFFECTIVE_DATE
