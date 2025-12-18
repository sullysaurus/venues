"""
Temporal activities for file storage operations.

These activities handle saving and loading files locally,
providing durability checkpoints for the workflow.
"""

import base64
import json
from pathlib import Path
from typing import Dict, List, Optional
from temporalio import activity


@activity.defn
async def save_seats_json_activity(
    venue_dir: str,
    venue_id: str,
    all_seats: List[dict],
    anchor_seats: List[dict]
) -> None:
    """
    Save seat data to JSON files.

    Args:
        venue_dir: Path to venue directory
        venue_id: Venue identifier
        all_seats: Complete list of generated seats
        anchor_seats: Subset of seats for rendering
    """
    venue_path = Path(venue_dir)
    venue_path.mkdir(parents=True, exist_ok=True)

    # Save all seats
    seats_path = venue_path / "seats.json"
    with open(seats_path, 'w') as f:
        json.dump({"venue": venue_id, "seats": all_seats}, f, indent=2)

    # Save anchor seats
    anchor_path = venue_path / "anchor_seats.json"
    with open(anchor_path, 'w') as f:
        json.dump(anchor_seats, f, indent=2)

    activity.logger.info(f"Saved {len(all_seats)} seats and {len(anchor_seats)} anchors to {venue_dir}")


@activity.defn
async def save_blend_file_activity(venue_dir: str, model_data: Dict[str, str]) -> Dict[str, str]:
    """
    Save .blend file and preview image to Supabase Storage.

    Args:
        venue_dir: Path to venue directory (e.g., "venues/venue-uuid")
        model_data: Dict with 'blend_file' and optional 'preview_image' (both base64)

    Returns:
        Dict with URLs to saved files
    """
    import os
    from supabase import create_client

    venue_path = Path(venue_dir)
    venue_id = venue_path.name

    result = {}

    # Get Supabase client
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    client = None

    if supabase_url and supabase_key:
        try:
            client = create_client(supabase_url, supabase_key)
        except Exception as e:
            activity.logger.warning(f"Failed to create Supabase client: {e}")

    # Upload blend file to Supabase
    blend_b64 = model_data.get("blend_file")
    if blend_b64:
        blend_bytes = base64.b64decode(blend_b64)

        if client:
            try:
                file_path = f"{venue_id}/venue_model.blend"
                client.storage.from_("IMAGES").upload(
                    file_path,
                    blend_bytes,
                    file_options={"content-type": "application/octet-stream", "upsert": "true"}
                )
                blend_url = client.storage.from_("IMAGES").get_public_url(file_path)
                result["blend_url"] = blend_url
                activity.logger.info(f"Uploaded blend file to Supabase: {file_path} ({len(blend_bytes)} bytes)")
            except Exception as e:
                activity.logger.warning(f"Failed to upload blend to Supabase: {e}")
                # Fall back to local
                venue_path.mkdir(parents=True, exist_ok=True)
                blend_path = venue_path / "venue_model.blend"
                with open(blend_path, 'wb') as f:
                    f.write(blend_bytes)
                result["blend_path"] = str(blend_path)
        else:
            # No Supabase, save locally
            venue_path.mkdir(parents=True, exist_ok=True)
            blend_path = venue_path / "venue_model.blend"
            with open(blend_path, 'wb') as f:
                f.write(blend_bytes)
            result["blend_path"] = str(blend_path)
            activity.logger.info(f"Saved blend file locally: {blend_path} ({len(blend_bytes)} bytes)")

    # Upload preview image to Supabase
    preview_b64 = model_data.get("preview_image")
    if preview_b64:
        preview_bytes = base64.b64decode(preview_b64)

        if client:
            try:
                file_path = f"{venue_id}/preview.png"
                client.storage.from_("IMAGES").upload(
                    file_path,
                    preview_bytes,
                    file_options={"content-type": "image/png", "upsert": "true"}
                )
                preview_url = client.storage.from_("IMAGES").get_public_url(file_path)
                result["preview_url"] = preview_url
                activity.logger.info(f"Uploaded preview to Supabase: {file_path}")
            except Exception as e:
                activity.logger.warning(f"Failed to upload preview to Supabase: {e}")
                # Fall back to local
                preview_path = venue_path / "outputs" / "model_preview.png"
                preview_path.parent.mkdir(parents=True, exist_ok=True)
                with open(preview_path, 'wb') as f:
                    f.write(preview_bytes)
                result["preview_path"] = str(preview_path)
        else:
            # No Supabase, save locally
            preview_path = venue_path / "outputs" / "model_preview.png"
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            with open(preview_path, 'wb') as f:
                f.write(preview_bytes)
            result["preview_path"] = str(preview_path)
            activity.logger.info(f"Saved preview locally: {preview_path}")

    return result


