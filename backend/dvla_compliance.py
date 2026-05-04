"""DVLA compliance status semantics — single source of truth.

DVLA's Vehicle Enquiry Service returns small string enums for `taxStatus`
and `motStatus`. We persist the raw strings on `vehicles` so the frontend
can colour-code per value. This module encodes which exact values count
as "alert Kristian" vs benign — kept here so Phase A persistence, Phase B
display, and Phase C scheduler/email all agree.

Locked 2026-05-03:
  Tax email triggers:  Untaxed, SORN, Not Taxed for on Road Use
  MOT email triggers:  Not valid, No details held by DVLA, No results returned
  Safe (no email):     Taxed, Valid, Could not verify (retry policy handles)
"""
from typing import Optional


# Values stored when DVLA itself can't be reached. Not from the DVLA spec —
# this is our internal sentinel. The 24h-before scheduler retries; if it
# stays this way after 3 daily ticks, the vehicle freezes (no more retries
# until the next vehicle activity touches it).
COULD_NOT_VERIFY = "Could not verify"


# DVLA enum values that should fire an alert email to Kristian.
TAX_ALERT_VALUES = frozenset({
    "Untaxed",
    "SORN",
    "Not Taxed for on Road Use",
})

MOT_ALERT_VALUES = frozenset({
    "Not valid",
    "No details held by DVLA",
    "No results returned",
})


def is_tax_alertable(tax_status: Optional[str]) -> bool:
    """True if this taxStatus value should trigger an email."""
    return tax_status in TAX_ALERT_VALUES


def is_mot_alertable(mot_status: Optional[str]) -> bool:
    """True if this motStatus value should trigger an email."""
    return mot_status in MOT_ALERT_VALUES


def should_alert(tax_status: Optional[str], mot_status: Optional[str]) -> bool:
    """True if either field warrants emailing Kristian.

    `None` and "Could not verify" are NEVER alertable — the retry policy
    handles transient/missing data so the daily scheduler doesn't spam
    Kristian on every DVLA blip.
    """
    return is_tax_alertable(tax_status) or is_mot_alertable(mot_status)
