"""HUEB coverage for the template roster effective-date runtime knob."""
import logging
from datetime import date as date_type

from roster_effective_date import get_roster_effective_date


def test_H_unset_uses_prod_default(monkeypatch):
    monkeypatch.delenv("TEMPLATE_ROSTER_EFFECTIVE_DATE", raising=False)

    assert get_roster_effective_date() == date_type(2026, 7, 1)


def test_H_valid_env_date_overrides_default(monkeypatch):
    monkeypatch.setenv("TEMPLATE_ROSTER_EFFECTIVE_DATE", "2026-06-15")

    assert get_roster_effective_date() == date_type(2026, 6, 15)


def test_H_env_date_is_read_per_call(monkeypatch):
    monkeypatch.setenv("TEMPLATE_ROSTER_EFFECTIVE_DATE", "2026-06-15")
    assert get_roster_effective_date() == date_type(2026, 6, 15)

    monkeypatch.setenv("TEMPLATE_ROSTER_EFFECTIVE_DATE", "2026-06-20")
    assert get_roster_effective_date() == date_type(2026, 6, 20)


def test_U_invalid_env_date_falls_back_and_warns(monkeypatch, caplog):
    monkeypatch.setenv("TEMPLATE_ROSTER_EFFECTIVE_DATE", "15/06/2026")

    with caplog.at_level(logging.WARNING):
        result = get_roster_effective_date()

    assert result == date_type(2026, 7, 1)
    assert "Invalid TEMPLATE_ROSTER_EFFECTIVE_DATE" in caplog.text
