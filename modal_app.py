"""
Modal App for Venue Seat Views Pipeline

This runs Blender and AI image generation in the cloud, solving:
- No local Blender installation needed
- No SSL certificate issues
- Scalable rendering

Usage:
    # Deploy
    modal deploy modal_app.py

    # Or run locally for testing
    modal run modal_app.py
"""

import modal
import json
import math
import io
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Create the Modal app
app = modal.App("venue-seat-views")

# Web server image with FastAPI and api package
web_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "supabase>=2.0.0",
        "python-multipart>=0.0.6",
        "httpx>=0.25.0",
        "temporalio>=1.7.0",
        "modal",  # Required for Function.lookup() to call other Modal functions
    )
    .add_local_python_source("api", "temporal", copy=True)
)

# Blender image with Python packages
blender_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "wget",
        "xz-utils",
        "libx11-6",
        "libxi6",
        "libxxf86vm1",
        "libxfixes3",
        "libxrender1",
        "libgl1-mesa-glx",
        "libsm6",
        "libxkbcommon0",      # Required for Blender
        "libxkbcommon-x11-0", # X11 keyboard support
        "libegl1",            # OpenGL/EGL support
        "libglu1-mesa",       # OpenGL utilities
    )
    .run_commands(
        # Download and install Blender 4.2 LTS
        "wget -q https://download.blender.org/release/Blender4.2/blender-4.2.0-linux-x64.tar.xz",
        "tar -xf blender-4.2.0-linux-x64.tar.xz -C /opt",
        "ln -s /opt/blender-4.2.0-linux-x64/blender /usr/local/bin/blender",
        "rm blender-4.2.0-linux-x64.tar.xz",
    )
)

# Image for AI generation with Replicate
ai_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("replicate", "pillow", "requests", "httpx", "openai")
)


# ============== SEATMAP EXTRACTION (AI Vision) ==============

# Tier position defaults for 2D-to-3D mapping
TIER_DEFAULTS = {
    "floor": {"inner_radius": 8, "base_height": 0, "row_rise": 0.0},
    "lower": {"inner_radius": 18, "base_height": 2, "row_rise": 0.4},
    "mid": {"inner_radius": 30, "base_height": 8, "row_rise": 0.45},
    "upper": {"inner_radius": 42, "base_height": 16, "row_rise": 0.5},
    "club": {"inner_radius": 25, "base_height": 6, "row_rise": 0.35},
}

EXTRACTION_PROMPT = """You are analyzing a venue seatmap image. Your task is to extract ALL visible sections.

CRITICAL: Most venue seatmaps have 20-40+ sections. You MUST identify EVERY section visible in the image.
Look carefully for section numbers/labels around the entire venue - they are usually printed on each section.

For EACH section you find, extract:
- section_id: The label shown on the map (e.g., "101", "102", "A", "B", "Floor 1")
- tier: "floor" (on the playing surface), "lower" (closest bowl), "mid" (middle level), "upper" (top level), or "club" (premium areas)
- angle: Position around the venue in degrees (0 = top/12 o'clock, 90 = right/3 o'clock, 180 = bottom/6 o'clock, 270 = left/9 o'clock)
- estimated_rows: Number of rows in this section (typically 10-30)
- shape: "curved" for bowl seating, "straight" for theater-style

Walk around the entire seatmap clockwise starting from the top:
1. Start at 12 o'clock (angle 0) and note all sections there
2. Move to 3 o'clock (angle 90) and note all sections
3. Continue to 6 o'clock (angle 180)
4. Then 9 o'clock (angle 270)
5. Don't forget floor/field level sections in the center

Return ONLY valid JSON:
{
  "venue_type": "arena",
  "estimated_capacity": 18000,
  "sections": [
    {"section_id": "101", "tier": "lower", "angle": 0, "estimated_rows": 20, "shape": "curved", "position_description": "lower bowl, north side", "confidence": 0.9},
    {"section_id": "102", "tier": "lower", "angle": 15, "estimated_rows": 20, "shape": "curved", "position_description": "lower bowl, north side", "confidence": 0.9},
    {"section_id": "103", "tier": "lower", "angle": 30, "estimated_rows": 20, "shape": "curved", "position_description": "lower bowl, northeast", "confidence": 0.9}
  ]
}

Remember: Include ALL sections. A typical arena has 30+ sections. Do not stop after finding just a few."""


def map_2d_to_3d(extracted_section: dict) -> dict:
    """
    Convert 2D seatmap position to 3D venue coordinates.

    Uses tier to determine radius and height parameters.
    """
    tier = extracted_section.get("tier", "lower")
    defaults = TIER_DEFAULTS.get(tier, TIER_DEFAULTS["lower"])

    return {
        "section_id": extracted_section.get("section_id", "unknown"),
        "tier": tier,
        "angle": extracted_section.get("angle", 0.0),
        "inner_radius": defaults["inner_radius"],
        "estimated_rows": extracted_section.get("estimated_rows", 15),
        "rows": extracted_section.get("estimated_rows", 15),
        "row_depth": 0.85,
        "row_rise": defaults["row_rise"],
        "base_height": defaults["base_height"],
        "confidence": extracted_section.get("confidence", 0.5),
        "position_description": extracted_section.get("position_description"),
    }


