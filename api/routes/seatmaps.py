"""
Seatmap API Routes

Handle seatmap image upload, AI extraction, and section management.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from typing import Optional
import uuid
import logging
from datetime import datetime

from api.db import get_supabase, resolve_venue_id
from api.schemas import (
    SeatmapExtractionResponse,
    SeatmapAdjustmentRequest,
    ExtractedSection,
    ExtractionStatus,
    ExtractionProvider,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ============== Seatmap Upload ==============

@router.post("/{venue_id}/seatmaps/upload")
async def upload_seatmap(
    venue_id: str,
    file: UploadFile = File(...),
    event_type_id: Optional[str] = Form(None),  # Optional now
    image_type: str = Form("seatmap"),  # 'seatmap' or 'reference'
):
    """
    Upload a seatmap or reference image for a venue.

    Args:
        venue_id: The venue ID or slug
        file: PNG/JPG image file
        event_type_id: Optional event type to associate with
        image_type: 'seatmap' for section extraction, 'reference' for IP-Adapter style
    """
    supabase = get_supabase()

    # Resolve venue_id (handle slug or UUID)
    actual_venue_id = resolve_venue_id(supabase, venue_id)

    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        # Read file content
        content = await file.read()

        # Generate storage path
        ext = file.filename.split(".")[-1] if file.filename else "png"
        filename = f"{image_type}_{uuid.uuid4().hex[:8]}.{ext}"
        storage_path = f"venues/{actual_venue_id}/seatmaps/{filename}"

        # Upload to Supabase Storage (bucket name is case-sensitive)
        storage_response = supabase.storage.from_("IMAGES").upload(
            storage_path,
            content,
            {"content-type": file.content_type}
        )

        # Get public URL
        public_url = supabase.storage.from_("IMAGES").get_public_url(storage_path)

        # Update venue with seatmap URL
        supabase.table("venues").update({
            "has_seatmap": True
        }).eq("id", actual_venue_id).execute()

        # If event_type_id provided, update it too
        if event_type_id:
            if image_type == "seatmap":
                supabase.table("event_types").update({
                    "seatmap_url": public_url
                }).eq("id", event_type_id).execute()
            elif image_type == "reference":
                supabase.table("event_types").update({
                    "reference_image_url": public_url
                }).eq("id", event_type_id).execute()

        logger.info(f"Uploaded {image_type} image for venue {actual_venue_id}")

        return {
            "status": "uploaded",
            "url": public_url,
            "image_type": image_type,
            "venue_id": actual_venue_id,
        }

    except Exception as e:
        logger.error(f"Error uploading seatmap: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== AI Extraction ==============

async def run_extraction(
    extraction_id: str,
    venue_id: str,
    seatmap_url: str,
):
    """Background task to run AI extraction."""
    try:
        supabase = get_supabase()
    except Exception:
        logger.error("Database not available for background extraction")
        return

    try:
        # Update status to processing
        supabase.table("seatmap_extractions").update({
            "status": ExtractionStatus.PROCESSING.value
        }).eq("id", extraction_id).execute()

        # Call Modal function for extraction
        # This will use either Replicate or OpenAI based on provider
        logger.info(f"Attempting Modal Function.lookup for extraction {extraction_id}")

        try:
            import modal
            logger.info(f"Modal import successful, version: {modal.__version__}")
        except ImportError as import_err:
            error_msg = f"Failed to import modal package: {import_err}"
            logger.error(error_msg)
            supabase.table("seatmap_extractions").update({
                "status": ExtractionStatus.FAILED.value,
                "error_message": error_msg,
            }).eq("id", extraction_id).execute()
            return

        try:
            logger.info("Looking up Modal function: venue-seat-views/extract_sections_from_seatmap")
            # Use Function.from_name() - the modern Modal API
            extract_fn = modal.Function.from_name("venue-seat-views", "extract_sections_from_seatmap")
            logger.info(f"Function lookup successful, calling with URL: {seatmap_url[:50]}...")
            result = extract_fn.remote(seatmap_url)  # Always uses OpenAI (default in Modal function)
            logger.info(f"Modal function returned: {len(result.get('sections', []))} sections")
        except Exception as modal_error:
            error_msg = f"Modal function call failed: {type(modal_error).__name__}: {modal_error}"
            logger.error(error_msg)
            supabase.table("seatmap_extractions").update({
                "status": ExtractionStatus.FAILED.value,
                "error_message": error_msg,
            }).eq("id", extraction_id).execute()
            return

        # Process results
        extracted_sections = []
        for section in result.get("sections", []):
            extracted_sections.append(ExtractedSection(
                section_id=section.get("section_id", f"section_{len(extracted_sections)}"),
                tier=section.get("tier", "lower"),
                angle=section.get("angle", 0.0),
                estimated_rows=section.get("estimated_rows", 15),
                inner_radius=section.get("inner_radius", 18.0),
                row_depth=section.get("row_depth", 0.85),
                row_rise=section.get("row_rise", 0.4),
                base_height=section.get("base_height", 2.0),
                confidence=section.get("confidence", 0.5),
                position_description=section.get("position_description"),
            ).model_dump())

        confidence_scores = result.get("confidence_scores", {})

        # Update extraction record
        supabase.table("seatmap_extractions").update({
            "status": ExtractionStatus.COMPLETED.value,
            "raw_extraction": result,
            "extracted_sections": extracted_sections,
            "confidence_scores": confidence_scores,
        }).eq("id", extraction_id).execute()

        logger.info(f"Extraction {extraction_id} completed with {len(extracted_sections)} sections")

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        supabase.table("seatmap_extractions").update({
            "status": ExtractionStatus.FAILED.value,
            "error_message": str(e),
        }).eq("id", extraction_id).execute()


@router.post("/{venue_id}/seatmaps/extract")
async def start_extraction(
    venue_id: str,
    background_tasks: BackgroundTasks,
    seatmap_url: Optional[str] = None,  # Query param, optional
):
    """
    Start AI extraction of sections from a seatmap image.

    This triggers a background task that analyzes the seatmap
    and extracts section definitions.
    """
    supabase = get_supabase()

    try:
        # Resolve venue_id (handle slug or UUID)
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        # If no seatmap_url provided, get the most recent one from storage
        if not seatmap_url:
            # List files in the venue's seatmaps folder
            storage_files = supabase.storage.from_("IMAGES").list(f"venues/{actual_venue_id}/seatmaps")
            seatmap_files = [f for f in storage_files if f['name'].startswith('seatmap_')]
            if not seatmap_files:
                raise HTTPException(status_code=400, detail="No seatmap uploaded for this venue")
            # Get the most recent one
            latest = sorted(seatmap_files, key=lambda x: x.get('created_at', ''), reverse=True)[0]
            seatmap_url = supabase.storage.from_("IMAGES").get_public_url(
                f"venues/{actual_venue_id}/seatmaps/{latest['name']}"
            )

        # Create extraction record
        extraction_id = str(uuid.uuid4())
        extraction_data = {
            "id": extraction_id,
            "venue_id": actual_venue_id,
            "seatmap_url": seatmap_url,
            "provider": "openai",  # Always use OpenAI
            "status": ExtractionStatus.PENDING.value,
        }

        supabase.table("seatmap_extractions").insert(extraction_data).execute()

        # Start background extraction (always uses OpenAI)
        background_tasks.add_task(
            run_extraction,
            extraction_id,
            actual_venue_id,
            seatmap_url,
        )

        logger.info(f"Started extraction {extraction_id} for venue {actual_venue_id}")

        return {
            "extraction_id": extraction_id,
            "status": ExtractionStatus.PENDING.value,
            "message": "Extraction started. Poll the extraction endpoint for progress.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting extraction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{venue_id}/seatmaps/extractions/{extraction_id}", response_model=SeatmapExtractionResponse)
async def get_extraction(venue_id: str, extraction_id: str):
    """Get the status and results of a seatmap extraction."""
    supabase = get_supabase()

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)
        response = supabase.table("seatmap_extractions").select("*").eq(
            "id", extraction_id
        ).eq("venue_id", actual_venue_id).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Extraction not found")

        row = response.data

        # Parse extracted sections
        extracted_sections = None
        if row.get("extracted_sections"):
            extracted_sections = [
                ExtractedSection(**section) for section in row["extracted_sections"]
            ]

        return SeatmapExtractionResponse(
            id=row["id"],
            venue_id=row["venue_id"],
            event_type_id=row.get("event_type_id"),
            seatmap_url=row["seatmap_url"],
            provider=ExtractionProvider(row.get("provider", "replicate")),
            status=ExtractionStatus(row["status"]),
            extracted_sections=extracted_sections,
            confidence_scores=row.get("confidence_scores"),
            error_message=row.get("error_message"),
            created_at=row.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting extraction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{venue_id}/seatmaps/extractions/{extraction_id}/adjust")
async def adjust_extraction(
    venue_id: str,
    extraction_id: str,
    request: SeatmapAdjustmentRequest,
):
    """
    Save user adjustments to extracted sections.

    Use this to modify section parameters before finalizing.
    """
    supabase = get_supabase()

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        # Convert sections to serializable format
        adjusted_sections = {
            section_id: section.model_dump()
            for section_id, section in request.sections.items()
        }

        response = supabase.table("seatmap_extractions").update({
            "user_adjustments": adjusted_sections,
            "extracted_sections": list(adjusted_sections.values()),
        }).eq("id", extraction_id).eq("venue_id", actual_venue_id).execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Extraction not found")

        logger.info(f"Saved adjustments for extraction {extraction_id}")

        return {
            "status": "updated",
            "sections_count": len(adjusted_sections),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adjusting extraction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{venue_id}/seatmaps/extractions/{extraction_id}/finalize")
async def finalize_extraction(
    venue_id: str,
    extraction_id: str,
):
    """
    Finalize extraction and commit sections to the database.

    This creates actual section records that can be used for pipeline execution.
    """
    supabase = get_supabase()

    try:
        # Resolve venue_id (handle slug or UUID)
        actual_venue_id = resolve_venue_id(supabase, venue_id)

        # Get extraction with adjusted sections
        extraction = supabase.table("seatmap_extractions").select("*").eq(
            "id", extraction_id
        ).eq("venue_id", actual_venue_id).single().execute()

        if not extraction.data:
            raise HTTPException(status_code=404, detail="Extraction not found")

        if extraction.data["status"] != ExtractionStatus.COMPLETED.value:
            raise HTTPException(status_code=400, detail="Extraction not completed")

        # Use adjusted sections if available, otherwise use extracted
        sections = extraction.data.get("user_adjustments") or extraction.data.get("extracted_sections", [])

        if not sections:
            raise HTTPException(status_code=400, detail="No sections to finalize")

        # Convert dict to list if needed
        if isinstance(sections, dict):
            sections = list(sections.values())

        logger.info(f"Finalizing {len(sections)} sections for venue {actual_venue_id}")

        # Delete existing sections for this venue (no event_type filter - replace all default sections)
        try:
            delete_result = supabase.table("sections").delete().eq(
                "venue_id", actual_venue_id
            ).is_("event_type_id", None).execute()
            logger.info(f"Deleted existing sections: {delete_result.data}")
        except Exception as delete_error:
            logger.warning(f"Delete sections error (continuing anyway): {delete_error}")

        # Insert new sections
        sections_to_insert = []
        for section in sections:
            section_id = section.get("section_id") or section.get("name") or f"Section_{len(sections_to_insert)+1}"
            section_data = {
                "id": str(uuid.uuid4()),
                "venue_id": actual_venue_id,
                "section_id": str(section_id),  # Ensure string
                "tier": section.get("tier", "lower"),
                "angle": float(section.get("angle", 0)),
                "inner_radius": float(section.get("inner_radius", 18.0)),
                "rows": int(section.get("estimated_rows", section.get("rows", 15))),
                "row_depth": float(section.get("row_depth", 0.85)),
                "row_rise": float(section.get("row_rise", 0.4)),
                "base_height": float(section.get("base_height", 2.0)),
            }
            sections_to_insert.append(section_data)
            logger.debug(f"Section to insert: {section_data}")

        if sections_to_insert:
            logger.info(f"Inserting {len(sections_to_insert)} sections...")
            insert_result = supabase.table("sections").insert(sections_to_insert).execute()
            logger.info(f"Insert result: {len(insert_result.data)} sections inserted")

        # Mark extraction as finalized
        supabase.table("seatmap_extractions").update({
            "finalized_at": datetime.utcnow().isoformat(),
        }).eq("id", extraction_id).execute()

        # Update venue has_seatmap flag
        supabase.table("venues").update({
            "has_seatmap": True
        }).eq("id", actual_venue_id).execute()

        logger.info(f"Finalized extraction {extraction_id} with {len(sections_to_insert)} sections")

        return {
            "status": "finalized",
            "sections_count": len(sections_to_insert),
            "venue_id": actual_venue_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finalizing extraction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{venue_id}/seatmaps/extractions")
async def list_extractions(venue_id: str, event_type_id: Optional[str] = None):
    """List all extractions for a venue, optionally filtered by event type."""
    supabase = get_supabase()

    try:
        actual_venue_id = resolve_venue_id(supabase, venue_id)
        query = supabase.table("seatmap_extractions").select("*").eq("venue_id", actual_venue_id)

        if event_type_id:
            query = query.eq("event_type_id", event_type_id)

        response = query.order("created_at", desc=True).execute()

        extractions = []
        for row in response.data:
            extractions.append({
                "id": row["id"],
                "event_type_id": row.get("event_type_id"),
                "seatmap_url": row["seatmap_url"],
                "provider": row.get("provider", "replicate"),
                "status": row["status"],
                "sections_count": len(row.get("extracted_sections", []) or []),
                "created_at": row.get("created_at"),
                "finalized_at": row.get("finalized_at"),
            })

        return {"extractions": extractions, "total": len(extractions)}

    except Exception as e:
        logger.error(f"Error listing extractions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
