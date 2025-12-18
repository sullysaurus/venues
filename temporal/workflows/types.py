"""
Data types for the venue pipeline workflow.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class PipelineStage(Enum):
    """Stages of the venue pipeline."""
    PENDING = "pending"
    GENERATING_SEATS = "generating_seats"
    BUILDING_MODEL = "building_model"
    RENDERING_DEPTHS = "rendering_depths"
    GENERATING_IMAGES = "generating_images"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class VenuePipelineInput:
    """Input parameters for the venue pipeline workflow."""
    venue_id: str
    config: Dict
    sections: Dict[str, dict]
    event_type: str = "default"
    selected_section_ids: Optional[List[str]] = None
    custom_seats: Optional[List[str]] = None

    # AI generation settings
    prompt: str = "Arena view, empty arena"
    model: str = "flux"  # flux, sdxl, controlnet, ip_adapter
    strength: float = 0.75

    # Reference image for style transfer (base64 encoded)
    reference_image_b64: Optional[str] = None
    ip_adapter_scale: float = 0.6

    # Processing options
    parallel_image_batch_size: int = 5
    depth_batch_size: int = 10
    stop_after_model: bool = False      # Stop after building 3D model
    stop_after_depths: bool = False     # Stop after rendering depth maps
    skip_ai_generation: bool = False    # Legacy alias for stop_after_depths

    # Resume options - skip steps if assets already exist
    skip_model_build: bool = False      # Use existing .blend file from storage
    skip_depth_render: bool = False     # Use existing depth maps from storage

    # Storage path
    venue_dir: Optional[str] = None

    def __post_init__(self):
        if self.venue_dir is None:
            self.venue_dir = f"venues/{self.venue_id}"


@dataclass
class PipelineProgress:
    """Progress state for UI updates."""
    stage: PipelineStage = PipelineStage.PENDING
    current_step: int = 0
    total_steps: int = 4
    current_item: str = ""
    message: str = ""

    # Cost tracking
    estimated_cost: float = 0.0
    actual_cost: float = 0.0

    # Results so far
    seats_generated: int = 0
    depth_maps_rendered: int = 0
    images_generated: int = 0
    failed_items: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Final result of the pipeline workflow."""
    venue_id: str
    success: bool

    # Seat generation results
    all_seats_count: int = 0
    anchor_seats_count: int = 0

    # Depth map results
    depth_maps_rendered: int = 0
    depth_map_paths: List[str] = field(default_factory=list)

    # AI image results
    images_generated: int = 0
    image_paths: List[str] = field(default_factory=list)
    failed_seats: List[str] = field(default_factory=list)

    # Cost tracking
    total_cost: float = 0.0
    cost_breakdown: Dict[str, float] = field(default_factory=dict)

    # Timing
    duration_seconds: float = 0.0
    error_message: Optional[str] = None


# Cost estimates per operation (USD)
COST_ESTIMATES = {
    "seats": 0.001,
    "blender_build": 0.05,
    "depth_render_per_seat": 0.02,
    "flux_per_image": 0.035,
    "sdxl_per_image": 0.015,
    "controlnet_per_image": 0.008,
    "ip_adapter_per_image": 0.02,
}