@app.function(
    image=ai_image,
    secrets=[
        modal.Secret.from_name("openai-secret"),
    ],
    timeout=300  # 5 minutes for GPT-4 Vision
)
def extract_sections_from_seatmap(seatmap_url: str) -> dict:
    """
    Extract section definitions from a seatmap image using GPT-4 Vision.

    Args:
        seatmap_url: URL to the seatmap image

    Returns:
        {
            "venue_type": str,
            "raw_extraction": dict,
            "sections": [...processed sections with 3D coords...],
            "confidence_scores": {section_id: float}
        }
    """
    import os
    import requests
    import base64
    import json
    import re
    import openai

    print(f"Starting extraction with GPT-4 Vision")
    print(f"Seatmap URL: {seatmap_url}")

    # Download image
    response = requests.get(seatmap_url)
    response.raise_for_status()
    image_data = base64.b64encode(response.content).decode('utf-8')

    # Determine content type
    content_type = response.headers.get('content-type', 'image/png')
    if 'jpeg' in content_type or 'jpg' in content_type:
        mime_type = 'image/jpeg'
    else:
        mime_type = 'image/png'

    data_uri = f"data:{mime_type};base64,{image_data}"

    # Use GPT-4 Vision
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key not found in secrets. Add 'openai-secret' to Modal.")

    client = openai.OpenAI(api_key=api_key)

    print("Calling GPT-4 Vision API...")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are an expert at analyzing venue seatmaps and extracting structural information. Always respond with valid JSON only."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ]
            }
        ],
        max_tokens=4000
    )

    response_text = response.choices[0].message.content
    print(f"GPT-4 Vision response: {response_text[:500]}...")

    # Parse JSON from response (handle markdown code blocks)
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
    if json_match:
        response_text = json_match.group(1)

    result = json.loads(response_text)

    # Process sections: map 2D to 3D coordinates
    processed_sections = []
    confidence_scores = {}

    for section in result.get("sections", []):
        processed = map_2d_to_3d(section)
        processed_sections.append(processed)
        confidence_scores[processed["section_id"]] = processed.get("confidence", 0.5)

    print(f"Extracted {len(processed_sections)} sections")

    return {
        "venue_type": result.get("venue_type", "arena"),
        "raw_extraction": result,
        "sections": processed_sections,
        "confidence_scores": confidence_scores,
    }


# ============== SEAT GENERATION (Pure Python) ==============

