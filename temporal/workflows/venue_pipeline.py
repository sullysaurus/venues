"""
Main venue pipeline workflow.

Orchestrates the complete pipeline:
1. Generate seats from sections
2. Build 3D venue model in Blender
3. Render depth maps (batched)
4. Generate AI images (parallel with concurrency control)
"""

from datetime import timedelta
from typing import Dict, List, Optional
from temporalio import workflow
from temporalio.common import RetryPolicy

from .types import (
    VenuePipelineInput,
    PipelineResult,
    PipelineProgress,
    PipelineStage,
    COST_ESTIMATES,
)

# Import activities with proper handling for workflow sandbox
with workflow.unsafe.imports_passed_through():
    from ..activities.modal_activities import (
        generate_seats_activity,
        build_venue_model_activity,
        render_depth_maps_activity,
        generate_ai_image_activity,
    )
    from ..activities.storage_activities import (
        save_seats_json_activity,
        save_blend_file_activity,
        save_depth_maps_activity,
        save_generated_images_activity,
        load_existing_images_activity,
        load_existing_blend_activity,
        load_existing_depth_maps_activity,
    )


# Retry policies for different activity types
FAST_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_attempts=3,
    maximum_interval=timedelta(seconds=30),
)

BLENDER_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_attempts=3,
    maximum_interval=timedelta(minutes=2),
    non_retryable_error_types=["ValueError"],  # Config errors shouldn't retry
)

AI_GENERATION_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_attempts=5,
    maximum_interval=timedelta(minutes=5),
    # Retry on rate limits (429) and transient errors
)


