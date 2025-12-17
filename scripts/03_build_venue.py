#!/usr/bin/env python3
"""
03_build_venue.py

Blender Python script to build a 3D venue model.
Run with: blender --background --python 03_build_venue.py -- <venue_id> [event_type]
"""

import json
import math
import sys
from pathlib import Path

# Blender imports (only available when run inside Blender)
try:
    import bpy
    import mathutils
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False
    print("Warning: Blender not available. This script must be run inside Blender.")


class VenueBuilder:
    """Build a 3D venue in Blender from configuration."""
    
    def __init__(self, config_path: Path, sections_path: Path):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        with open(sections_path, 'r') as f:
            self.sections = json.load(f)
        
        self.venue_id = self.config["venue_id"]
        self.name = self.config["name"]
    
    def clear_scene(self):
        """Remove all objects from the scene."""
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()
        
        # Clear orphan data
        for block in bpy.data.meshes:
            if block.users == 0:
                bpy.data.meshes.remove(block)
    
    def create_material(self, name: str, color: list) -> bpy.types.Material:
        """Create a simple diffuse material."""
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (*color, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.8
        
        return mat
    
    def create_surface(self, event_type: str = "hockey"):
        """Create the playing surface (rink, court, or stage)."""
        config = self.config["configurations"].get(event_type, {})
        surface_type = config.get("surface", "rink")
        
        length = config.get("length", 60)
        width = config.get("width", 26)
        color = config.get("surface_color", [0.9, 0.95, 1.0])
        
        # Create surface plane
        bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
        surface = bpy.context.active_object
        surface.name = f"Surface_{surface_type}"
        surface.scale = (length / 2, width / 2, 1)
        
        mat = self.create_material(f"{surface_type}_material", color)
        surface.data.materials.append(mat)
        
        # Add boards for hockey rink
        if surface_type == "rink":
            self._create_boards(length, width)
        
        return surface
    
    def _create_boards(self, length: float, width: float, height: float = 1.2):
        """Create hockey boards around the rink."""
        # Board material
        board_mat = self.create_material("board_material", [0.95, 0.95, 0.95])
        
        # Create boards as a hollow box
        positions = [
            (0, width/2 + 0.1, height/2, length, 0.2, height),   # Top
            (0, -width/2 - 0.1, height/2, length, 0.2, height),  # Bottom
            (length/2 + 0.1, 0, height/2, 0.2, width, height),   # Right
            (-length/2 - 0.1, 0, height/2, 0.2, width, height),  # Left
        ]
        
        for i, (x, y, z, sx, sy, sz) in enumerate(positions):
            bpy.ops.mesh.primitive_cube_add(location=(x, y, z))
            board = bpy.context.active_object
            board.name = f"Board_{i}"
            board.scale = (sx/2, sy/2, sz/2)
            board.data.materials.append(board_mat)
    
    def create_seating_bowl(self):
        """Create the seating bowl geometry."""
        seat_color_lower = self.config["materials"]["seats"]["lower"]["color"]
        seat_color_upper = self.config["materials"]["seats"]["upper"]["color"]
        
        mat_lower = self.create_material("seats_lower", seat_color_lower)
        mat_upper = self.create_material("seats_upper", seat_color_upper)
        
        # Group sections by tier for batch creation
        tier_sections = {"lower": [], "mid": [], "upper": []}
        for section_id, section_data in self.sections.items():
            tier = section_data["tier"]
            tier_sections[tier].append(section_data)
        
        # Create geometry for each tier
        for tier, sections in tier_sections.items():
            if not sections:
                continue
            
            # Use first section's params (they're the same within a tier)
            params = sections[0]
            
            vertices, faces = self._create_tier_geometry(
                inner_radius=params["inner_radius"],
                rows=params["rows"],
                row_depth=params["row_depth"],
                row_rise=params["row_rise"],
                base_height=params["base_height"],
                sections=len(sections)
            )
            
            mesh = bpy.data.meshes.new(f"Seating_{tier}")
            mesh.from_pydata(vertices, [], faces)
            mesh.update()
            
            obj = bpy.data.objects.new(f"Seating_{tier}", mesh)
            bpy.context.collection.objects.link(obj)
            
            mat = mat_lower if tier == "lower" else mat_upper
            obj.data.materials.append(mat)
    
    def _create_tier_geometry(
        self,
        inner_radius: float,
        rows: int,
        row_depth: float,
        row_rise: float,
        base_height: float,
        sections: int = 32
    ) -> tuple:
        """Create stepped seating bowl geometry."""
        vertices = []
        faces = []
        
        num_segments = sections * 4  # Smooth curve
        
        for row in range(rows + 1):
            current_radius = inner_radius + (row * row_depth)
            current_height = base_height + (row * row_rise)
            
            for seg in range(num_segments):
                angle = (seg / num_segments) * 2 * math.pi
                x = current_radius * math.cos(angle)
                y = current_radius * math.sin(angle)
                vertices.append((x, y, current_height))
        
        # Create faces
        for row in range(rows):
            for seg in range(num_segments):
                next_seg = (seg + 1) % num_segments
                
                v1 = row * num_segments + seg
                v2 = row * num_segments + next_seg
                v3 = (row + 1) * num_segments + next_seg
                v4 = (row + 1) * num_segments + seg
                
                faces.append((v1, v2, v3, v4))
        
        return vertices, faces
    
    def create_jumbotron(self):
        """Create center-hung jumbotron."""
        jumbotron_config = self.config.get("landmarks", {}).get("jumbotron")
        if not jumbotron_config:
            return None
        
        position = jumbotron_config["position"]
        size = jumbotron_config["size"]
        
        bpy.ops.mesh.primitive_cube_add(location=position)
        jumbotron = bpy.context.active_object
        jumbotron.name = "Jumbotron"
        jumbotron.scale = (size[0]/2, size[1]/2, size[2]/2)
        
        mat = self.create_material("jumbotron_mat", [0.1, 0.1, 0.1])
        jumbotron.data.materials.append(mat)
        
        return jumbotron
    
    def create_lighting(self):
        """Set up arena lighting."""
        lighting_config = self.config.get("lighting", {})
        
        # Main overhead light
        main = lighting_config.get("main", {})
        if main:
            bpy.ops.object.light_add(
                type='AREA',
                location=main.get("position", [0, 0, 20])
            )
            light = bpy.context.active_object
            light.name = "MainLight"
            light.data.energy = main.get("energy", 40000)
            light.data.size = main.get("size", 20)
            
            color = main.get("color", [1, 1, 1])
            light.data.color = color
        
        # Accent lights
        accent = lighting_config.get("accent", {})
        if accent:
            for i, pos in enumerate(accent.get("positions", [])):
                bpy.ops.object.light_add(type='SPOT', location=pos)
                light = bpy.context.active_object
                light.name = f"AccentLight_{i}"
                light.data.energy = accent.get("energy", 5000)
                light.data.spot_size = math.radians(60)
    
    def create_crowd_placeholder(self):
        """
        Create simple crowd representation.
        For depth maps, we just need shapes to establish geometry.
        """
        # For now, the seating bowl geometry is enough
        # In production, you might add crowd billboards or particle systems
        pass
    
    def build(self, event_type: str = "hockey"):
        """Build the complete venue."""
        print(f"Building {self.name} for {event_type}...")
        
        self.clear_scene()
        self.create_surface(event_type)
        self.create_seating_bowl()
        self.create_jumbotron()
        self.create_lighting()
        self.create_crowd_placeholder()
        
        print(f"Venue {self.name} built successfully")
        return self
    
    def save(self, output_path: Path):
        """Save the Blender file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
        print(f"Saved to {output_path}")


def main():
    import argparse

    if not BLENDER_AVAILABLE:
        print("This script must be run inside Blender:")
        print("  blender --background --python 03_build_venue.py -- --venue pnc_arena")
        sys.exit(1)

    # Parse command line arguments (after --)
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Build 3D venue model")
    parser.add_argument("--venue", default="pnc_arena", help="Venue ID")
    parser.add_argument("--event", default="hockey", help="Event type")
    args = parser.parse_args(argv)

    venue_id = args.venue
    event_type = args.event

    # Paths
    script_dir = Path(__file__).parent
    venue_dir = script_dir.parent / "venues" / venue_id
    config_path = venue_dir / "config.json"
    sections_path = venue_dir / "sections.json"
    output_path = venue_dir / "venue_model.blend"  # Standard name

    if not sections_path.exists():
        print(f"Error: sections.json not found at {sections_path}")
        sys.exit(1)

    print(f"Building 3D model for {venue_id}...")

    # Build venue
    builder = VenueBuilder(config_path, sections_path)
    builder.build(event_type)
    builder.save(output_path)

    print(f"Success! Saved model to {output_path}")


if __name__ == "__main__":
    main()