@app.function(image=modal.Image.debian_slim(python_version="3.11"))
def generate_seats(sections: Dict[str, dict]) -> Tuple[List[dict], List[dict], List[dict]]:
    """
    Generate seat coordinates from section definitions.
    Returns: (all_seats, sample_seats, anchor_seats)
    """

    def angle_to_radians(degrees: float) -> float:
        return degrees * math.pi / 180

    def calculate_seat_position(
        section_angle: float,
        tier_radius: float,
        row_num: int,
        seat_num: int,
        seats_per_row: int,
        row_depth: float,
        row_rise: float,
        base_height: float,
        section_arc: float = 15.0
    ) -> Tuple[float, float, float, float]:
        current_radius = tier_radius + (row_num * row_depth)
        current_height = base_height + (row_num * row_rise)

        if seats_per_row > 1:
            seat_offset = (seat_num / (seats_per_row - 1) - 0.5) * section_arc
        else:
            seat_offset = 0

        total_angle = section_angle + seat_offset
        angle_rad = angle_to_radians(total_angle)

        x = current_radius * math.sin(angle_rad)
        y = current_radius * math.cos(angle_rad)
        z = current_height

        look_angle = math.degrees(math.atan2(-x, -y))

        return (round(x, 3), round(y, 3), round(z, 3), round(look_angle, 2))

    def generate_seats_for_section(section_data: dict) -> List[dict]:
        """Generate 3 representative seats per section: Front, Middle, Back."""
        seats = []
        section_id = section_data["section_id"]
        section_angle = section_data["angle"]
        tier = section_data["tier"]
        inner_radius = section_data["inner_radius"]
        rows = section_data["rows"]  # Actual row count for position calculation
        row_depth = section_data["row_depth"]
        row_rise = section_data["row_rise"]
        base_height = section_data["base_height"]

        # Generate 3 strategic positions: Front, Middle, Back
        positions = [
            ("Front", 0),           # First row
            ("Middle", rows // 2),  # Middle row
            ("Back", rows - 1)      # Last row
        ]

        for row_label, row_num in positions:
            x, y, z, look_angle = calculate_seat_position(
                section_angle, inner_radius, row_num, 0, 1, row_depth, row_rise, base_height
            )
            seats.append({
                "id": f"{section_id}_{row_label}_1",
                "section": section_id, "row": row_label, "seat": 1,
                "tier": tier, "x": x, "y": y, "z": z, "look_angle": look_angle
            })
        return seats

    # Generate all seats
    all_seats = []
    for section_id, section_data in sections.items():
        all_seats.extend(generate_seats_for_section(section_data))

    # Sample seats
    sample_seats = []
    sections_by_id = {}
    for seat in all_seats:
        sections_by_id.setdefault(seat["section"], []).append(seat)

    for section_id, section_seats in sections_by_id.items():
        rows = sorted(set(s["row"] for s in section_seats))
        sample_rows = [rows[0]]
        if len(rows) > 2:
            sample_rows.append(rows[len(rows) // 2])
        if len(rows) > 1:
            sample_rows.append(rows[-1])

        for row in sample_rows:
            row_seats = [s for s in section_seats if s["row"] == row]
            if row_seats:
                sample_seats.append(row_seats[len(row_seats) // 2])

    # Anchor seats (minimal set)
    anchor_seats = []
    tiers = {"lower": [], "mid": [], "upper": []}
    for seat in all_seats:
        tiers[seat["tier"]].append(seat)

    for tier, tier_seats in tiers.items():
        tier_sections = sorted(set(s["section"] for s in tier_seats))
        if len(tier_sections) >= 3:
            sample_sections = [tier_sections[0], tier_sections[len(tier_sections)//2], tier_sections[-1]]
        else:
            sample_sections = tier_sections

        for section in sample_sections:
            section_seats = [s for s in tier_seats if s["section"] == section]
            rows = sorted(set(s["row"] for s in section_seats))
            if rows:
                front_row = [s for s in section_seats if s["row"] == rows[0]]
                if front_row:
                    anchor_seats.append(front_row[len(front_row)//2])
                if len(rows) > 1:
                    back_row = [s for s in section_seats if s["row"] == rows[-1]]
                    if back_row:
                        anchor_seats.append(back_row[len(back_row)//2])

    return all_seats, sample_seats, anchor_seats


# ============== BLENDER VENUE BUILDING ==============

VENUE_BUILD_SCRIPT = '''
import bpy
import json
import math
import sys

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)

def create_material(name, color):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.8
    return mat

def create_surface(config):
    """Create playing surface based on surface_type from config."""
    surface_config = config.get("surface_config", {})
    surface_type = surface_config.get("surface_type", "rink")
    length = surface_config.get("length", 60)
    width = surface_config.get("width", 26)
    boards = surface_config.get("boards", surface_type == "rink")
    boards_height = surface_config.get("boards_height", 1.2)

    # Surface color based on type
    surface_colors = {
        "rink": [0.9, 0.95, 1.0],     # Ice - light blue/white
        "court": [0.76, 0.54, 0.33],  # Hardwood - tan/brown
        "stage": [0.1, 0.1, 0.1],     # Stage - dark/black
        "field": [0.2, 0.5, 0.2],     # Grass - green
    }
    color = surface_colors.get(surface_type, [0.5, 0.5, 0.5])

    # Create base surface
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    surface = bpy.context.active_object
    surface.name = "Surface"
    surface.scale = (length / 2, width / 2, 1)

    mat = create_material("surface_mat", color)
    surface.data.materials.append(mat)

    # Add surface-specific elements
    if surface_type == "rink" and boards:
        # Hockey boards
        board_mat = create_material("board_mat", [0.95, 0.95, 0.95])
        height = boards_height
        positions = [
            (0, width/2 + 0.1, height/2, length, 0.2, height),
            (0, -width/2 - 0.1, height/2, length, 0.2, height),
            (length/2 + 0.1, 0, height/2, 0.2, width, height),
            (-length/2 - 0.1, 0, height/2, 0.2, width, height),
        ]
        for i, (x, y, z, sx, sy, sz) in enumerate(positions):
            bpy.ops.mesh.primitive_cube_add(location=(x, y, z))
            board = bpy.context.active_object
            board.name = f"Board_{i}"
            board.scale = (sx/2, sy/2, sz/2)
            board.data.materials.append(board_mat)

    elif surface_type == "court":
        # Basketball court markings (simplified)
        line_mat = create_material("court_lines", [0.9, 0.9, 0.9])
        # Center circle
        bpy.ops.mesh.primitive_circle_add(vertices=32, radius=1.8, location=(0, 0, 0.01))
        center_circle = bpy.context.active_object
        center_circle.name = "CenterCircle"
        center_circle.data.materials.append(line_mat)
        # Free throw circles (simplified)
        for x_offset in [length/2 - 5.8, -length/2 + 5.8]:
            bpy.ops.mesh.primitive_circle_add(vertices=32, radius=1.8, location=(x_offset, 0, 0.01))
            ft_circle = bpy.context.active_object
            ft_circle.name = f"FreeThrowCircle_{x_offset:.0f}"
            ft_circle.data.materials.append(line_mat)

    elif surface_type == "stage":
        # Stage platform - raised
        stage_mat = create_material("stage_mat", [0.15, 0.15, 0.15])
        stage_width = width * 0.4
        stage_length = length * 0.3
        stage_height = 1.0
        bpy.ops.mesh.primitive_cube_add(location=(0, width/2 - stage_width/2, stage_height/2))
        stage = bpy.context.active_object
        stage.name = "Stage"
        stage.scale = (stage_length/2, stage_width/2, stage_height/2)
        stage.data.materials.append(stage_mat)

    elif surface_type == "field":
        # Field markings - simplified
        line_mat = create_material("field_lines", [0.95, 0.95, 0.95])
        # Center line
        bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0.01))
        center_line = bpy.context.active_object
        center_line.name = "CenterLine"
        center_line.scale = (0.1, width/2, 1)
        center_line.data.materials.append(line_mat)
        # End zones
        for x_offset in [length/2 - 5, -length/2 + 5]:
            bpy.ops.mesh.primitive_plane_add(size=1, location=(x_offset, 0, 0.01))
            endzone = bpy.context.active_object
            endzone.name = f"Endzone_{x_offset:.0f}"
            endzone.scale = (5, width/2, 1)
            endzone_mat = create_material(f"endzone_mat_{x_offset:.0f}", [0.4, 0.15, 0.15])
            endzone.data.materials.append(endzone_mat)

def create_tier_geometry(inner_radius, rows, row_depth, row_rise, base_height, sections=32):
    vertices = []
    faces = []
    num_segments = sections * 4

    for row in range(rows + 1):
        current_radius = inner_radius + (row * row_depth)
        current_height = base_height + (row * row_rise)
        for seg in range(num_segments):
            angle = (seg / num_segments) * 2 * math.pi
            x = current_radius * math.cos(angle)
            y = current_radius * math.sin(angle)
            vertices.append((x, y, current_height))

    for row in range(rows):
        for seg in range(num_segments):
            next_seg = (seg + 1) % num_segments
            v1 = row * num_segments + seg
            v2 = row * num_segments + next_seg
            v3 = (row + 1) * num_segments + next_seg
            v4 = (row + 1) * num_segments + seg
            faces.append((v1, v2, v3, v4))

    return vertices, faces

def create_seating_bowl(sections):
    mat_lower = create_material("seats_lower", [0.6, 0.1, 0.1])
    mat_upper = create_material("seats_upper", [0.2, 0.2, 0.5])

    tier_sections = {"lower": [], "mid": [], "upper": []}
    for section_id, data in sections.items():
        tier_sections[data["tier"]].append(data)

    for tier, tier_data in tier_sections.items():
        if not tier_data:
            continue
        params = tier_data[0]
        vertices, faces = create_tier_geometry(
            params["inner_radius"], params["rows"],
            params["row_depth"], params["row_rise"],
            params["base_height"], len(tier_data)
        )

        mesh = bpy.data.meshes.new(f"Seating_{tier}")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()

        obj = bpy.data.objects.new(f"Seating_{tier}", mesh)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(mat_lower if tier == "lower" else mat_upper)

def create_lighting():
    bpy.ops.object.light_add(type='AREA', location=(0, 0, 20))
    light = bpy.context.active_object
    light.name = "MainLight"
    light.data.energy = 40000
    light.data.size = 20

def render_preview():
    """Render a preview image of the venue from above."""
    # Create camera for overview shot
    bpy.ops.object.camera_add(location=(0, -50, 40))
    camera = bpy.context.active_object
    camera.name = "PreviewCamera"

    # Point camera at center
    camera.rotation_euler = (math.radians(50), 0, 0)

    # Set as active camera
    bpy.context.scene.camera = camera

    # Configure render settings for fast preview
    scene = bpy.context.scene
    # Blender 4.x uses BLENDER_EEVEE_NEXT, older versions use BLENDER_EEVEE
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x = 800
    scene.render.resolution_y = 600
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'

    # Render
    scene.render.filepath = "/tmp/venue_preview.png"
    bpy.ops.render.render(write_still=True)
    print("PREVIEW: Rendered to /tmp/venue_preview.png")

# Main execution
try:
    config = json.loads(sys.argv[-2])
    sections = json.loads(sys.argv[-1])

    print(f"CONFIG: {config}")
    print(f"SECTIONS: {list(sections.keys())}")

    print("Clearing scene...")
    clear_scene()

    print("Creating surface...")
    create_surface(config)

    print("Creating seating bowl...")
    create_seating_bowl(sections)

    print("Creating lighting...")
    create_lighting()

    print("Rendering preview...")
    render_preview()

    print("Saving blend file...")
    bpy.ops.wm.save_as_mainfile(filepath="/tmp/venue_model.blend")
    print("SUCCESS: Model saved to /tmp/venue_model.blend")

except Exception as e:
    import traceback
    print(f"ERROR in Blender script: {e}")
    print(traceback.format_exc())
    sys.exit(1)
'''


@app.function(image=blender_image, timeout=300)
def build_venue_model(config: dict, sections: dict) -> dict:
    """
    Build a 3D venue model in Blender.
    Returns dict with 'blend_file' (bytes) and 'preview_image' (bytes).
    """
    import subprocess
    import os

    print(f"Building venue model with config: {config}")
    print(f"Sections count: {len(sections)}")

    # Write the build script
    script_path = "/tmp/build_script.py"
    with open(script_path, "w") as f:
        f.write(VENUE_BUILD_SCRIPT)

    # Run Blender
    cmd = [
        "blender", "--background", "--python", script_path,
        "--", json.dumps(config), json.dumps(sections)
    ]

    print(f"Running Blender command: {' '.join(cmd[:5])}...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Always log output for debugging
    if result.stdout:
        print(f"Blender stdout:\n{result.stdout[-2000:]}")  # Last 2000 chars
    if result.stderr:
        print(f"Blender stderr:\n{result.stderr[-2000:]}")

    if result.returncode != 0:
        raise RuntimeError(f"Blender build failed (code {result.returncode}): {result.stderr}")

    # Check if the blend file was created
    blend_path = "/tmp/venue_model.blend"
    if not os.path.exists(blend_path):
        # Check what files were created
        tmp_files = os.listdir("/tmp")
        print(f"Files in /tmp: {[f for f in tmp_files if 'venue' in f.lower() or 'blend' in f.lower()]}")
        raise FileNotFoundError(
            f"Blender script completed but {blend_path} was not created. "
            f"Check Blender output above for errors. stdout: {result.stdout[-500:]}"
        )

    # Read the blend file
    with open(blend_path, "rb") as f:
        blend_bytes = f.read()
    print(f"Read blend file: {len(blend_bytes)} bytes")

    # Read the preview image if it exists
    preview_bytes = None
    if os.path.exists("/tmp/venue_preview.png"):
        with open("/tmp/venue_preview.png", "rb") as f:
            preview_bytes = f.read()
        print(f"Read preview image: {len(preview_bytes)} bytes")

    return {
        "blend_file": blend_bytes,
        "preview_image": preview_bytes,
    }


# ============== DEPTH MAP RENDERING ==============

RENDER_DEPTH_SCRIPT = '''
import bpy
import json
import sys
from mathutils import Vector

EYE_HEIGHT = 1.2
LOOK_AT = Vector((0, 0, 0))

def setup_render():
    scene = bpy.context.scene
    # Blender 4.x uses BLENDER_EEVEE_NEXT
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'

def create_depth_material():
    mat_name = "DepthViz"
    if mat_name in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials[mat_name])

    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    cam_data = nodes.new('ShaderNodeCameraData')
    cam_data.location = (-600, 0)

    divide = nodes.new('ShaderNodeMath')
    divide.operation = 'DIVIDE'
    divide.location = (-400, 0)
    divide.inputs[1].default_value = 100.0

    subtract = nodes.new('ShaderNodeMath')
    subtract.operation = 'SUBTRACT'
    subtract.location = (-200, 0)
    subtract.inputs[0].default_value = 1.0

    clamp = nodes.new('ShaderNodeClamp')
    clamp.location = (0, 0)

    emission = nodes.new('ShaderNodeEmission')
    emission.location = (200, 0)
    emission.inputs['Strength'].default_value = 1.0

    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (400, 0)

    links.new(cam_data.outputs['View Z Depth'], divide.inputs[0])
    links.new(divide.outputs[0], subtract.inputs[1])
    links.new(subtract.outputs[0], clamp.inputs[0])
    links.new(clamp.outputs[0], emission.inputs['Color'])
    links.new(emission.outputs[0], output.inputs['Surface'])
    return mat

def apply_depth_material():
    depth_mat = create_depth_material()
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            obj.data.materials.clear()
            obj.data.materials.append(depth_mat)

def setup_camera():
    camera = bpy.data.objects.get('SeatCamera')
    if camera is None:
        bpy.ops.object.camera_add()
        camera = bpy.context.active_object
        camera.name = 'SeatCamera'
    camera.data.lens = 18
    camera.data.clip_start = 0.1
    camera.data.clip_end = 200
    bpy.context.scene.camera = camera
    return camera

def render_seat(camera, seat, output_path):
    x, y, z = seat["x"], seat["y"], seat["z"]
    camera.location = Vector((x, y, z + EYE_HEIGHT))
    direction = LOOK_AT - camera.location
    camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    bpy.context.scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)

# Load blend file and seats
blend_path = sys.argv[-2]
seats_json = sys.argv[-1]

bpy.ops.wm.open_mainfile(filepath=blend_path)

seats = json.loads(seats_json)
setup_render()
apply_depth_material()
camera = setup_camera()

results = []
for i, seat in enumerate(seats):
    output_path = f"/tmp/depth_{seat['id']}.png"
    render_seat(camera, seat, output_path)
    results.append({"id": seat["id"], "path": output_path})
    print(f"RENDERED: {seat['id']}")

print(f"SUCCESS: Rendered {len(seats)} depth maps")
'''


@app.function(image=blender_image, timeout=600)
def render_depth_maps(blend_file_bytes: bytes, seats: List[dict]) -> Dict[str, bytes]:
    """
    Render depth maps for given seats.
    Returns dict mapping seat_id -> PNG bytes.
    """
    import subprocess

    # Save blend file
    blend_path = "/tmp/venue_model.blend"
    with open(blend_path, "wb") as f:
        f.write(blend_file_bytes)

    # Write render script
    script_path = "/tmp/render_script.py"
    with open(script_path, "w") as f:
        f.write(RENDER_DEPTH_SCRIPT)

    # Run Blender
    cmd = [
        "blender", "--background", "--python", script_path,
        "--", blend_path, json.dumps(seats)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if "SUCCESS" not in result.stdout:
        raise RuntimeError(f"Blender render failed: {result.stderr}\n{result.stdout}")

    # Collect rendered images
    depth_maps = {}
    for seat in seats:
        png_path = f"/tmp/depth_{seat['id']}.png"
        try:
            with open(png_path, "rb") as f:
                depth_maps[seat["id"]] = f.read()
        except FileNotFoundError:
            print(f"Warning: Depth map not found for {seat['id']}")

    return depth_maps


# ============== AI IMAGE GENERATION ==============

@app.function(
    image=ai_image,
    secrets=[
        modal.Secret.from_name("REPLICATE_API_TOKEN"),
        modal.Secret.from_name("openai-secret"),
    ],
    timeout=180
)
def generate_ai_image(
    depth_map_bytes: bytes,
    prompt: str,
    model: str = "flux",
    strength: float = 0.75,
    reference_image_bytes: Optional[bytes] = None,
    ip_adapter_scale: float = 0.6
) -> Optional[bytes]:
    """
    Generate an AI image from a depth map using Replicate.

    Args:
        depth_map_bytes: Depth map PNG bytes
        prompt: Text prompt for generation
        model: Model to use (flux, sdxl, controlnet, ip_adapter, style_transfer)
        strength: Generation strength (0-1)
        reference_image_bytes: Optional reference image for style transfer
        ip_adapter_scale: Style influence strength (0-1)

    Returns:
        JPEG bytes or None on failure.
    """
    import os
    import replicate
    import base64
    import requests
    from PIL import Image
    import io

    # Handle different secret key naming conventions
    token = os.environ.get("REPLICATE_API_TOKEN") or os.environ.get("replicate_api_token")
    if token:
        os.environ["REPLICATE_API_TOKEN"] = token

    # Convert depth map to base64 data URI
    b64 = base64.b64encode(depth_map_bytes).decode('utf-8')
    depth_uri = f"data:image/png;base64,{b64}"

    # Convert reference image if provided
    reference_uri = None
    if reference_image_bytes:
        ref_b64 = base64.b64encode(reference_image_bytes).decode('utf-8')
        reference_uri = f"data:image/jpeg;base64,{ref_b64}"

    # Strong negative prompt to suppress people and text
    negative_prompt = (
        "people, person, crowd, audience, spectators, fans, players, athletes, "
        "performers, humans, figures, faces, hands, bodies, "
        "text, words, letters, writing, font, typography, signs, signage, banners, "
        "posters, advertisements, logos, branding, labels, captions, subtitles, "
        "numbers, digits, scoreboard text, watermark, signature, graffiti, lettering, "
        "blurry, low quality, distorted, artifacts, cartoon, anime, drawing, "
        "illustration, 3d render, cgi, video game graphics"
    )

    try:
        if model == "ip_adapter" and reference_uri:
            # IP-Adapter SDXL: Style transfer with reference image
            output = replicate.run(
                "lucataco/ip_adapter_sdxl:7f47ede58e5b0c98cfdf8d4e7d7ce75c36a8a5f66d0a6e7c6b6d0e25db2c57fa",
                input={
                    "image": reference_uri,
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "ip_adapter_scale": ip_adapter_scale,
                    "num_inference_steps": 30,
                    "guidance_scale": 7.5,
                }
            )
        elif model == "flux-schnell":
            # Flux Schnell: Fast, good quality
            output = replicate.run(
                "black-forest-labs/flux-schnell",
                input={
                    "prompt": f"{prompt}, stadium interior, arena view, professional photography",
                    "go_fast": True,
                    "num_outputs": 1,
                    "aspect_ratio": "16:9",
                    "output_format": "jpg",
                    "output_quality": 90,
                }
            )
        elif model == "flux-dev":
            # Flux Dev: Higher quality, slower
            output = replicate.run(
                "black-forest-labs/flux-dev",
                input={
                    "prompt": f"{prompt}, stadium interior, arena view, professional photography",
                    "guidance": 3.5,
                    "num_outputs": 1,
                    "aspect_ratio": "16:9",
                    "output_format": "jpg",
                    "output_quality": 90,
                    "num_inference_steps": 28,
                }
            )
        elif model == "flux-2":
            # Flux 1.1 Pro: Latest high-quality Flux model
            output = replicate.run(
                "black-forest-labs/flux-1.1-pro",
                input={
                    "prompt": f"{prompt}, stadium interior, arena view, professional photography",
                    "aspect_ratio": "16:9",
                    "output_format": "jpg",
                    "output_quality": 90,
                    "safety_tolerance": 2,
                }
            )
        elif model == "sdxl":
            # SDXL with depth ControlNet
            output = replicate.run(
                "lucataco/sdxl-controlnet:ca6b7358e3d5a2a0a77ce77ca7a7269fbbe7d34c3ac93a8fe86b8b95d3e78f73",
                input={
                    "image": depth_uri,
                    "prompt": f"{prompt}, stadium interior, arena view, professional photography, high quality, detailed",
                    "negative_prompt": negative_prompt,
                    "condition_scale": strength,
                    "num_inference_steps": 30,
                    "guidance_scale": 7.5,
                }
            )
        elif model == "dall-e-3":
            # OpenAI DALL-E 3
            import openai
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key not found")

            client = openai.OpenAI(api_key=api_key)

            # DALL-E 3 doesn't support depth conditioning, so we use a detailed prompt
            dalle_prompt = f"{prompt}, stadium interior view from spectator seat, professional sports photography, photorealistic, high detail, wide angle lens, empty arena"

            response = client.images.generate(
                model="dall-e-3",
                prompt=dalle_prompt,
                size="1792x1024",  # Landscape format
                quality="hd",
                n=1,
            )

            # Download the generated image
            image_url = response.data[0].url
            img_response = requests.get(image_url)
            img_response.raise_for_status()
            return img_response.content

        else:  # flux (default) - uses depth conditioning
            output = replicate.run(
                "black-forest-labs/flux-depth-pro",
                input={
                    "prompt": prompt,
                    "control_image": depth_uri,
                    "guidance_scale": 3.5,
                    "num_inference_steps": 28,
                    "output_format": "jpg",
                    "output_quality": 90,
                }
            )

        # Handle different Replicate output formats
        image_data = None

        # New Replicate SDK returns FileOutput objects
        if hasattr(output, 'read'):
            # FileOutput object - read bytes directly
            image_data = output.read()
        elif hasattr(output, 'url'):
            # FileOutput with URL attribute
            response = requests.get(output.url)
            response.raise_for_status()
            image_data = response.content
        elif isinstance(output, list) and output:
            # List of URLs or FileOutputs
            first = output[0]
            if hasattr(first, 'read'):
                image_data = first.read()
            elif hasattr(first, 'url'):
                response = requests.get(first.url)
                response.raise_for_status()
                image_data = response.content
            elif isinstance(first, str):
                response = requests.get(first)
                response.raise_for_status()
                image_data = response.content
        elif isinstance(output, str):
            # Direct URL string
            response = requests.get(output)
            response.raise_for_status()
            image_data = response.content

        if not image_data:
            return None

        # Convert to JPEG
        img = Image.open(io.BytesIO(image_data))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        output_buffer = io.BytesIO()
        img.save(output_buffer, format='JPEG', quality=90)
        return output_buffer.getvalue()

    except Exception as e:
        print(f"AI generation error: {e}")
        raise RuntimeError(f"AI generation failed: {e}")


# ============== WEB API ENDPOINT ==============

@app.function(
    image=web_image,
    secrets=[modal.Secret.from_name("venue-seat-views-secrets")],
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def fastapi_app():
    """
    Serve the FastAPI backend on Modal.

    Deploy with: modal deploy modal_app.py
    Access at: https://venue-seat-views--fastapi-app.modal.run

    Uses the api.main FastAPI app which includes all routes:
    - /venues - Venue management
    - /venues/{id}/event-types - Event type management
    - /venues/{id}/seatmaps - Seatmap upload and extraction
    - /pipelines - Pipeline management (Temporal workflows)
    - /images - Image retrieval

    The Temporal worker is automatically started by GitHub Actions after deploy.
    """
    import os
    from api.main import app as api_app

    # Add worker control endpoints
    @api_app.post("/worker/start")
    async def start_worker():
        """Start the Temporal worker (spawns in background)."""
        try:
            temporal_worker.spawn()
            return {"status": "started", "message": "Temporal worker spawning in background..."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @api_app.get("/worker/status")
    async def worker_status():
        """Check Temporal configuration."""
        return {
            "temporal_namespace": os.environ.get("TEMPORAL_NAMESPACE", "not set"),
            "temporal_address": os.environ.get("TEMPORAL_ADDRESS", "not set"),
            "temporal_api_key_set": bool(os.environ.get("TEMPORAL_API_KEY")),
        }

    return api_app


# ============== TEMPORAL WORKER ==============

# Image for Temporal worker - includes the temporal package from local source
# Rebuild trigger: 2025-12-18-v2
temporal_worker_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "temporalio>=1.7.0",
        "replicate",
        "pillow",
        "requests",
        "httpx",
        "supabase>=2.0.0",
    )
    .add_local_python_source("temporal", copy=True)
)

@app.function(
    image=temporal_worker_image,
    secrets=[
        modal.Secret.from_name("venue-seat-views-secrets"),
        modal.Secret.from_name("REPLICATE_API_TOKEN"),
    ],
    timeout=86400,  # 24 hours
    # NOTE: Schedule removed - worker is started once on deploy via GitHub Actions.
    # Multiple schedules were causing duplicate workers.
)
async def temporal_worker():
    """
    Run the Temporal worker on Modal.

    This connects to Temporal Cloud and processes venue pipeline workflows.
    Uses the workflow defined in temporal/workflows/venue_pipeline.py.
    """
    import os
    import asyncio
    from temporalio.client import Client
    from temporalio.worker import Worker

    # Import the workflow and activities from our temporal package
    from temporal.workflows.venue_pipeline import VenuePipelineWorkflow
    from temporal.activities.modal_activities import (
        generate_seats_activity,
        build_venue_model_activity,
        render_depth_maps_activity,
        generate_ai_image_activity,
    )
    from temporal.activities.storage_activities import (
        save_seats_json_activity,
        save_blend_file_activity,
        save_depth_maps_activity,
        save_generated_images_activity,
        load_existing_images_activity,
        load_existing_blend_activity,
        load_existing_depth_maps_activity,
    )

    # Get Temporal credentials from secrets
    namespace = os.environ.get("TEMPORAL_NAMESPACE")
    address = os.environ.get("TEMPORAL_ADDRESS")
    api_key = os.environ.get("TEMPORAL_API_KEY")

    if not all([namespace, address, api_key]):
        raise ValueError("Missing Temporal credentials in secrets")

    print(f"Connecting to Temporal Cloud: {namespace}")

    client = await Client.connect(
        address,
        namespace=namespace,
        api_key=api_key,
        tls=True,
    )

    print(f"Connected to Temporal namespace: {client.namespace}")

    # Create and run worker with the proper workflow and activities
    worker = Worker(
        client,
        task_queue="venue-pipeline-queue",
        workflows=[VenuePipelineWorkflow],
        activities=[
            # Modal compute activities
            generate_seats_activity,
            build_venue_model_activity,
            render_depth_maps_activity,
            generate_ai_image_activity,
            # Storage activities
            save_seats_json_activity,
            save_blend_file_activity,
            save_depth_maps_activity,
            save_generated_images_activity,
            load_existing_images_activity,
            load_existing_blend_activity,
            load_existing_depth_maps_activity,
        ],
    )

    print("Starting Temporal worker on task queue: venue-pipeline-queue")
    print(f"Registered workflow: VenuePipelineWorkflow")
    print(f"Registered {11} activities")

    # Run for 23 hours (Modal will restart after 24h timeout)
    try:
        await asyncio.wait_for(worker.run(), timeout=82800)
    except asyncio.TimeoutError:
        print("Worker timeout - will be restarted by Modal")


# ============== CLI ENTRY POINT ==============

@app.local_entrypoint()
def main():
    """Test the pipeline locally."""
    print("Testing Modal venue pipeline...")

    # Test sections
    test_sections = {
        "101": {
            "section_id": "101",
            "angle": 0,
            "tier": "lower",
            "inner_radius": 18.0,
            "rows": 5,
            "seats_per_row": 10,
            "row_depth": 0.85,
            "row_rise": 0.40,
            "base_height": 2.0
        }
    }

    test_config = {
        "venue_id": "test_arena",
        "name": "Test Arena",
        "configurations": {"hockey": {"surface": "rink", "length": 60, "width": 26}},
        "materials": {
            "seats": {
                "lower": {"color": [0.6, 0.1, 0.1]},
                "upper": {"color": [0.2, 0.2, 0.5]}
            }
        }
    }

    # Test seat generation
    print("\n1. Testing seat generation...")
    all_seats, sample_seats, anchor_seats = generate_seats.remote(test_sections)
    print(f"   Generated {len(all_seats)} seats, {len(anchor_seats)} anchors")

    # Test venue building
    print("\n2. Testing venue model building...")
    blend_bytes = build_venue_model.remote(test_config, test_sections)
    print(f"   Built venue model: {len(blend_bytes)} bytes")

    # Test depth rendering
    print("\n3. Testing depth map rendering...")
    test_seats = anchor_seats[:2]  # Just test 2 seats
    depth_maps = render_depth_maps.remote(blend_bytes, test_seats)
    print(f"   Rendered {len(depth_maps)} depth maps")

    print("\nAll tests passed!")