@activity.defn
async def save_depth_maps_activity(
    venue_dir: str,
    depth_maps: Dict[str, str]
) -> Dict[str, str]:
    """
    Save depth maps to Supabase Storage.

    Args:
        venue_dir: Path to venue directory (e.g., "venues/venue-uuid")
        depth_maps: Dictionary mapping seat_id to base64-encoded PNG

    Returns:
        Dictionary mapping seat_id to Supabase URL
    """
    import os
    from supabase import create_client

    venue_path = Path(venue_dir)
    venue_id = venue_path.name

    # Get Supabase client
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    client = None

    if supabase_url and supabase_key:
        try:
            client = create_client(supabase_url, supabase_key)
        except Exception as e:
            activity.logger.warning(f"Failed to create Supabase client: {e}")

    urls = {}
    for seat_id, b64_data in depth_maps.items():
        image_bytes = base64.b64decode(b64_data)

        if client:
            try:
                file_path = f"{venue_id}/depth_maps/{seat_id}_depth.png"
                client.storage.from_("IMAGES").upload(
                    file_path,
                    image_bytes,
                    file_options={"content-type": "image/png", "upsert": "true"}
                )
                url = client.storage.from_("IMAGES").get_public_url(file_path)
                urls[seat_id] = url
            except Exception as e:
                activity.logger.warning(f"Failed to upload depth map {seat_id}: {e}")
                # Fall back to local
                depth_dir = Path(venue_dir) / "outputs" / "depth_maps"
                depth_dir.mkdir(parents=True, exist_ok=True)
                path = depth_dir / f"{seat_id}_depth.png"
                with open(path, 'wb') as f:
                    f.write(image_bytes)
                urls[seat_id] = str(path)
        else:
            # No Supabase, save locally
            depth_dir = Path(venue_dir) / "outputs" / "depth_maps"
            depth_dir.mkdir(parents=True, exist_ok=True)
            path = depth_dir / f"{seat_id}_depth.png"
            with open(path, 'wb') as f:
                f.write(image_bytes)
            urls[seat_id] = str(path)

    activity.logger.info(f"Saved {len(urls)} depth maps to Supabase")
    return urls


@activity.defn
async def save_generated_images_activity(
    venue_dir: str,
    images: Dict[str, str]
) -> Dict[str, str]:
    """
    Save generated images to Supabase Storage.

    Args:
        venue_dir: Path to venue directory (e.g., "venues/venue-uuid")
        images: Dictionary mapping seat_id to base64-encoded JPEG

    Returns:
        Dictionary mapping seat_id to Supabase URL
    """
    import os
    from supabase import create_client

    venue_path = Path(venue_dir)
    venue_id = venue_path.name

    # Get Supabase client
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    client = None

    if supabase_url and supabase_key:
        try:
            client = create_client(supabase_url, supabase_key)
        except Exception as e:
            activity.logger.warning(f"Failed to create Supabase client: {e}")

    urls = {}
    for seat_id, b64_data in images.items():
        image_bytes = base64.b64decode(b64_data)

        if client:
            try:
                file_path = f"{venue_id}/final_images/{seat_id}_final.jpg"
                client.storage.from_("IMAGES").upload(
                    file_path,
                    image_bytes,
                    file_options={"content-type": "image/jpeg", "upsert": "true"}
                )
                url = client.storage.from_("IMAGES").get_public_url(file_path)
                urls[seat_id] = url
            except Exception as e:
                activity.logger.warning(f"Failed to upload image {seat_id}: {e}")
                # Fall back to local
                images_dir = Path(venue_dir) / "outputs" / "final_images"
                images_dir.mkdir(parents=True, exist_ok=True)
                path = images_dir / f"{seat_id}_final.jpg"
                with open(path, 'wb') as f:
                    f.write(image_bytes)
                urls[seat_id] = str(path)
        else:
            # No Supabase, save locally
            images_dir = Path(venue_dir) / "outputs" / "final_images"
            images_dir.mkdir(parents=True, exist_ok=True)
            path = images_dir / f"{seat_id}_final.jpg"
            with open(path, 'wb') as f:
                f.write(image_bytes)
            urls[seat_id] = str(path)

    activity.logger.info(f"Saved {len(urls)} images to Supabase")
    return urls


