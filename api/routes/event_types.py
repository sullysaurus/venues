"""
Event Types API Routes

Manage event type configurations (hockey, basketball, concert) per venue.
"""

from fastapi import APIRouter, HTTPException
import uuid
import logging

from api.db import get_supabase, resolve_venue_id
from api.schemas import (
    EventTypeCreate,
    EventTypeUpdate,
    EventTypeResponse,
    EventTypeListResponse,
    SurfaceConfig,
    SurfaceType,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# Default surface configurations for each event type
DEFAULT_SURFACE_CONFIGS = {
    SurfaceType.RINK: SurfaceConfig(
        length=60.0,
        width=26.0,
        boards=True,
        boards_height=1.2,
        extra={"surface_color": [0.9, 0.95, 1.0], "line_color": [0.8, 0.0, 0.0]}
    ),
    SurfaceType.COURT: SurfaceConfig(
        length=28.65,
        width=15.24,
        boards=False,
        boards_height=0,
        extra={"surface_color": [0.76, 0.60, 0.42], "line_color": [1.0, 1.0, 1.0]}
    ),
    SurfaceType.STAGE: SurfaceConfig(
        length=20.0,
        width=15.0,
        boards=False,
        boards_height=0,
        extra={"stage_height": 1.2, "thrust": False}
    ),
    SurfaceType.FIELD: SurfaceConfig(
        length=100.0,
        width=64.0,
        boards=False,
        boards_height=0,
        extra={"surface_color": [0.2, 0.6, 0.2], "endzone_length": 10.0}
    ),
}


@router.get("/{venue_id}/event-types", response_model=EventTypeListResponse)
async def list_event_types(venue_id: str):
    """List all event types for a venue."""
    supabase = get_supabase()

    try:
        # Resolve venue_id (handle slug or UUID)
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        # Get event types with section counts
        response = supabase.table("event_types").select(
            "*, sections:sections(count)"
        ).eq("venue_id", actual_venue_id).order("created_at").execute()

        event_types = []
        for row in response.data:
            sections_count = row.get("sections", [{}])[0].get("count", 0) if row.get("sections") else 0
            event_types.append(EventTypeResponse(
                id=row["id"],
                venue_id=row["venue_id"],
                name=row["name"],
                display_name=row["display_name"],
                seatmap_url=row.get("seatmap_url"),
                reference_image_url=row.get("reference_image_url"),
                surface_type=SurfaceType(row["surface_type"]),
                surface_config=SurfaceConfig(**row.get("surface_config", {})) if row.get("surface_config") else SurfaceConfig(),
                is_default=row.get("is_default", False),
                sections_count=sections_count,
                created_at=row.get("created_at"),
            ))

        return EventTypeListResponse(event_types=event_types, total=len(event_types))

    except Exception as e:
        logger.error(f"Error listing event types: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{venue_id}/event-types", response_model=EventTypeResponse)
async def create_event_type(venue_id: str, request: EventTypeCreate):
    """Create a new event type for a venue."""
    supabase = get_supabase()

    try:
        # Resolve venue_id (handle slug or UUID)
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        # Use default surface config if not provided
        surface_config = request.surface_config or DEFAULT_SURFACE_CONFIGS.get(
            request.surface_type,
            SurfaceConfig()
        )

        # If this is set as default, unset any existing default
        if request.is_default:
            supabase.table("event_types").update(
                {"is_default": False}
            ).eq("venue_id", actual_venue_id).execute()

        # Create event type
        event_type_id = str(uuid.uuid4())
        data = {
            "id": event_type_id,
            "venue_id": actual_venue_id,
            "name": request.name.lower().replace(" ", "_"),
            "display_name": request.display_name,
            "surface_type": request.surface_type.value,
            "surface_config": surface_config.model_dump(),
            "is_default": request.is_default,
        }

        response = supabase.table("event_types").insert(data).execute()
        row = response.data[0]

        logger.info(f"Created event type {request.name} for venue {venue_id}")

        return EventTypeResponse(
            id=row["id"],
            venue_id=row["venue_id"],
            name=row["name"],
            display_name=row["display_name"],
            seatmap_url=row.get("seatmap_url"),
            reference_image_url=row.get("reference_image_url"),
            surface_type=SurfaceType(row["surface_type"]),
            surface_config=SurfaceConfig(**row.get("surface_config", {})),
            is_default=row.get("is_default", False),
            sections_count=0,
            created_at=row.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating event type: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{venue_id}/event-types/{event_type_id}", response_model=EventTypeResponse)
async def get_event_type(venue_id: str, event_type_id: str):
    """Get a specific event type with its details."""
    supabase = get_supabase()

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)
        response = supabase.table("event_types").select(
            "*, sections:sections(count)"
        ).eq("id", event_type_id).eq("venue_id", actual_venue_id).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Event type not found")

        row = response.data
        sections_count = row.get("sections", [{}])[0].get("count", 0) if row.get("sections") else 0

        return EventTypeResponse(
            id=row["id"],
            venue_id=row["venue_id"],
            name=row["name"],
            display_name=row["display_name"],
            seatmap_url=row.get("seatmap_url"),
            reference_image_url=row.get("reference_image_url"),
            surface_type=SurfaceType(row["surface_type"]),
            surface_config=SurfaceConfig(**row.get("surface_config", {})) if row.get("surface_config") else SurfaceConfig(),
            is_default=row.get("is_default", False),
            sections_count=sections_count,
            created_at=row.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting event type: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{venue_id}/event-types/{event_type_id}", response_model=EventTypeResponse)
async def update_event_type(venue_id: str, event_type_id: str, request: EventTypeUpdate):
    """Update an event type."""
    supabase = get_supabase()

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        # Build update data
        update_data = {}
        if request.display_name is not None:
            update_data["display_name"] = request.display_name
        if request.surface_type is not None:
            update_data["surface_type"] = request.surface_type.value
        if request.surface_config is not None:
            update_data["surface_config"] = request.surface_config.model_dump()
        if request.is_default is not None:
            # If setting as default, unset others first
            if request.is_default:
                supabase.table("event_types").update(
                    {"is_default": False}
                ).eq("venue_id", actual_venue_id).execute()
            update_data["is_default"] = request.is_default

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        response = supabase.table("event_types").update(update_data).eq(
            "id", event_type_id
        ).eq("venue_id", actual_venue_id).execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Event type not found")

        # Return updated event type
        return await get_event_type(venue_id, event_type_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating event type: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{venue_id}/event-types/{event_type_id}")
async def delete_event_type(venue_id: str, event_type_id: str):
    """Delete an event type and its associated sections."""
    supabase = get_supabase()

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        # Delete event type (sections will cascade delete)
        response = supabase.table("event_types").delete().eq(
            "id", event_type_id
        ).eq("venue_id", actual_venue_id).execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Event type not found")

        logger.info(f"Deleted event type {event_type_id} for venue {venue_id}")

        return {"status": "deleted", "event_type_id": event_type_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting event type: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{venue_id}/event-types/{event_type_id}/set-default")
async def set_default_event_type(venue_id: str, event_type_id: str):
    """Set an event type as the default for the venue."""
    supabase = get_supabase()

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        # Unset all defaults for this venue
        supabase.table("event_types").update(
            {"is_default": False}
        ).eq("venue_id", actual_venue_id).execute()

        # Set this one as default
        response = supabase.table("event_types").update(
            {"is_default": True}
        ).eq("id", event_type_id).eq("venue_id", actual_venue_id).execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Event type not found")

        logger.info(f"Set event type {event_type_id} as default for venue {venue_id}")

        return {"status": "updated", "event_type_id": event_type_id, "is_default": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting default event type: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{venue_id}/event-types/{event_type_id}/sections")
async def get_event_type_sections(venue_id: str, event_type_id: str):
    """Get all sections for a specific event type."""
    supabase = get_supabase()

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)
        response = supabase.table("sections").select("*").eq(
            "venue_id", actual_venue_id
        ).eq("event_type_id", event_type_id).execute()

        sections = {}
        for row in response.data:
            sections[row["section_id"]] = {
                "section_id": row["section_id"],
                "tier": row["tier"],
                "angle": row["angle"],
                "inner_radius": row["inner_radius"],
                "rows": row["rows"],
                "row_depth": row["row_depth"],
                "row_rise": row["row_rise"],
                "base_height": row["base_height"],
            }

        return {"sections": sections, "total": len(sections)}

    except Exception as e:
        logger.error(f"Error getting event type sections: {e}")
        raise HTTPException(status_code=500, detail=str(e))
