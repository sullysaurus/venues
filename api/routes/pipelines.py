"""
Pipeline management endpoints - Temporal workflow integration.
"""

import uuid
import base64
import logging
import httpx
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException

from api.db import get_supabase
from api.schemas import (
    PipelineRequest,
    PipelineProgress,
    PipelineResult,
    PipelineStartResponse,
    PipelineStage,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Temporal client (lazy loaded)
_temporal_client = None


async def get_temporal_client():
    """Get or create Temporal client."""
    global _temporal_client
    if _temporal_client is None:
        from temporal.client import get_temporal_client as get_client
        _temporal_client = await get_client()
    return _temporal_client


async def fetch_reference_image(url: str) -> Optional[str]:
    """Fetch an image from URL and return as base64."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()
            image_bytes = response.content
            return base64.b64encode(image_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to fetch reference image from {url}: {e}")
        return None


@router.get("/health/check")
async def health_check():
    """
    Health check endpoint - verifies Temporal connection and worker status.
    """
    from temporal.client import TASK_QUEUE
    import os

    result = {
        "temporal_connected": False,
        "task_queue": TASK_QUEUE,
        "recent_workflows": [],
        "config": {
            "namespace": os.environ.get("TEMPORAL_NAMESPACE", "not set"),
            "address": os.environ.get("TEMPORAL_ADDRESS", "not set")[:30] + "..." if os.environ.get("TEMPORAL_ADDRESS") else "not set",
        }
    }

    try:
        client = await get_temporal_client()
        result["temporal_connected"] = True

        # List recent workflows to see activity
        workflows = []
        async for workflow in client.list_workflows(
            query="ORDER BY StartTime DESC",
            page_size=5
        ):
            workflows.append({
                "id": workflow.id,
                "status": workflow.status.name,
                "start_time": workflow.start_time.isoformat() if workflow.start_time else None,
            })
        result["recent_workflows"] = workflows

        # Check if any workflows are stuck (running for too long without progress)
        running_count = sum(1 for w in workflows if w["status"] == "RUNNING")
        result["running_workflows"] = running_count

        if running_count > 0 and len(workflows) > 0:
            result["worker_status"] = "LIKELY_RUNNING" if any(w["status"] == "COMPLETED" for w in workflows) else "POSSIBLY_NOT_CONNECTED"
        elif len(workflows) == 0:
            result["worker_status"] = "NO_WORKFLOWS_YET"
        else:
            result["worker_status"] = "OK"

    except Exception as e:
        result["error"] = str(e)
        result["worker_status"] = "TEMPORAL_CONNECTION_FAILED"

    return result


@router.post("/", response_model=PipelineStartResponse)
async def start_pipeline(request: PipelineRequest):
    """
    Start a new venue pipeline workflow.

    Returns a workflow_id that can be used to track progress.
    """
    from temporal.client import TASK_QUEUE
    from temporal.workflows.venue_pipeline import VenuePipelineWorkflow
    from temporal.workflows.types import VenuePipelineInput

    try:
        client = await get_temporal_client()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Temporal not available: {str(e)}. Make sure TEMPORAL_* environment variables are set."
        )

    workflow_id = f"venue-pipeline-{request.venue_id}-{uuid.uuid4().hex[:8]}"

    # Parse model string (might be "ip_adapter:0.6" format)
    model = request.model.value
    ip_adapter_scale = request.ip_adapter_scale
    if isinstance(model, str) and ":" in model:
        parts = model.split(":")
        model = parts[0]
        if len(parts) > 1:
            try:
                ip_adapter_scale = float(parts[1])
            except ValueError:
                pass

    # Fetch reference image from event type if using IP-Adapter and not provided
    reference_image_b64 = request.reference_image_b64

    # Build surface config from request surface_type
    surface_config = {
        "surface_type": request.surface_type.value,
    }

    if request.event_type_id and (model == "ip_adapter" or not reference_image_b64):
        try:
            supabase = get_supabase()
            event_type = supabase.table("event_types").select(
                "reference_image_url, surface_type, surface_config"
            ).eq("id", request.event_type_id).single().execute()

            if event_type.data:
                # Fetch reference image if using IP-Adapter
                ref_url = event_type.data.get("reference_image_url")
                if model == "ip_adapter" and ref_url and not reference_image_b64:
                    logger.info(f"Fetching reference image from {ref_url}")
                    reference_image_b64 = await fetch_reference_image(ref_url)
                    if not reference_image_b64:
                        logger.warning("Failed to fetch reference image, IP-Adapter may not work correctly")

                # Get surface config from event type (overrides request if present)
                event_surface_config = event_type.data.get("surface_config", {})
                if event_surface_config:
                    surface_config.update(event_surface_config)
        except HTTPException:
            # Database not configured, skip event type lookup
            logger.warning("Database not available, skipping event type lookup")
        except Exception as e:
            logger.error(f"Failed to fetch event type: {e}")

    # Build workflow input
    input_data = VenuePipelineInput(
        venue_id=request.venue_id,
        config={"surface_config": surface_config},  # Include surface config
        sections=request.sections,
        selected_section_ids=request.selected_section_ids,
        custom_seats=request.custom_seats,
        prompt=request.prompt,
        model=model,
        strength=request.strength,
        reference_image_b64=reference_image_b64,
        ip_adapter_scale=ip_adapter_scale,
        stop_after_model=request.stop_after_model,
        stop_after_depths=request.stop_after_depths,
        skip_ai_generation=request.skip_ai_generation,
    )

    try:
        await client.start_workflow(
            VenuePipelineWorkflow.run,
            input_data,
            id=workflow_id,
            task_queue=TASK_QUEUE,
            execution_timeout=timedelta(hours=2),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")

    return PipelineStartResponse(
        workflow_id=workflow_id,
        status="started",
        message=f"Pipeline started for venue {request.venue_id}",
    )


@router.get("/{workflow_id}", response_model=PipelineProgress)
async def get_pipeline_progress(workflow_id: str):
    """
    Get the current progress of a pipeline workflow.
    """
    from temporal.workflows.venue_pipeline import VenuePipelineWorkflow

    try:
        client = await get_temporal_client()
    except Exception as e:
        logger.error(f"Failed to connect to Temporal: {e}")
        raise HTTPException(status_code=503, detail=f"Temporal not available: {str(e)}")

    handle = client.get_workflow_handle(workflow_id)

    try:
        # Query workflow for progress
        progress = await handle.query(VenuePipelineWorkflow.get_progress)

        return PipelineProgress(
            workflow_id=workflow_id,
            stage=PipelineStage(progress.stage.value),
            current_step=progress.current_step,
            total_steps=progress.total_steps,
            message=progress.message,
            seats_generated=progress.seats_generated,
            depth_maps_rendered=progress.depth_maps_rendered,
            images_generated=progress.images_generated,
            estimated_cost=progress.estimated_cost,
            actual_cost=progress.actual_cost,
            failed_items=progress.failed_items,
        )
    except Exception as query_error:
        # Workflow might have completed or failed - can't query completed workflows
        logger.info(f"Query failed for {workflow_id}, checking workflow status: {query_error}")
        try:
            desc = await handle.describe()
            status = desc.status.name
            logger.info(f"Workflow {workflow_id} status: {status}")

            if status == "COMPLETED":
                return PipelineProgress(
                    workflow_id=workflow_id,
                    stage=PipelineStage.COMPLETED,
                    current_step=4,
                    total_steps=4,
                    message="Pipeline completed",
                )
            elif status == "FAILED":
                return PipelineProgress(
                    workflow_id=workflow_id,
                    stage=PipelineStage.FAILED,
                    current_step=0,
                    total_steps=4,
                    message="Pipeline failed",
                )
            elif status == "CANCELLED":
                return PipelineProgress(
                    workflow_id=workflow_id,
                    stage=PipelineStage.CANCELLED,
                    current_step=0,
                    total_steps=4,
                    message="Pipeline cancelled",
                )
            elif status == "RUNNING":
                # Workflow is running but query failed - might be initializing
                return PipelineProgress(
                    workflow_id=workflow_id,
                    stage=PipelineStage.PENDING,
                    current_step=0,
                    total_steps=4,
                    message="Pipeline starting...",
                )
            else:
                logger.warning(f"Unknown workflow status: {status}")
                raise HTTPException(status_code=500, detail=f"Unknown workflow status: {status}")
        except HTTPException:
            raise
        except Exception as desc_error:
            logger.error(f"Failed to describe workflow {workflow_id}: {desc_error}")
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")


@router.get("/{workflow_id}/result", response_model=PipelineResult)
async def get_pipeline_result(workflow_id: str):
    """
    Get the final result of a completed pipeline.
    """
    try:
        client = await get_temporal_client()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Temporal not available: {str(e)}")

    handle = client.get_workflow_handle(workflow_id)

    try:
        # Get workflow result (will raise if not complete)
        result = await handle.result()

        return PipelineResult(
            workflow_id=workflow_id,
            venue_id=result.venue_id,
            success=result.success,
            all_seats_count=result.all_seats_count,
            depth_maps_rendered=result.depth_maps_rendered,
            images_generated=result.images_generated,
            image_paths=result.image_paths,
            failed_seats=result.failed_seats,
            total_cost=result.total_cost,
            duration_seconds=result.duration_seconds,
            error_message=result.error_message,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Workflow not complete or failed: {str(e)}")


@router.post("/{workflow_id}/cancel")
async def cancel_pipeline(workflow_id: str):
    """
    Cancel a running pipeline workflow.
    """
    from temporal.workflows.venue_pipeline import VenuePipelineWorkflow

    try:
        client = await get_temporal_client()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Temporal not available: {str(e)}")

    handle = client.get_workflow_handle(workflow_id)

    try:
        # Send cancel signal
        await handle.signal(VenuePipelineWorkflow.cancel_pipeline)
        return {"status": "cancel_requested", "workflow_id": workflow_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel: {str(e)}")


@router.get("/{workflow_id}/status")
async def get_workflow_status(workflow_id: str):
    """
    Get the raw Temporal workflow status.
    """
    try:
        client = await get_temporal_client()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Temporal not available: {str(e)}")

    handle = client.get_workflow_handle(workflow_id)

    try:
        desc = await handle.describe()
        return {
            "workflow_id": workflow_id,
            "status": desc.status.name,
            "start_time": desc.start_time.isoformat() if desc.start_time else None,
            "execution_time": desc.execution_time.isoformat() if desc.execution_time else None,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
