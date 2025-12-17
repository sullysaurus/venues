"""
Application configuration using Pydantic Settings.
"""

from typing import Optional
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None

    # Temporal
    temporal_address: Optional[str] = None
    temporal_namespace: Optional[str] = None

    # Replicate (AI generation)
    replicate_api_token: Optional[str] = None

    # App settings
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @property
    def use_supabase(self) -> bool:
        """Check if Supabase is configured."""
        return bool(self.supabase_url and self.supabase_key)

    @property
    def use_temporal(self) -> bool:
        """Check if Temporal is configured."""
        return bool(self.temporal_address and self.temporal_namespace)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience accessor
settings = get_settings()
