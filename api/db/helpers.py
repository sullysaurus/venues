"""
Shared database helper functions.

Consolidates duplicate helper functions from route files.
"""

from fastapi import HTTPException

from api.config import settings


def get_supabase():
    """
    Get Supabase client if available.

    Returns:
        Supabase client instance

    Raises:
        HTTPException: 503 if database not configured
    """
    if not settings.use_supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    from api.db import get_supabase_client
    return get_supabase_client()


def resolve_venue_id(supabase, venue_id: str) -> str:
    """
    Resolve venue_id (UUID or slug) to actual UUID.

    Args:
        supabase: Supabase client instance
        venue_id: Either a UUID or a slug string

    Returns:
        The venue UUID

    Raises:
        HTTPException: 404 if venue not found
    """
    is_uuid = len(venue_id) == 36 and '-' in venue_id
    if is_uuid:
        return venue_id
    result = supabase.table("venues").select("id").eq("slug", venue_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Venue not found")
    return result.data["id"]
