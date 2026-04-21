"""
Tests for login code email functionality.

Tests the send_login_code_email function in email_service.py.
"""
import pytest
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSendLoginCodeEmail:
    """Tests for the send_login_code_email function."""

    def test_send_login_code_email_success(self):
        """Should send email successfully with valid parameters."""
        with patch('email_service.send_email', return_value=True) as mock_send:
            from email_service import send_login_code_email

            result = send_login_code_email(
                email="test@example.com",
                first_name="Test",
                code="123456"
            )

            assert result is True
            mock_send.assert_called_once()

    def test_send_login_code_email_failure(self):
        """Should return False when email sending fails."""
        with patch('email_service.send_email', return_value=False) as mock_send:
            from email_service import send_login_code_email

            result = send_login_code_email(
                email="test@example.com",
                first_name="Test",
                code="123456"
            )

            assert result is False
            mock_send.assert_called_once()

    def test_send_login_code_email_contains_code_in_subject(self):
        """Should include the code in the email subject."""
        with patch('email_service.send_email', return_value=True) as mock_send:
            from email_service import send_login_code_email

            send_login_code_email(
                email="test@example.com",
                first_name="Test",
                code="987654"
            )

            # Get the arguments passed to send_email
            call_args = mock_send.call_args
            subject = call_args[0][1]  # Second positional arg is subject

            assert "987654" in subject

    def test_send_login_code_email_subject_mentions_tag(self):
        """Subject line should mention TAG."""
        with patch('email_service.send_email', return_value=True) as mock_send:
            from email_service import send_login_code_email

            send_login_code_email(
                email="test@example.com",
                first_name="Test",
                code="123456"
            )

            call_args = mock_send.call_args
            subject = call_args[0][1]

            assert "TAG" in subject

    def test_send_login_code_email_contains_name_in_body(self):
        """Should include the user's name in the email content."""
        with patch('email_service.send_email', return_value=True) as mock_send:
            from email_service import send_login_code_email

            send_login_code_email(
                email="test@example.com",
                first_name="Alice",
                code="123456"
            )

            call_args = mock_send.call_args
            html_content = call_args[0][2]  # Third positional arg is html_content

            assert "Alice" in html_content

    def test_send_login_code_email_contains_code_in_body(self):
        """Should include the code in the email body."""
        with patch('email_service.send_email', return_value=True) as mock_send:
            from email_service import send_login_code_email

            send_login_code_email(
                email="test@example.com",
                first_name="Test",
                code="654321"
            )

            call_args = mock_send.call_args
            html_content = call_args[0][2]

            assert "654321" in html_content

    def test_send_login_code_email_correct_recipient(self):
        """Should send to the correct email address."""
        with patch('email_service.send_email', return_value=True) as mock_send:
            from email_service import send_login_code_email

            send_login_code_email(
                email="recipient@example.com",
                first_name="Test",
                code="123456"
            )

            call_args = mock_send.call_args
            to_email = call_args[0][0]  # First positional arg is to_email

            assert to_email == "recipient@example.com"

    def test_send_login_code_email_special_characters_in_name(self):
        """Should handle special characters in name."""
        with patch('email_service.send_email', return_value=True) as mock_send:
            from email_service import send_login_code_email

            result = send_login_code_email(
                email="test@example.com",
                first_name="O'Brien",
                code="123456"
            )

            assert result is True
            mock_send.assert_called_once()

            # Verify name is in the content
            call_args = mock_send.call_args
            html_content = call_args[0][2]
            assert "O'Brien" in html_content

    def test_send_login_code_email_unicode_name(self):
        """Should handle unicode characters in name."""
        with patch('email_service.send_email', return_value=True) as mock_send:
            from email_service import send_login_code_email

            result = send_login_code_email(
                email="test@example.com",
                first_name="Müller",
                code="123456"
            )

            assert result is True
            mock_send.assert_called_once()

    def test_send_login_code_email_empty_name(self):
        """Should handle empty name gracefully."""
        with patch('email_service.send_email', return_value=True) as mock_send:
            from email_service import send_login_code_email

            result = send_login_code_email(
                email="test@example.com",
                first_name="",
                code="123456"
            )

            # Should still work, even with empty name
            assert result is True

    def test_send_login_code_email_various_code_formats(self):
        """Should handle various code formats."""
        codes = ["000000", "999999", "123456", "111111"]

        for code in codes:
            with patch('email_service.send_email', return_value=True):
                from email_service import send_login_code_email

                result = send_login_code_email(
                    email="test@example.com",
                    first_name="Test",
                    code=code
                )
                assert result is True, f"Failed for code: {code}"

    def test_send_login_code_email_html_structure(self):
        """Should have proper HTML structure."""
        with patch('email_service.send_email', return_value=True) as mock_send:
            from email_service import send_login_code_email

            send_login_code_email(
                email="test@example.com",
                first_name="Test",
                code="123456"
            )

            call_args = mock_send.call_args
            html_content = call_args[0][2]

            # Check for basic HTML elements
            assert "<!DOCTYPE html>" in html_content
            assert "<html>" in html_content
            assert "</html>" in html_content
            assert "<body" in html_content
            assert "</body>" in html_content

    def test_send_login_code_email_mentions_expiry(self):
        """Should mention that the code expires."""
        with patch('email_service.send_email', return_value=True) as mock_send:
            from email_service import send_login_code_email

            send_login_code_email(
                email="test@example.com",
                first_name="Test",
                code="123456"
            )

            call_args = mock_send.call_args
            html_content = call_args[0][2]

            # Should mention expiry time
            assert "expire" in html_content.lower() or "10 minute" in html_content.lower()


class TestSendEmailFunction:
    """Tests for the base send_email function."""

    def test_send_email_with_sendgrid_success(self):
        """Should send email via SendGrid when configured."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_client.send.return_value = mock_response

        with patch('email_service.SENDGRID_API_KEY', 'test_api_key'):
            with patch('email_service.SendGridAPIClient', return_value=mock_client):
                from email_service import send_email

                result = send_email(
                    to_email="test@example.com",
                    subject="Test Subject",
                    html_content="<p>Test content</p>"
                )

                assert result is True

    def test_send_email_sendgrid_error(self):
        """Should return False when SendGrid returns error."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.body = "Bad Request"
        mock_client.send.return_value = mock_response

        with patch('email_service.SENDGRID_API_KEY', 'test_api_key'):
            with patch('email_service.SendGridAPIClient', return_value=mock_client):
                from email_service import send_email

                result = send_email(
                    to_email="test@example.com",
                    subject="Test Subject",
                    html_content="<p>Test content</p>"
                )

                assert result is False

    def test_send_email_exception(self):
        """Should return False when exception occurs."""
        with patch('email_service.SENDGRID_API_KEY', 'test_api_key'):
            with patch('email_service.SendGridAPIClient', side_effect=Exception("Network error")):
                from email_service import send_email

                result = send_email(
                    to_email="test@example.com",
                    subject="Test Subject",
                    html_content="<p>Test content</p>"
                )

                assert result is False


class TestIsEmailEnabled:
    """Tests for the is_email_enabled function."""

    def test_email_enabled_returns_bool(self):
        """Should return a boolean value."""
        from email_service import is_email_enabled

        result = is_email_enabled()
        assert isinstance(result, bool)
