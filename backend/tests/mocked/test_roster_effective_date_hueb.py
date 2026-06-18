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


def test_B_blank_env_value_uses_default_without_warning(monkeypatch, caplog):
    """A set-but-blank value strips to empty and takes the silent default
    path — it is NOT treated as 'invalid', so no warning is logged."""
    monkeypatch.setenv("TEMPLATE_ROSTER_EFFECTIVE_DATE", "   ")

    with caplog.at_level(logging.WARNING):
        result = get_roster_effective_date()

    assert result == date_type(2026, 7, 1)
    assert "Invalid" not in caplog.text


def test_U_syntactically_impossible_date_falls_back(monkeypatch):
    """A well-formed but impossible ISO date (Feb 30) raises ValueError in
    fromisoformat and must fall back to the default, not crash the caller."""
    monkeypatch.setenv("TEMPLATE_ROSTER_EFFECTIVE_DATE", "2026-02-30")

    assert get_roster_effective_date() == date_type(2026, 7, 1)
