"""
Pydantic schemas for API request/response models.
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


# ============== Enums ==============

class PipelineStage(str, Enum):
    """Pipeline execution stages."""
    PENDING = "pending"
    GENERATING_SEATS = "generating_seats"
    BUILDING_MODEL = "building_model"
    RENDERING_DEPTHS = "rendering_depths"
    GENERATING_IMAGES = "generating_images"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AIModel(str, Enum):
    """Available AI models for image generation."""
    FLUX = "flux"
    FLUX_SCHNELL = "flux-schnell"
    FLUX_DEV = "flux-dev"
    SDXL = "sdxl"
    CONTROLNET = "controlnet"
    IP_ADAPTER = "ip_adapter"


class SurfaceType(str, Enum):
    """Types of playing surfaces."""
    RINK = "rink"        # Ice hockey
    COURT = "court"      # Basketball
    STAGE = "stage"      # Concert
    FIELD = "field"      # Football/Soccer


class ExtractionStatus(str, Enum):
    """Seatmap extraction statuses."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractionProvider(str, Enum):
    """AI providers for seatmap extraction."""
    REPLICATE = "replicate"
    OPENAI = "openai"


# ============== Venue Schemas ==============

class SectionConfig(BaseModel):
    """Configuration for a venue section."""
    section_id: str
    tier: str = "lower"  # lower, mid, upper, club, floor, balcony
    angle: float = 0.0
    inner_radius: float = 18.0
    rows: int = 21
    row_depth: float = 0.8
    row_rise: float = 0.3
    base_height: float = 2.0


class VenueConfig(BaseModel):
    """Venue configuration."""
    venue_id: str
    name: str
    location: Optional[str] = None
    configurations: Dict = Field(default_factory=dict)
    materials: Dict = Field(default_factory=dict)


class VenueCreate(BaseModel):
    """Request to create a new venue."""
    name: str
    location: Optional[str] = None


class VenueResponse(BaseModel):
    """Venue response with full details."""
    venue_id: str
    slug: str  # URL-friendly slug for pretty URLs
    name: str
    location: Optional[str] = None
    sections_count: int = 0
    has_seatmap: bool = False
    has_model: bool = False
    images_count: int = 0
    event_types_count: int = 0  # Number of event types configured
    created_at: Optional[datetime] = None


class VenueListResponse(BaseModel):
    """List of venues."""
    venues: List[VenueResponse]
    total: int


# ============== Pipeline Schemas ==============

class PipelineRequest(BaseModel):
    """Request to start a pipeline."""
    venue_id: str
    sections: Dict[str, dict]
    event_type_id: Optional[str] = None  # For fetching reference image and surface config
    selected_section_ids: Optional[List[str]] = None
    custom_seats: Optional[List[str]] = None

    # Surface configuration
    surface_type: SurfaceType = SurfaceType.RINK

    # AI generation settings
    prompt: str = "Arena view, empty arena"
    model: AIModel = AIModel.FLUX
    strength: float = Field(0.75, ge=0.0, le=1.0)

    # Reference image (base64) - auto-fetched from event type if not provided
    reference_image_b64: Optional[str] = None
    ip_adapter_scale: float = Field(0.6, ge=0.0, le=1.0)

    # Processing options - control pipeline stopping points
    stop_after_model: bool = False      # Stop after building 3D model (for preview)
    stop_after_depths: bool = False     # Stop after rendering depth maps
    skip_ai_generation: bool = False    # Legacy - same as stop_after_depths


class PipelineProgress(BaseModel):
    """Pipeline progress response."""
    workflow_id: str
    stage: PipelineStage
    current_step: int
    total_steps: int = 4
    message: str = ""

    # Progress counts
    seats_generated: int = 0
    depth_maps_rendered: int = 0
    images_generated: int = 0

    # Cost tracking
    estimated_cost: float = 0.0
    actual_cost: float = 0.0

    # Failures
    failed_items: List[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    """Final pipeline result."""
    workflow_id: str
    venue_id: str
    success: bool

    # Counts
    all_seats_count: int = 0
    depth_maps_rendered: int = 0
    images_generated: int = 0

    # Paths
    image_paths: List[str] = Field(default_factory=list)
    failed_seats: List[str] = Field(default_factory=list)

    # Cost and timing
    total_cost: float = 0.0
    duration_seconds: float = 0.0
    error_message: Optional[str] = None


class PipelineStartResponse(BaseModel):
    """Response when starting a pipeline."""
    workflow_id: str
    status: str = "started"
    message: str = "Pipeline started successfully"


# ============== Image Schemas ==============

class SeatImage(BaseModel):
    """Information about a generated seat image."""
    seat_id: str
    section: str
    row: str
    seat: int
    tier: str
    depth_map_url: Optional[str] = None
    final_image_url: Optional[str] = None
    generated_at: Optional[datetime] = None


class ImageGalleryResponse(BaseModel):
    """Response for image gallery."""
    venue_id: str
    images: List[SeatImage]
    total: int


# ============== Event Type Schemas ==============

class SurfaceConfig(BaseModel):
    """Configuration for playing surface."""
    length: float = 60.0      # Surface length in meters
    width: float = 26.0       # Surface width in meters
    boards: bool = True       # Whether to include boards (hockey)
    boards_height: float = 1.2
    # Additional surface-specific settings
    extra: Dict = Field(default_factory=dict)


class EventTypeCreate(BaseModel):
    """Request to create an event type."""
    name: str                                    # 'hockey', 'basketball', 'concert'
    display_name: str                            # 'Hockey', 'Basketball', 'Concert'
    surface_type: SurfaceType = SurfaceType.RINK
    surface_config: Optional[SurfaceConfig] = None
    is_default: bool = False


class EventTypeUpdate(BaseModel):
    """Request to update an event type."""
    display_name: Optional[str] = None
    surface_type: Optional[SurfaceType] = None
    surface_config: Optional[SurfaceConfig] = None
    is_default: Optional[bool] = None


class EventTypeResponse(BaseModel):
    """Event type response."""
    id: str
    venue_id: str
    name: str
    display_name: str
    seatmap_url: Optional[str] = None
    reference_image_url: Optional[str] = None
    surface_type: SurfaceType
    surface_config: SurfaceConfig = Field(default_factory=SurfaceConfig)
    is_default: bool = False
    sections_count: int = 0
    created_at: Optional[datetime] = None


class EventTypeListResponse(BaseModel):
    """List of event types."""
    event_types: List[EventTypeResponse]
    total: int


# ============== Seatmap Extraction Schemas ==============

class ExtractedSection(BaseModel):
    """Section extracted from seatmap by AI."""
    section_id: str
    tier: str = "lower"
    angle: float = 0.0
    estimated_rows: int = 15
    inner_radius: float = 18.0
    row_depth: float = 0.85
    row_rise: float = 0.4
    base_height: float = 2.0
    confidence: float = 0.5
    position_description: Optional[str] = None


class SeatmapExtractionResponse(BaseModel):
    """Seatmap extraction response."""
    id: str
    venue_id: str
    event_type_id: Optional[str] = None
    seatmap_url: str
    provider: ExtractionProvider
    status: ExtractionStatus
    extracted_sections: Optional[List[ExtractedSection]] = None
    confidence_scores: Optional[Dict[str, float]] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None


class SeatmapAdjustmentRequest(BaseModel):
    """Request to adjust extracted sections."""
    sections: Dict[str, ExtractedSection]  # section_id -> adjusted section