@workflow.defn
class VenuePipelineWorkflow:
    """
    Main workflow for venue seat view generation pipeline.

    Provides:
    - Durable execution across failures
    - Progress tracking via queries
    - Graceful cancellation via signals
    - Automatic retries with exponential backoff
    - Parallel AI image generation
    """

    def __init__(self):
        self._progress = PipelineProgress()
        self._should_cancel = False

    @workflow.signal
    def cancel_pipeline(self):
        """Signal to cancel the pipeline gracefully."""
        self._should_cancel = True
        workflow.logger.info("Cancel signal received")

    @workflow.query
    def get_progress(self) -> PipelineProgress:
        """Query current pipeline progress."""
        return self._progress

    @workflow.run
    async def run(self, input: VenuePipelineInput) -> PipelineResult:
        """Execute the full pipeline."""
        start_time = workflow.now()
        cost_breakdown: Dict[str, float] = {}
        venue_dir = input.venue_dir or f"venues/{input.venue_id}"

        # Track intermediate results
        all_seats: List[dict] = []
        anchor_seats: List[dict] = []
        all_depth_maps: Dict[str, str] = {}
        depth_paths: Dict[str, str] = {}
        image_paths: Dict[str, str] = {}

        try:
            # ===== STAGE 1: GENERATE SEATS =====
            self._update_progress(
                PipelineStage.GENERATING_SEATS,
                step=1,
                message="Generating seat coordinates..."
            )

            # Filter sections if specific ones selected
            sections = input.sections
            if input.selected_section_ids:
                sections = {
                    k: v for k, v in input.sections.items()
                    if k in input.selected_section_ids
                }

            all_seats, sample_seats, anchor_seats = await workflow.execute_activity(
                generate_seats_activity,
                sections,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=FAST_RETRY,
            )

            cost_breakdown["seats"] = COST_ESTIMATES["seats"]
            self._progress.actual_cost += COST_ESTIMATES["seats"]
            self._progress.seats_generated = len(all_seats)

            # Save seats to storage
            await workflow.execute_activity(
                save_seats_json_activity,
                args=[venue_dir, input.venue_id, all_seats, anchor_seats],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=FAST_RETRY,
            )

            if self._should_cancel:
                return self._make_cancelled_result(input, start_time, cost_breakdown)

            # ===== STAGE 2: BUILD 3D MODEL =====
            blend_file_b64 = None

            if input.skip_model_build:
                # Try to load existing blend file from storage
                self._update_progress(
                    PipelineStage.BUILDING_MODEL,
                    step=2,
                    message="Loading existing 3D model..."
                )

                blend_file_b64 = await workflow.execute_activity(
                    load_existing_blend_activity,
                    args=[input.venue_id],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=FAST_RETRY,
                )

                if blend_file_b64:
                    workflow.logger.info("Using existing blend file from storage")
                else:
                    workflow.logger.warning("No existing blend file found, building new one")

            if not blend_file_b64:
                # Build new model
                self._update_progress(
                    PipelineStage.BUILDING_MODEL,
                    step=2,
                    message="Building 3D venue model with Blender..."
                )

                model_result = await workflow.execute_activity(
                    build_venue_model_activity,
                    args=[input.config, sections],
                    start_to_close_timeout=timedelta(minutes=15),
                    retry_policy=BLENDER_RETRY,
                    # No heartbeat_timeout - Modal calls are blocking and can't heartbeat during execution
                )

                # Extract blend file for depth rendering
                blend_file_b64 = model_result["blend_file"]

                cost_breakdown["model_build"] = COST_ESTIMATES["blender_build"]
                self._progress.actual_cost += COST_ESTIMATES["blender_build"]

                # Save blend file and preview
                await workflow.execute_activity(
                    save_blend_file_activity,
                    args=[venue_dir, model_result],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=FAST_RETRY,
                )

            if self._should_cancel:
                return self._make_cancelled_result(input, start_time, cost_breakdown)

            # Check if we should stop after building the model
            if input.stop_after_model:
                self._update_progress(
                    PipelineStage.COMPLETED,
                    step=2,
                    message="3D model built successfully! Ready for depth map rendering."
                )
                return self._make_result(
                    input, start_time, cost_breakdown,
                    all_seats, anchor_seats, {}, {},
                )

            # ===== STAGE 3: RENDER DEPTH MAPS =====
            if input.skip_depth_render:
                # Try to load existing depth maps from storage
                self._update_progress(
                    PipelineStage.RENDERING_DEPTHS,
                    step=3,
                    message="Loading existing depth maps..."
                )

                all_depth_maps = await workflow.execute_activity(
                    load_existing_depth_maps_activity,
                    args=[input.venue_id],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=FAST_RETRY,
                )

                if all_depth_maps:
                    workflow.logger.info(f"Loaded {len(all_depth_maps)} existing depth maps")
                    self._progress.depth_maps_rendered = len(all_depth_maps)
                    # Set depth_paths for the result (already in Supabase)
                    for seat_id in all_depth_maps:
                        depth_paths[seat_id] = f"supabase://{input.venue_id}/depth_maps/{seat_id}_depth.png"
                else:
                    workflow.logger.warning("No existing depth maps found, rendering new ones")

            if not all_depth_maps:
                # Render new depth maps
                self._update_progress(
                    PipelineStage.RENDERING_DEPTHS,
                    step=3,
                    message="Rendering depth maps..."
                )

                # Determine which seats to render
                seats_to_render = anchor_seats
                if input.custom_seats:
                    # Use custom seats instead
                    seats_to_render = [
                        s for s in all_seats if s.get("id") in input.custom_seats
                    ]

                # Batch depth map rendering
                depth_batch_size = input.depth_batch_size

                for batch_idx in range(0, len(seats_to_render), depth_batch_size):
                    if self._should_cancel:
                        break

                    batch = seats_to_render[batch_idx:batch_idx + depth_batch_size]
                    batch_num = batch_idx // depth_batch_size + 1
                    total_batches = (len(seats_to_render) + depth_batch_size - 1) // depth_batch_size

                    self._update_progress(
                        message=f"Rendering depth maps: batch {batch_num}/{total_batches}"
                    )

                    batch_depths = await workflow.execute_activity(
                        render_depth_maps_activity,
                        args=[blend_file_b64, batch, batch_idx],
                        start_to_close_timeout=timedelta(minutes=20),
                        retry_policy=BLENDER_RETRY,
                        # No heartbeat_timeout - Modal calls are blocking
                    )

                    all_depth_maps.update(batch_depths)
                    cost = len(batch) * COST_ESTIMATES["depth_render_per_seat"]
                    cost_breakdown["depth_rendering"] = cost_breakdown.get("depth_rendering", 0) + cost
                    self._progress.actual_cost += cost
                    self._progress.depth_maps_rendered = len(all_depth_maps)

                # Save depth maps
                depth_paths = await workflow.execute_activity(
                    save_depth_maps_activity,
                    args=[venue_dir, all_depth_maps],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=FAST_RETRY,
                )

            # Check if we should stop after depth maps
            if self._should_cancel or input.stop_after_depths or input.skip_ai_generation:
                self._update_progress(
                    PipelineStage.COMPLETED,
                    step=3,
                    message="Depth maps rendered! Ready for AI image generation."
                )
                return self._make_result(
                    input, start_time, cost_breakdown,
                    all_seats, anchor_seats, depth_paths, {},
                )

            # ===== STAGE 4: GENERATE AI IMAGES (PARALLEL) =====
            self._update_progress(
                PipelineStage.GENERATING_IMAGES,
                step=4,
                message="Generating AI images..."
            )

            # Check for existing images to skip
            existing_images = await workflow.execute_activity(
                load_existing_images_activity,
                venue_dir,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=FAST_RETRY,
            )

            # Generate images in parallel batches
            image_paths = await self._generate_images_parallel(
                input, all_depth_maps, existing_images, cost_breakdown
            )

            # ===== COMPLETE =====
            self._update_progress(
                PipelineStage.COMPLETED,
                step=4,
                message="Pipeline complete!"
            )

            return self._make_result(
                input, start_time, cost_breakdown,
                all_seats, anchor_seats, depth_paths, image_paths,
            )

        except Exception as e:
            workflow.logger.error(f"Pipeline failed: {e}")
            self._update_progress(
                PipelineStage.FAILED,
                message=f"Pipeline failed: {str(e)}"
            )
            return PipelineResult(
                venue_id=input.venue_id,
                success=False,
                all_seats_count=self._progress.seats_generated,
                anchor_seats_count=len(anchor_seats),
                depth_maps_rendered=self._progress.depth_maps_rendered,
                depth_map_paths=list(depth_paths.values()),
                images_generated=self._progress.images_generated,
                image_paths=list(image_paths.values()),
                failed_seats=self._progress.failed_items,
                total_cost=self._progress.actual_cost,
                cost_breakdown=cost_breakdown,
                duration_seconds=(workflow.now() - start_time).total_seconds(),
                error_message=str(e),
            )

    async def _generate_images_parallel(
        self,
        input: VenuePipelineInput,
        depth_maps: Dict[str, str],
        existing_images: Dict[str, str],
        cost_breakdown: Dict[str, float],
    ) -> Dict[str, str]:
        """Generate AI images in parallel with concurrency control."""

        # Get cost per image based on model
        model_costs = {
            "flux": COST_ESTIMATES["flux_per_image"],
            "sdxl": COST_ESTIMATES["sdxl_per_image"],
            "controlnet": COST_ESTIMATES["controlnet_per_image"],
            "ip_adapter": COST_ESTIMATES["ip_adapter_per_image"],
        }
        cost_per_image = model_costs.get(input.model, 0.02)

        # Start with existing images
        generated = dict(existing_images)

        # Filter to seats that need generation
        seat_ids = [sid for sid in depth_maps.keys() if sid not in existing_images]

        if not seat_ids:
            workflow.logger.info("All images already exist, skipping generation")
            return generated

        workflow.logger.info(f"Generating {len(seat_ids)} images ({len(existing_images)} already exist)")

        batch_size = input.parallel_image_batch_size

        for batch_start in range(0, len(seat_ids), batch_size):
            if self._should_cancel:
                break

            batch_ids = seat_ids[batch_start:batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            total_batches = (len(seat_ids) + batch_size - 1) // batch_size

            self._update_progress(
                message=f"Generating images: batch {batch_num}/{total_batches} ({batch_start + 1}-{min(batch_start + batch_size, len(seat_ids))} of {len(seat_ids)})"
            )

            # Launch parallel activities for this batch
            tasks = []
            for seat_id in batch_ids:
                task = workflow.execute_activity(
                    generate_ai_image_activity,
                    args=[
                        depth_maps[seat_id],
                        seat_id,
                        input.prompt,
                        input.model,
                        input.strength,
                        input.reference_image_b64,
                        input.ip_adapter_scale,
                    ],
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=AI_GENERATION_RETRY,
                    # No heartbeat_timeout - Modal calls are blocking
                )
                tasks.append((seat_id, task))

            # Await all tasks in batch and save results
            batch_images = {}
            for seat_id, task in tasks:
                try:
                    result = await task
                    if result:
                        batch_images[seat_id] = result
                        self._progress.images_generated += 1
                        cost_breakdown["image_generation"] = cost_breakdown.get("image_generation", 0) + cost_per_image
                        self._progress.actual_cost += cost_per_image
                    else:
                        self._progress.failed_items.append(seat_id)
                        workflow.logger.warning(f"No image returned for {seat_id}")
                except Exception as e:
                    workflow.logger.warning(f"Failed to generate image for {seat_id}: {e}")
                    self._progress.failed_items.append(seat_id)

            # Save batch to storage
            if batch_images:
                batch_paths = await workflow.execute_activity(
                    save_generated_images_activity,
                    args=[input.venue_dir or f"venues/{input.venue_id}", batch_images],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=FAST_RETRY,
                )
                generated.update(batch_paths)

        return generated

    def _update_progress(
        self,
        stage: Optional[PipelineStage] = None,
        step: Optional[int] = None,
        message: Optional[str] = None,
        current_item: Optional[str] = None,
    ):
        """Update progress state."""
        if stage is not None:
            self._progress.stage = stage
        if step is not None:
            self._progress.current_step = step
        if message is not None:
            self._progress.message = message
        if current_item is not None:
            self._progress.current_item = current_item

    def _make_result(
        self,
        input: VenuePipelineInput,
        start_time,
        cost_breakdown: Dict[str, float],
        all_seats: List[dict],
        anchor_seats: List[dict],
        depth_paths: Dict[str, str],
        image_paths: Dict[str, str],
    ) -> PipelineResult:
        """Create successful result."""
        return PipelineResult(
            venue_id=input.venue_id,
            success=True,
            all_seats_count=len(all_seats),
            anchor_seats_count=len(anchor_seats),
            depth_maps_rendered=len(depth_paths),
            depth_map_paths=list(depth_paths.values()),
            images_generated=len(image_paths),
            image_paths=list(image_paths.values()),
            failed_seats=self._progress.failed_items,
            total_cost=self._progress.actual_cost,
            cost_breakdown=cost_breakdown,
            duration_seconds=(workflow.now() - start_time).total_seconds(),
        )

    def _make_cancelled_result(
        self,
        input: VenuePipelineInput,
        start_time,
        cost_breakdown: Dict[str, float],
    ) -> PipelineResult:
        """Create cancelled result."""
        return PipelineResult(
            venue_id=input.venue_id,
            success=False,
            all_seats_count=self._progress.seats_generated,
            anchor_seats_count=0,
            depth_maps_rendered=self._progress.depth_maps_rendered,
            depth_map_paths=[],
            images_generated=self._progress.images_generated,
            image_paths=[],
            failed_seats=[],
            total_cost=self._progress.actual_cost,
            cost_breakdown=cost_breakdown,
            duration_seconds=(workflow.now() - start_time).total_seconds(),
            error_message="Cancelled by user",
        )
