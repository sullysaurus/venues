"""
Venue management endpoints.
Uses Supabase for data storage.
"""

from fastapi import APIRouter, HTTPException

from api.db import VenuesDB
from api.schemas import (
    VenueCreate,
    VenueResponse,
    VenueListResponse,
)

router = APIRouter()


@router.get("/", response_model=VenueListResponse)
async def list_venues():
    """List all venues."""
    try:
        result = VenuesDB.list()
        venues = [VenueResponse(**v) for v in result["venues"]]
        return VenueListResponse(venues=venues, total=result["total"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=VenueResponse)
async def create_venue(request: VenueCreate):
    """Create a new venue."""
    try:
        result = VenuesDB.create(name=request.name, location=request.location)
        return VenueResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{venue_id}", response_model=VenueResponse)
async def get_venue(venue_id: str):
    """Get venue details."""
    result = VenuesDB.get(venue_id)
    if not result:
        raise HTTPException(status_code=404, detail="Venue not found")
    return VenueResponse(**result)


@router.delete("/{venue_id}")
async def delete_venue(venue_id: str):
    """Delete a venue."""
    venue = VenuesDB.get(venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    actual_venue_id = venue["venue_id"]
    VenuesDB.delete(actual_venue_id)
    return {"status": "deleted", "venue_id": actual_venue_id}


@router.get("/{venue_id}/sections")
async def get_sections(venue_id: str):
    """Get venue sections."""
    venue = VenuesDB.get(venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    actual_venue_id = venue["venue_id"]
    return VenuesDB.get_sections(actual_venue_id)


@router.put("/{venue_id}/sections")
async def update_sections(venue_id: str, sections: dict):
    """Update venue sections."""
    venue = VenuesDB.get(venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    actual_venue_id = venue["venue_id"]
    VenuesDB.update_sections(actual_venue_id, sections)
    return {"status": "updated", "sections_count": len(sections)}


@router.get("/{venue_id}/config")
async def get_config(venue_id: str):
    """Get venue configuration."""
    result = VenuesDB.get(venue_id)
    if not result:
        raise HTTPException(status_code=404, detail="Venue not found")
    return {
        "config": {
            "venue_id": result["venue_id"],
            "name": result["name"],
            "location": result.get("location"),
        }
    }


@router.put("/{venue_id}/config")
async def update_config(venue_id: str, config: dict):
    """Update venue configuration."""
    venue = VenuesDB.get(venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    actual_venue_id = venue["venue_id"]
    VenuesDB.update(actual_venue_id, **config)
    return {"status": "updated"}