@activity.defn
async def load_existing_images_activity(venue_dir: str) -> Dict[str, str]:
    """
    Load existing generated images for resume capability.

    Args:
        venue_dir: Path to venue directory

    Returns:
        Dictionary mapping seat_id to file path (not bytes, to save memory)
    """
    images_dir = Path(venue_dir) / "outputs" / "final_images"
    if not images_dir.exists():
        return {}

    result = {}
    for path in images_dir.glob("*_final.jpg"):
        seat_id = path.stem.replace("_final", "")
        result[seat_id] = str(path)

    activity.logger.info(f"Found {len(result)} existing images in {images_dir}")
    return result


@activity.defn
async def load_existing_blend_activity(venue_id: str) -> Optional[str]:
    """
    Load existing .blend file from Supabase Storage.

    Args:
        venue_id: Venue identifier

    Returns:
        Base64-encoded blend file, or None if not found
    """
    import os
    from supabase import create_client

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        activity.logger.warning("Supabase not configured, cannot load existing blend file")
        return None

    try:
        client = create_client(supabase_url, supabase_key)
        file_path = f"{venue_id}/venue_model.blend"

        blend_bytes = client.storage.from_("IMAGES").download(file_path)
        if blend_bytes:
            activity.logger.info(f"Loaded existing blend file: {len(blend_bytes)} bytes")
            return base64.b64encode(blend_bytes).decode('utf-8')
    except Exception as e:
        activity.logger.warning(f"Failed to load blend file from Supabase: {e}")

    return None


@activity.defn
async def load_existing_depth_maps_activity(venue_id: str) -> Dict[str, str]:
    """
    Load existing depth maps from Supabase Storage.

    Args:
        venue_id: Venue identifier

    Returns:
        Dictionary mapping seat_id to base64-encoded PNG
    """
    import os
    from supabase import create_client

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        activity.logger.warning("Supabase not configured, cannot load existing depth maps")
        return {}

    try:
        client = create_client(supabase_url, supabase_key)
        bucket = client.storage.from_("IMAGES")

        # List depth maps
        depth_files = bucket.list(f"{venue_id}/depth_maps")
        result = {}

        for f in depth_files:
            if f.get("id") and f.get("name", "").endswith(".png"):
                file_path = f"{venue_id}/depth_maps/{f['name']}"
                try:
                    depth_bytes = bucket.download(file_path)
                    if depth_bytes:
                        # Extract seat_id from filename (e.g., "103_Back_1_depth.png" -> "103_Back_1")
                        seat_id = f["name"].replace("_depth.png", "")
                        result[seat_id] = base64.b64encode(depth_bytes).decode('utf-8')
                except Exception as e:
                    activity.logger.warning(f"Failed to download {file_path}: {e}")

        activity.logger.info(f"Loaded {len(result)} existing depth maps from Supabase")
        return result

    except Exception as e:
        activity.logger.warning(f"Failed to list depth maps: {e}")
        return {}
