"""
Temporal worker for the venue pipeline.

Run this to start processing workflows:
    python -m temporal.worker

Or with local dev server:
    TEMPORAL_LOCAL=true python -m temporal.worker
"""

import asyncio
import logging
import sys
from pathlib import Path

from temporalio.worker import Worker

from .client import get_temporal_client, TASK_QUEUE
from .workflows.venue_pipeline import VenuePipelineWorkflow
from .activities.modal_activities import (
    generate_seats_activity,
    build_venue_model_activity,
    render_depth_maps_activity,
    generate_ai_image_activity,
)
from .activities.storage_activities import (
    save_seats_json_activity,
    save_blend_file_activity,
    save_depth_maps_activity,
    save_generated_images_activity,
    load_existing_images_activity,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def run_worker():
    """Run the Temporal worker for venue pipeline."""
    logger.info("Connecting to Temporal...")
    client = await get_temporal_client()
    logger.info(f"Connected to Temporal namespace: {client.namespace}")

    # Create worker
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[VenuePipelineWorkflow],
        activities=[
            # Modal activities (cloud compute)
            generate_seats_activity,
            build_venue_model_activity,
            render_depth_maps_activity,
            generate_ai_image_activity,
            # Storage activities (local file I/O)
            save_seats_json_activity,
            save_blend_file_activity,
            save_depth_maps_activity,
            save_generated_images_activity,
            load_existing_images_activity,
        ],
    )

    logger.info(f"Starting worker on task queue: {TASK_QUEUE}")
    logger.info("Press Ctrl+C to stop")

    try:
        await worker.run()
    except asyncio.CancelledError:
        logger.info("Worker shutdown requested")
    finally:
        logger.info("Worker stopped")


def main():
    """Entry point for the worker."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")


if __name__ == "__main__":
    main()
