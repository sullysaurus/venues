#!/usr/bin/env python3
"""
run_pipeline.py - Master script for venue seat view generation
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


class VenuePipeline:
    def __init__(self, venue_id: str, event_type: str = "hockey"):
        self.venue_id = venue_id
        self.event_type = event_type
        self.blender_path = None
        
        self.script_dir = Path(__file__).parent
        self.project_dir = self.script_dir.parent
        self.venue_dir = self.project_dir / "venues" / venue_id
        
        self.config_path = self.venue_dir / "config.json"
        self.sections_path = self.venue_dir / "sections.json"
        self.blend_path = self.venue_dir / f"{venue_id}_{event_type}.blend"
        self.all_seats_path = self.venue_dir / "all_seats.json"
        self.sample_seats_path = self.venue_dir / "sample_seats.json"
        self.anchor_seats_path = self.venue_dir / "anchor_seats.json"
        self.depth_maps_dir = self.venue_dir / "outputs" / "depth_maps"
        self.final_images_dir = self.venue_dir / "outputs" / "final_images"
    
    def run_command(self, cmd: list, description: str):
        print(f"\n{'='*60}")
        print(f"STEP: {description}")
        print(f"{'='*60}")
        print(f"Command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=False)
        
        if result.returncode != 0:
            print(f"Error: {description} failed with code {result.returncode}")
            sys.exit(1)
        
        print(f"✓ {description} complete")
    
    def find_blender(self) -> str:
        """Find Blender executable."""
        # Check PATH first
        blender_in_path = shutil.which("blender")
        if blender_in_path:
            return blender_in_path
        
        # Mac locations
        mac_paths = [
            "/Applications/Blender.app/Contents/MacOS/Blender",
            os.path.expanduser("~/Applications/Blender.app/Contents/MacOS/Blender"),
            "/opt/homebrew/bin/blender",
        ]
        
        # Linux locations
        linux_paths = [
            "/usr/bin/blender",
            "/snap/bin/blender",
        ]
        
        for path in mac_paths + linux_paths:
            if os.path.isfile(path):
                return path
        
        return None
    
    def check_prerequisites(self):
        print("\nChecking prerequisites...")
        
        if not self.config_path.exists():
            print(f"Error: Config not found at {self.config_path}")
            sys.exit(1)
        
        self.blender_path = self.find_blender()
        if not self.blender_path:
            print("Error: Blender not found.")
            print("\nTo fix on Mac:")
            print("  brew install --cask blender")
            print("  OR add to PATH:")
            print('  export PATH="/Applications/Blender.app/Contents/MacOS:$PATH"')
            sys.exit(1)
        
        print(f"✓ Found Blender: {self.blender_path}")
        
        self.depth_maps_dir.mkdir(parents=True, exist_ok=True)
        self.final_images_dir.mkdir(parents=True, exist_ok=True)
        
        print("✓ Prerequisites OK")
    
    def step_1_extract_sections(self):
        cmd = [sys.executable, str(self.script_dir / "01_extract_sections.py")]
        self.run_command(cmd, "Extract sections")
    
    def step_2_generate_seats(self):
        cmd = [sys.executable, str(self.script_dir / "02_generate_seats.py")]
        self.run_command(cmd, "Generate seat coordinates")
    
    def step_3_build_venue(self):
        cmd = [
            self.blender_path, "--background",
            "--python", str(self.script_dir / "03_build_venue.py"),
            "--", self.venue_id, self.event_type
        ]
        self.run_command(cmd, f"Build 3D venue ({self.event_type})")
    
    def step_4_render_depths(self, seats_file: str = "anchor_seats.json"):
        seats_path = self.venue_dir / seats_file
        
        cmd = [
            self.blender_path, str(self.blend_path), "--background",
            "--python", str(self.script_dir / "04_render_depths.py"),
            "--", str(seats_path), str(self.depth_maps_dir)
        ]
        self.run_command(cmd, f"Render depth maps ({seats_file})")
    
    def step_5_generate_images(self, model: str = "flux"):
        cmd = [
            sys.executable,
            str(self.script_dir / "05_generate_images.py"),
            "--venue", self.venue_id,
            "--event", self.event_type,
            "--model", model
        ]
        self.run_command(cmd, "Generate final images")
    
    def run_full_pipeline(self, samples_only: bool = True, skip_ai: bool = False, model: str = "flux"):
        print(f"\n{'#'*60}")
        print(f"# VENUE SEAT VIEW PIPELINE")
        print(f"# Venue: {self.venue_id}")
        print(f"# Event: {self.event_type}")
        print(f"{'#'*60}")
        
        self.check_prerequisites()
        
        if not self.sections_path.exists():
            self.step_1_extract_sections()
        else:
            print(f"\n✓ Sections exist: {self.sections_path}")
        
        if not self.anchor_seats_path.exists():
            self.step_2_generate_seats()
        else:
            print(f"\n✓ Seats exist: {self.anchor_seats_path}")
        
        if not self.blend_path.exists():
            self.step_3_build_venue()
        else:
            print(f"\n✓ Venue model exists: {self.blend_path}")
        
        seats_file = "anchor_seats.json" if samples_only else "sample_seats.json"
        self.step_4_render_depths(seats_file)
        
        if not skip_ai:
            if not os.environ.get("REPLICATE_API_TOKEN"):
                print(f"\n⚠ REPLICATE_API_TOKEN not set")
                print("  export REPLICATE_API_TOKEN=r8_...")
                print("  Skipping AI generation.")
            else:
                self.step_5_generate_images(model)
        else:
            print("\n✓ Skipping AI generation (--skip-ai)")
        
        print(f"\n{'#'*60}")
        print(f"# COMPLETE")
        print(f"{'#'*60}")
        print(f"\nDepth maps: {self.depth_maps_dir}")
        print(f"Final images: {self.final_images_dir}")
        
        depth_count = len(list(self.depth_maps_dir.glob("*.png")))
        final_count = len(list(self.final_images_dir.glob("*.jpg")))
        print(f"\n  {depth_count} depth maps")
        print(f"  {final_count} final images")


def main():
    parser = argparse.ArgumentParser(description="Venue seat view pipeline")
    parser.add_argument("venue", help="Venue ID (e.g., pnc_arena)")
    parser.add_argument("event", nargs="?", default="hockey", help="Event type")
    parser.add_argument("--full-samples", action="store_true", help="Render more seats")
    parser.add_argument("--skip-ai", action="store_true", help="Skip AI generation")
    parser.add_argument("--model", default="flux", choices=["flux", "sdxl", "controlnet"])
    parser.add_argument("--step", choices=["sections", "seats", "build", "render", "generate"])
    
    args = parser.parse_args()
    
    pipeline = VenuePipeline(args.venue, args.event)
    
    if args.step:
        pipeline.check_prerequisites()
        if args.step == "sections":
            pipeline.step_1_extract_sections()
        elif args.step == "seats":
            pipeline.step_2_generate_seats()
        elif args.step == "build":
            pipeline.step_3_build_venue()
        elif args.step == "render":
            seats_file = "sample_seats.json" if args.full_samples else "anchor_seats.json"
            pipeline.step_4_render_depths(seats_file)
        elif args.step == "generate":
            pipeline.step_5_generate_images(args.model)
    else:
        pipeline.run_full_pipeline(
            samples_only=not args.full_samples,
            skip_ai=args.skip_ai,
            model=args.model
        )


if __name__ == "__main__":
    main()
