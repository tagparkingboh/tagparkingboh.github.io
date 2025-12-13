"""
Configuration management for the TAG booking system.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Stripe configuration
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # DVLA Vehicle Enquiry Service API
    dvla_api_key_test: str = ""
    dvla_api_key_prod: str = ""

    # OS Places API (Ordnance Survey address lookup)
    os_places_api_key: str = ""

    # Environment
    environment: str = "development"

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Frontend URL (for CORS and redirects)
    frontend_url: str = "http://localhost:5173"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields like DATABASE_URL


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def is_stripe_configured() -> bool:
    """Check if Stripe is properly configured."""
    settings = get_settings()
    return bool(
        settings.stripe_secret_key
        and settings.stripe_secret_key.startswith(("sk_test_", "sk_live_"))
    )
