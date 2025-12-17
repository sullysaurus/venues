"""
Image serving endpoints.
Uses Supabase for metadata, filesystem for image files.
"""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.db import ImagesDB, VenuesDB
from api.schemas import SeatImage, ImageGalleryResponse

router = APIRouter()

# Base path for venues (needed for serving files)
VENUES_DIR = Path(__file__).parent.parent.parent / "venues"


@router.get("/{venue_id}")
async def list_images(venue_id: str, tier: Optional[str] = None, section: Optional[str] = None):
    """List all generated images for a venue."""
    venue = VenuesDB.get(venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    # Use resolved UUID from venue lookup (venue_id param could be a slug)
    actual_venue_id = venue["venue_id"]
    result = ImagesDB.list(actual_venue_id, tier=tier, section=section)
    images = [SeatImage(**img) for img in result["images"]]
    return ImageGalleryResponse(
        venue_id=actual_venue_id,
        images=images,
        total=result["total"],
    )


# IMPORTANT: Specific routes must come BEFORE generic /{venue_id}/{seat_id}
# Otherwise FastAPI will match "preview" as a seat_id

@router.get("/{venue_id}/preview")
async def get_model_preview(venue_id: str):
    """Get the 3D model preview URL for a venue (from Supabase Storage)."""
    from api.db import StorageDB

    # Get the Supabase URL for the preview
    preview_url = StorageDB.get_preview_url(venue_id)

    if preview_url:
        # Redirect to Supabase Storage URL
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=preview_url)

    # Fallback to local file
    venue_dir = VENUES_DIR / venue_id
    preview_path = venue_dir / "outputs" / "model_preview.png"
    if preview_path.exists():
        return FileResponse(
            preview_path,
            media_type="image/png",
            filename=f"{venue_id}_preview.png",
        )

    raise HTTPException(status_code=404, detail="Preview not found")


@router.get("/{venue_id}/model")
async def get_venue_model(venue_id: str):
    """Get the 3D model (.blend file) for a venue from Supabase Storage."""
    from api.db import StorageDB

    # Try Supabase first
    blend_url = StorageDB.get_blend_url(venue_id)
    if blend_url:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=blend_url)

    # Fallback to local file
    venue_dir = VENUES_DIR / venue_id
    blend_path = venue_dir / "venue_model.blend"
    if blend_path.exists():
        return FileResponse(
            blend_path,
            media_type="application/octet-stream",
            filename=f"{venue_id}_model.blend",
        )

    raise HTTPException(status_code=404, detail="Model not found")


@router.get("/{venue_id}/files")
async def list_venue_files(venue_id: str):
    """Debug endpoint: List all files in Supabase Storage for a venue."""
    from api.db.client import get_supabase_client

    try:
        client = get_supabase_client()
        files = client.storage.from_("IMAGES").list(venue_id)
        return {
            "venue_id": venue_id,
            "files": [
                {
                    "name": f["name"],
                    "size": f.get("metadata", {}).get("size"),
                    "updated_at": f.get("updated_at"),
                }
                for f in files
            ],
            "count": len(files),
        }
    except Exception as e:
        return {"venue_id": venue_id, "error": str(e), "files": []}


@router.get("/{venue_id}/seatmap/{event_type}")
async def get_seatmap(venue_id: str, event_type: str = "default"):
    """Get the seatmap image for a venue."""
    venue_dir = VENUES_DIR / venue_id
    if not venue_dir.exists():
        raise HTTPException(status_code=404, detail="Venue not found")

    seatmap_path = venue_dir / "seatmaps" / f"{event_type}.png"
    if not seatmap_path.exists():
        seatmap_path = venue_dir / "seatmaps" / "default.png"
    if not seatmap_path.exists():
        seatmaps_dir = venue_dir / "seatmaps"
        if seatmaps_dir.exists():
            pngs = list(seatmaps_dir.glob("*.png"))
            if pngs:
                seatmap_path = pngs[0]

    if not seatmap_path.exists():
        raise HTTPException(status_code=404, detail="Seatmap not found")

    return FileResponse(
        seatmap_path,
        media_type="image/png",
        filename=f"{venue_id}_seatmap.png",
    )


# Generic seat_id routes - must come AFTER specific routes like /preview and /seatmap

@router.get("/{venue_id}/{seat_id}")
async def get_image(venue_id: str, seat_id: str):
    """Get the generated image for a specific seat."""
    venue_dir = VENUES_DIR / venue_id
    if not venue_dir.exists():
        raise HTTPException(status_code=404, detail="Venue not found")

    image_path = venue_dir / "outputs" / "final_images" / f"{seat_id}_final.jpg"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(
        image_path,
        media_type="image/jpeg",
        filename=f"{venue_id}_{seat_id}.jpg",
    )


@router.get("/{venue_id}/{seat_id}/depth")
async def get_depth_map(venue_id: str, seat_id: str):
    """Get the depth map for a specific seat."""
    venue_dir = VENUES_DIR / venue_id
    if not venue_dir.exists():
        raise HTTPException(status_code=404, detail="Venue not found")

    depth_path = venue_dir / "outputs" / "depth_maps" / f"{seat_id}_depth.png"
    if not depth_path.exists():
        raise HTTPException(status_code=404, detail="Depth map not found")

    return FileResponse(
        depth_path,
        media_type="image/png",
        filename=f"{venue_id}_{seat_id}_depth.png",
    )


@router.delete("/{venue_id}/{seat_id}")
async def delete_image(venue_id: str, seat_id: str):
    """Delete a generated image."""
    venue = VenuesDB.get(venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    actual_venue_id = venue["venue_id"]
    venue_dir = VENUES_DIR / actual_venue_id

    image_path = venue_dir / "outputs" / "final_images" / f"{seat_id}_final.jpg"
    depth_path = venue_dir / "outputs" / "depth_maps" / f"{seat_id}_depth.png"

    deleted = []
    if image_path.exists():
        image_path.unlink()
        deleted.append("image")
    if depth_path.exists():
        depth_path.unlink()
        deleted.append("depth_map")

    # Also delete from Supabase
    ImagesDB.delete(actual_venue_id, seat_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="No files found")

    return {"status": "deleted", "files": deleted}
