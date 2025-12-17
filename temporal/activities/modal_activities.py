"""
Temporal activities that wrap Modal function calls.

These activities provide the bridge between Temporal orchestration
and Modal compute for Blender and AI generation.
"""

import base64
from typing import Dict, List, Optional, Tuple
from temporalio import activity

# Modal app name (must match modal_app.py)
MODAL_APP_NAME = "venue-seat-views"


@activity.defn
async def generate_seats_activity(sections: Dict[str, dict]) -> Tuple[List[dict], List[dict], List[dict]]:
    """
    Generate seat coordinates from section definitions.

    Args:
        sections: Dictionary mapping section_id to section config

    Returns:
        Tuple of (all_seats, sample_seats, anchor_seats)
    """
    import modal

    activity.heartbeat(f"Generating seats for {len(sections)} sections")

    generate_seats = modal.Function.from_name(MODAL_APP_NAME, "generate_seats")
    result = generate_seats.remote(sections)

    activity.logger.info(f"Generated {len(result[0])} total seats, {len(result[2])} anchor seats")
    return result


@activity.defn
async def build_venue_model_activity(config: dict, sections: dict) -> Dict[str, Optional[str]]:
    """
    Build 3D venue model in Blender via Modal.

    Args:
        config: Venue configuration dictionary
        sections: Section definitions

    Returns:
        Dict with 'blend_file' (base64) and 'preview_image' (base64 or None)
    """
    import modal

    activity.heartbeat("Building 3D venue model with Blender 4.2")

    build_venue = modal.Function.from_name(MODAL_APP_NAME, "build_venue_model")
    result = build_venue.remote(config, sections)

    blend_bytes = result["blend_file"]
    preview_bytes = result.get("preview_image")

    # Encode as base64 for workflow state persistence
    blend_b64 = base64.b64encode(blend_bytes).decode('utf-8')
    preview_b64 = base64.b64encode(preview_bytes).decode('utf-8') if preview_bytes else None

    activity.logger.info(f"Built venue model: {len(blend_bytes)} bytes, preview: {len(preview_bytes) if preview_bytes else 0} bytes")

    return {
        "blend_file": blend_b64,
        "preview_image": preview_b64,
    }


@activity.defn
async def render_depth_maps_activity(
    blend_file_b64: str,
    seats: List[dict],
    batch_id: int = 0
) -> Dict[str, str]:
    """
    Render depth maps for a batch of seats.

    Args:
        blend_file_b64: Base64-encoded .blend file
        seats: List of seat dictionaries to render
        batch_id: Batch identifier for logging

    Returns:
        Dictionary mapping seat_id to base64-encoded PNG bytes
    """
    import modal

    activity.heartbeat(f"Rendering depth maps batch {batch_id}: {len(seats)} seats")

    # Decode blend file
    blend_bytes = base64.b64decode(blend_file_b64)

    render_depths = modal.Function.from_name(MODAL_APP_NAME, "render_depth_maps")
    depth_maps = render_depths.remote(blend_bytes, seats)

    # Encode results as base64
    result = {}
    for seat_id, png_bytes in depth_maps.items():
        result[seat_id] = base64.b64encode(png_bytes).decode('utf-8')
        activity.heartbeat(f"Rendered {seat_id}")

    activity.logger.info(f"Rendered {len(result)} depth maps in batch {batch_id}")
    return result


@activity.defn
async def generate_ai_image_activity(
    depth_map_b64: str,
    seat_id: str,
    prompt: str,
    model: str = "flux",
    strength: float = 0.75,
    reference_image_b64: Optional[str] = None,
    ip_adapter_scale: float = 0.6
) -> Optional[str]:
    """
    Generate a single AI image from a depth map.

    Args:
        depth_map_b64: Base64-encoded depth map PNG
        seat_id: Seat identifier for logging
        prompt: Text prompt for generation
        model: Model to use (flux, sdxl, controlnet, ip_adapter)
        strength: Generation strength (0-1)
        reference_image_b64: Optional base64-encoded reference image
        ip_adapter_scale: Style influence strength (0-1)

    Returns:
        Base64-encoded JPEG bytes, or None on failure
    """
    import modal

    activity.heartbeat(f"Generating AI image for {seat_id} with {model}")

    # Decode inputs
    depth_bytes = base64.b64decode(depth_map_b64)
    reference_bytes = base64.b64decode(reference_image_b64) if reference_image_b64 else None

    generate_image = modal.Function.from_name(MODAL_APP_NAME, "generate_ai_image")

    try:
        image_bytes = generate_image.remote(
            depth_bytes,
            prompt,
            model,
            strength,
            reference_bytes,
            ip_adapter_scale
        )

        if image_bytes:
            activity.logger.info(f"Generated image for {seat_id}: {len(image_bytes)} bytes")
            return base64.b64encode(image_bytes).decode('utf-8')

        activity.logger.warning(f"No image returned for {seat_id}")
        return None

    except Exception as e:
        activity.logger.error(f"Failed to generate image for {seat_id}: {e}")
        raise
