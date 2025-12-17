"""
FastAPI Backend for Venue Seat Views

Run with: uvicorn api.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import logging

from api.config import settings
from api.routes import venues, pipelines, images, event_types, seatmaps

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    # Startup
    logger.info("Starting Venue Seat Views API...")
    logger.info(f"Supabase: {'enabled' if settings.use_supabase else 'disabled (file-based fallback)'}")
    logger.info(f"Temporal: {'enabled' if settings.use_temporal else 'disabled'}")
    yield
    # Shutdown
    logger.info("Shutting down...")


app = FastAPI(
    title="Venue Seat Views API",
    description="Generate AI-powered seat view images for any venue",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,  # Prevent 307 redirects that break CORS
)

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://gamtime-images.vercel.app",
        *settings.cors_origins,
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",  # Allow all Vercel preview deployments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(venues.router, prefix="/venues", tags=["venues"])
app.include_router(pipelines.router, prefix="/pipelines", tags=["pipelines"])
app.include_router(images.router, prefix="/images", tags=["images"])
app.include_router(event_types.router, prefix="/venues", tags=["event-types"])
app.include_router(seatmaps.router, prefix="/venues", tags=["seatmaps"])

# Serve venue static files (seatmaps, generated images)
venues_path = Path(__file__).parent.parent / "venues"
if venues_path.exists():
    app.mount("/static/venues", StaticFiles(directory=str(venues_path)), name="venues")


@app.get("/")
async def root():
    """API root."""
    return {
        "status": "ok",
        "service": "venue-seat-views",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint for load balancers and monitoring."""
    health_status = {
        "status": "healthy",
        "services": {
            "api": True,
            "supabase": settings.use_supabase,
            "temporal": settings.use_temporal,
        },
    }

    # Check Supabase connection if enabled
    if settings.use_supabase:
        try:
            from api.db import get_supabase_client
            client = get_supabase_client()
            # Simple query to verify connection
            client.table("venues").select("id").limit(1).execute()
            health_status["services"]["supabase_connected"] = True
        except Exception as e:
            health_status["services"]["supabase_connected"] = False
            health_status["services"]["supabase_error"] = str(e)
            health_status["status"] = "degraded"

    return health_status


@app.get("/config")
async def get_config():
    """Get public configuration (non-sensitive)."""
    import os
    return {
        "supabase_enabled": settings.use_supabase,
        "temporal_enabled": settings.use_temporal,
        "debug": settings.debug,
    }


@app.get("/debug/temporal")
async def debug_temporal():
    """Debug Temporal configuration (shows what env vars are available)."""
    import os
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "")
    address = os.environ.get("TEMPORAL_ADDRESS", "")
    api_key = os.environ.get("TEMPORAL_API_KEY", "")

    return {
        "temporal_namespace": namespace if namespace else "NOT SET",
        "temporal_address": address if address else "NOT SET",
        "temporal_api_key_length": len(api_key) if api_key else 0,
        "temporal_api_key_set": bool(api_key),
    }
