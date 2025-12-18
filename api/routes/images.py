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


@router.get("/{venue_id}/assets")
async def get_venue_assets(venue_id: str):
    """Check what assets exist for a venue (for resume capability)."""
    from api.db.client import get_supabase_client

    result = {
        "venue_id": venue_id,
        "has_model": False,
        "has_preview": False,
        "has_depth_maps": False,
        "has_images": False,
        "depth_map_count": 0,
        "image_count": 0,
        "model_url": None,
        "preview_url": None,
    }

    try:
        client = get_supabase_client()
        bucket = client.storage.from_("IMAGES")

        # Check root folder for model and preview
        try:
            root_files = bucket.list(venue_id)
            for f in root_files:
                if f.get("name") == "venue_model.blend":
                    result["has_model"] = True
                    result["model_url"] = bucket.get_public_url(f"{venue_id}/venue_model.blend")
                elif f.get("name") == "preview.png":
                    result["has_preview"] = True
                    result["preview_url"] = bucket.get_public_url(f"{venue_id}/preview.png")
        except Exception:
            pass

        # Check depth_maps folder
        try:
            depth_files = bucket.list(f"{venue_id}/depth_maps")
            depth_count = sum(1 for f in depth_files if f.get("id") and f.get("name", "").endswith(".png"))
            result["depth_map_count"] = depth_count
            result["has_depth_maps"] = depth_count > 0
        except Exception:
            pass

        # Check final_images folder
        try:
            image_files = bucket.list(f"{venue_id}/final_images")
            image_count = sum(1 for f in image_files if f.get("id") and f.get("name", "").endswith(".jpg"))
            result["image_count"] = image_count
            result["has_images"] = image_count > 0
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)

    return result


@router.get("/{venue_id}/depth-maps")
async def list_depth_maps(venue_id: str):
    """List all depth maps for a venue from Supabase Storage."""
    from api.db.client import get_supabase_client

    try:
        client = get_supabase_client()
        bucket = client.storage.from_("IMAGES")

        depth_maps = []
        try:
            depth_files = bucket.list(f"{venue_id}/depth_maps")
            for f in depth_files:
                if f.get("id") and f.get("name", "").endswith(".png"):
                    # Extract seat_id from filename (e.g., "101_Front_1_depth.png" -> "101_Front_1")
                    seat_id = f["name"].replace("_depth.png", "")
                    url = bucket.get_public_url(f"{venue_id}/depth_maps/{f['name']}")
                    depth_maps.append({
                        "id": seat_id,
                        "url": url,
                        "name": f["name"],
                    })
        except Exception as e:
            # Folder may not exist yet
            pass

        return {
            "venue_id": venue_id,
            "depth_maps": depth_maps,
            "count": len(depth_maps),
        }
    except Exception as e:
        return {"venue_id": venue_id, "depth_maps": [], "count": 0, "error": str(e)}


@router.get("/{venue_id}/files")
async def list_venue_files(venue_id: str):
    """Debug endpoint: List all files in Supabase Storage for a venue."""
    from api.db.client import get_supabase_client

    try:
        client = get_supabase_client()
        all_files = []

        # List files in root venue folder
        root_files = client.storage.from_("IMAGES").list(venue_id)
        for f in root_files:
            if f.get("id"):  # Skip folder entries (they have no id)
                all_files.append({
                    "path": f"{venue_id}/{f['name']}",
                    "name": f["name"],
                    "size": f.get("metadata", {}).get("size"),
                    "updated_at": f.get("updated_at"),
                })

        # List files in depth_maps subfolder
        try:
            depth_files = client.storage.from_("IMAGES").list(f"{venue_id}/depth_maps")
            for f in depth_files:
                if f.get("id"):
                    all_files.append({
                        "path": f"{venue_id}/depth_maps/{f['name']}",
                        "name": f["name"],
                        "size": f.get("metadata", {}).get("size"),
                        "updated_at": f.get("updated_at"),
                    })
        except Exception:
            pass  # Folder may not exist

        # List files in final_images subfolder
        try:
            image_files = client.storage.from_("IMAGES").list(f"{venue_id}/final_images")
            for f in image_files:
                if f.get("id"):
                    all_files.append({
                        "path": f"{venue_id}/final_images/{f['name']}",
                        "name": f["name"],
                        "size": f.get("metadata", {}).get("size"),
                        "updated_at": f.get("updated_at"),
                    })
        except Exception:
            pass  # Folder may not exist

        return {
            "venue_id": venue_id,
            "files": all_files,
            "count": len(all_files),
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
