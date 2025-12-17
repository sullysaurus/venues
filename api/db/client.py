"""
Supabase client configuration.
"""

from functools import lru_cache
from supabase import create_client, Client

from api.config import settings


@lru_cache()
def get_supabase_client() -> Client:
    """Get cached Supabase client."""
    if not settings.supabase_url or not settings.supabase_key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY environment variables must be set"
        )
    return create_client(settings.supabase_url, settings.supabase_key)
