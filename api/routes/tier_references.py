"""
Tier Reference API Routes

Handle uploading and managing reference images for each tier level.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional
import uuid
import logging

from api.db import get_supabase, resolve_venue_id
from api.schemas import (
    TierReferenceResponse,
    TierReferenceListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Valid tier values
VALID_TIERS = ["floor", "lower", "mid", "upper", "club"]


@router.get("/{venue_id}/tier-references", response_model=TierReferenceListResponse)
async def list_tier_references(venue_id: str):
    """List all tier reference images for a venue."""
    supabase = get_supabase()

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        response = supabase.table("tier_references").select("*").eq(
            "venue_id", actual_venue_id
        ).execute()

        tier_references = []
        for row in response.data:
            tier_references.append(TierReferenceResponse(
                id=row["id"],
                venue_id=row["venue_id"],
                tier=row["tier"],
                reference_image_url=row["reference_image_url"],
                ip_adapter_scale=row.get("ip_adapter_scale", 0.7),
                created_at=row.get("created_at"),
            ))

        return TierReferenceListResponse(
            venue_id=actual_venue_id,
            tier_references=tier_references,
            total=len(tier_references),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing tier references: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{venue_id}/tier-references/{tier}", response_model=TierReferenceResponse)
async def get_tier_reference(venue_id: str, tier: str):
    """Get the reference image for a specific tier."""
    supabase = get_supabase()

    if tier not in VALID_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier. Must be one of: {', '.join(VALID_TIERS)}"
        )

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        response = supabase.table("tier_references").select("*").eq(
            "venue_id", actual_venue_id
        ).eq("tier", tier).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail=f"No reference image for tier: {tier}")

        row = response.data
        return TierReferenceResponse(
            id=row["id"],
            venue_id=row["venue_id"],
            tier=row["tier"],
            reference_image_url=row["reference_image_url"],
            ip_adapter_scale=row.get("ip_adapter_scale", 0.7),
            created_at=row.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tier reference: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{venue_id}/tier-references/{tier}", response_model=TierReferenceResponse)
async def upload_tier_reference(
    venue_id: str,
    tier: str,
    file: UploadFile = File(...),
    ip_adapter_scale: float = Form(0.7),
):
    """
    Upload or replace a reference image for a specific tier.

    Args:
        venue_id: The venue ID or slug
        tier: The tier level (floor, lower, mid, upper, club)
        file: PNG/JPG image file
        ip_adapter_scale: IP-Adapter strength for this tier (0.0-1.0)
    """
    supabase = get_supabase()

    if tier not in VALID_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier. Must be one of: {', '.join(VALID_TIERS)}"
        )

    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Validate ip_adapter_scale
    if not 0.0 <= ip_adapter_scale <= 1.0:
        raise HTTPException(status_code=400, detail="ip_adapter_scale must be between 0.0 and 1.0")

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        # Read file content
        content = await file.read()

        # Generate storage path
        ext = file.filename.split(".")[-1] if file.filename else "png"
        filename = f"tier_ref_{tier}_{uuid.uuid4().hex[:8]}.{ext}"
        storage_path = f"venues/{actual_venue_id}/tier_references/{filename}"

        # Upload to Supabase Storage
        supabase.storage.from_("IMAGES").upload(
            storage_path,
            content,
            {"content-type": file.content_type}
        )

        # Get public URL
        public_url = supabase.storage.from_("IMAGES").get_public_url(storage_path)

        # Check if reference already exists for this tier
        existing = supabase.table("tier_references").select("id").eq(
            "venue_id", actual_venue_id
        ).eq("tier", tier).execute()

        if existing.data:
            # Update existing record
            ref_id = existing.data[0]["id"]
            supabase.table("tier_references").update({
                "reference_image_url": public_url,
                "ip_adapter_scale": ip_adapter_scale,
            }).eq("id", ref_id).execute()
            logger.info(f"Updated tier reference for {tier} on venue {actual_venue_id}")
        else:
            # Create new record
            ref_id = str(uuid.uuid4())
            supabase.table("tier_references").insert({
                "id": ref_id,
                "venue_id": actual_venue_id,
                "tier": tier,
                "reference_image_url": public_url,
                "ip_adapter_scale": ip_adapter_scale,
            }).execute()
            logger.info(f"Created tier reference for {tier} on venue {actual_venue_id}")

        # Fetch the complete record
        response = supabase.table("tier_references").select("*").eq(
            "venue_id", actual_venue_id
        ).eq("tier", tier).single().execute()

        row = response.data
        return TierReferenceResponse(
            id=row["id"],
            venue_id=row["venue_id"],
            tier=row["tier"],
            reference_image_url=row["reference_image_url"],
            ip_adapter_scale=row.get("ip_adapter_scale", 0.7),
            created_at=row.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading tier reference: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{venue_id}/tier-references/{tier}")
async def update_tier_reference(
    venue_id: str,
    tier: str,
    ip_adapter_scale: float = Form(...),
):
    """Update the IP-adapter scale for a tier reference (without re-uploading image)."""
    supabase = get_supabase()

    if tier not in VALID_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier. Must be one of: {', '.join(VALID_TIERS)}"
        )

    if not 0.0 <= ip_adapter_scale <= 1.0:
        raise HTTPException(status_code=400, detail="ip_adapter_scale must be between 0.0 and 1.0")

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        response = supabase.table("tier_references").update({
            "ip_adapter_scale": ip_adapter_scale,
        }).eq("venue_id", actual_venue_id).eq("tier", tier).execute()

        if not response.data:
            raise HTTPException(status_code=404, detail=f"No reference image for tier: {tier}")

        return {"status": "updated", "tier": tier, "ip_adapter_scale": ip_adapter_scale}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating tier reference: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{venue_id}/tier-references/{tier}")
async def delete_tier_reference(venue_id: str, tier: str):
    """Delete the reference image for a specific tier."""
    supabase = get_supabase()

    if tier not in VALID_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier. Must be one of: {', '.join(VALID_TIERS)}"
        )

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        # Get the record first to find the storage path
        existing = supabase.table("tier_references").select("*").eq(
            "venue_id", actual_venue_id
        ).eq("tier", tier).execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail=f"No reference image for tier: {tier}")

        # Delete from database
        supabase.table("tier_references").delete().eq(
            "venue_id", actual_venue_id
        ).eq("tier", tier).execute()

        # Note: We don't delete from storage to avoid potential issues with
        # orphaned files. The storage can be cleaned up separately if needed.

        logger.info(f"Deleted tier reference for {tier} on venue {actual_venue_id}")

        return {"status": "deleted", "tier": tier}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tier reference: {e}")
        raise HTTPException(status_code=500, detail=str(e))
