#!/usr/bin/env python3
"""
04_render_depths.py
Render depth maps from seat positions in Blender 5.0+
"""

import json
import sys
from pathlib import Path

try:
    import bpy
    import mathutils
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False

EYE_HEIGHT = 1.2
LOOK_AT = mathutils.Vector((0, 0, 0)) if BLENDER_AVAILABLE else None

def setup_render_settings():
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False

def create_depth_material():
    mat_name = "DepthVisualization"
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
    print(f"Applied depth material to all meshes")

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

def render_seat(camera, seat, output_dir):
    x, y, z = seat["x"], seat["y"], seat["z"]
    camera.location = mathutils.Vector((x, y, z + EYE_HEIGHT))
    direction = LOOK_AT - camera.location
    camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    
    output_path = output_dir / f"{seat['id']}_depth.png"
    bpy.context.scene.render.filepath = str(output_path)
    bpy.ops.render.render(write_still=True)

def main():
    import argparse

    if not BLENDER_AVAILABLE:
        print("Run inside Blender:")
        print("  blender venue_model.blend --background --python 04_render_depths.py -- --venue pnc_arena")
        sys.exit(1)

    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Render depth maps from seat positions")
    parser.add_argument("--venue", default="pnc_arena", help="Venue ID")
    parser.add_argument("--seats", default="anchor_seats.json", help="Seats file (anchor_seats.json, sample_seats.json, or all_seats.json)")
    args = parser.parse_args(argv)

    # Paths relative to venue directory
    script_dir = Path(__file__).parent
    venue_dir = script_dir.parent / "venues" / args.venue

    seats_file = venue_dir / args.seats
    output_dir = venue_dir / "outputs" / "depth_maps"

    # Fallback: check if running from blend file directory
    if not seats_file.exists():
        blend_dir = Path(bpy.data.filepath).parent if bpy.data.filepath else venue_dir
        seats_file = blend_dir / args.seats

    if not seats_file.exists():
        print(f"Error: Seats file not found: {seats_file}")
        print("Run 02_generate_seats.py first to generate seat positions.")
        sys.exit(1)

    print(f"Rendering depth maps for {args.venue}...")
    print(f"Seats file: {seats_file}")
    print(f"Output: {output_dir}")

    with open(seats_file, 'r') as f:
        data = json.load(f)
        # Handle both formats: list of seats or {"seats": [...]}
        if isinstance(data, dict) and "seats" in data:
            seats = data["seats"]
        else:
            seats = data

    output_dir.mkdir(parents=True, exist_ok=True)
    setup_render_settings()
    apply_depth_material()
    camera = setup_camera()

    print(f"Rendering {len(seats)} seats...")

    for i, seat in enumerate(seats):
        render_seat(camera, seat, output_dir)
        print(f"[{i+1}/{len(seats)}] {seat['id']}")

    print(f"\nSuccess! {len(seats)} depth maps saved to {output_dir}")

if __name__ == "__main__":
    main()
