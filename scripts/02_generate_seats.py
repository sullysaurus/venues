#!/usr/bin/env python3
"""
02_generate_seats.py

Generate individual seat coordinates from section definitions.
Creates XYZ positions and camera angles for each seat.
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple


def angle_to_radians(degrees: float) -> float:
    """Convert degrees to radians."""
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
    section_arc: float = 15.0  # degrees per section
) -> Tuple[float, float, float, float]:
    """
    Calculate XYZ position and look angle for a seat.
    
    Returns: (x, y, z, look_angle_degrees)
    """
    # Calculate radius for this row
    current_radius = tier_radius + (row_num * row_depth)
    
    # Calculate height for this row
    current_height = base_height + (row_num * row_rise)
    
    # Calculate seat angle within section
    # Seats spread across the section arc
    if seats_per_row > 1:
        seat_offset = (seat_num / (seats_per_row - 1) - 0.5) * section_arc
    else:
        seat_offset = 0
    
    total_angle = section_angle + seat_offset
    angle_rad = angle_to_radians(total_angle)
    
    # Convert polar to cartesian
    # Arena is oriented with center at 0,0
    # X = side to side, Y = toward/away from center, Z = height
    x = current_radius * math.sin(angle_rad)
    y = current_radius * math.cos(angle_rad)
    z = current_height
    
    # Look angle points toward center (0, 0, 0)
    look_angle = math.degrees(math.atan2(-x, -y))
    
    return (
        round(x, 3),
        round(y, 3),
        round(z, 3),
        round(look_angle, 2)
    )


def generate_seats_for_section(section_data: dict) -> List[dict]:
    """Generate 3 representative seat positions per section: Front, Middle, Back."""
    seats = []

    section_id = section_data["section_id"]
    section_angle = section_data["angle"]
    tier = section_data["tier"]
    inner_radius = section_data["inner_radius"]
    rows = section_data["rows"]  # Actual row count (21, 12, 9) for position calculation
    row_depth = section_data["row_depth"]
    row_rise = section_data["row_rise"]
    base_height = section_data["base_height"]

    # Generate 3 strategic positions: Front, Middle, Back
    positions = [
        ("Front", 0),                # First row
        ("Middle", rows // 2),       # Middle row
        ("Back", rows - 1)           # Last row
    ]

    for row_label, row_num in positions:
        x, y, z, look_angle = calculate_seat_position(
            section_angle=section_angle,
            tier_radius=inner_radius,
            row_num=row_num,
            seat_num=0,        # Center seat (only one)
            seats_per_row=1,
            row_depth=row_depth,
            row_rise=row_rise,
            base_height=base_height
        )

        seats.append({
            "id": f"{section_id}_{row_label}_1",
            "section": section_id,
            "row": row_label,
            "seat": 1,
            "tier": tier,
            "x": x,
            "y": y,
            "z": z,
            "look_angle": look_angle
        })

    return seats


def get_sample_seats(all_seats: List[dict], samples_per_section: int = 5) -> List[dict]:
    """
    Get a representative sample of seats for testing/initial renders.
    
    Samples:
    - Front row center
    - Front row edges
    - Back row center
    - Middle row center
    """
    samples = []
    
    # Group by section
    sections = {}
    for seat in all_seats:
        section = seat["section"]
        if section not in sections:
            sections[section] = []
        sections[section].append(seat)
    
    for section_id, section_seats in sections.items():
        # Get unique rows
        rows = sorted(set(s["row"] for s in section_seats))
        
        if len(rows) == 0:
            continue
        
        # Sample rows: front, middle, back
        sample_rows = [rows[0]]
        if len(rows) > 2:
            sample_rows.append(rows[len(rows) // 2])
        if len(rows) > 1:
            sample_rows.append(rows[-1])
        
        for row in sample_rows:
            row_seats = [s for s in section_seats if s["row"] == row]
            if len(row_seats) == 0:
                continue
            
            # Get center seat
            center_idx = len(row_seats) // 2
            samples.append(row_seats[center_idx])
    
    return samples


def get_anchor_seats(all_seats: List[dict]) -> List[dict]:
    """
    Get minimal anchor seats for quick testing.
    Just 2-3 seats per section tier.
    """
    anchors = []
    
    tiers = {"lower": [], "mid": [], "upper": []}
    for seat in all_seats:
        tiers[seat["tier"]].append(seat)
    
    for tier, tier_seats in tiers.items():
        # Get sections in this tier
        sections = sorted(set(s["section"] for s in tier_seats))
        
        # Sample 3 sections: start, middle, end
        if len(sections) >= 3:
            sample_sections = [sections[0], sections[len(sections)//2], sections[-1]]
        else:
            sample_sections = sections
        
        for section in sample_sections:
            section_seats = [s for s in tier_seats if s["section"] == section]
            rows = sorted(set(s["row"] for s in section_seats))
            
            # Get front row center seat
            if rows:
                front_row_seats = [s for s in section_seats if s["row"] == rows[0]]
                if front_row_seats:
                    anchors.append(front_row_seats[len(front_row_seats)//2])
                
                # Get back row center seat
                if len(rows) > 1:
                    back_row_seats = [s for s in section_seats if s["row"] == rows[-1]]
                    if back_row_seats:
                        anchors.append(back_row_seats[len(back_row_seats)//2])
    
    return anchors


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate seat coordinates from sections")
    parser.add_argument("--venue", default="pnc_arena", help="Venue ID")
    args = parser.parse_args()

    # Paths
    venue_dir = Path(__file__).parent.parent / "venues" / args.venue
    sections_path = venue_dir / "sections.json"

    if not sections_path.exists():
        print(f"Error: sections.json not found at {sections_path}")
        print("Please define sections first using the UI or 01_extract_sections.py")
        return

    # Load sections
    print(f"Loading sections for {args.venue}...")
    with open(sections_path, 'r') as f:
        sections = json.load(f)

    if not sections:
        print("Error: No sections found in sections.json")
        return

    # Generate all seats
    print("Generating seat coordinates...")
    all_seats = []
    for section_id, section_data in sections.items():
        section_seats = generate_seats_for_section(section_data)
        all_seats.extend(section_seats)

    print(f"Generated {len(all_seats)} total seats")

    # Save all seats (as seats.json for compatibility)
    seats_path = venue_dir / "seats.json"
    with open(seats_path, 'w') as f:
        json.dump({"venue": args.venue, "seats": all_seats}, f, indent=2)
    print(f"Saved seats to {seats_path}")

    # Also save as all_seats.json for backwards compatibility
    all_seats_path = venue_dir / "all_seats.json"
    with open(all_seats_path, 'w') as f:
        json.dump(all_seats, f, indent=2)

    # Generate sample seats (for initial testing)
    sample_seats = get_sample_seats(all_seats)
    sample_path = venue_dir / "sample_seats.json"
    with open(sample_path, 'w') as f:
        json.dump(sample_seats, f, indent=2)
    print(f"Saved {len(sample_seats)} sample seats to {sample_path}")

    # Generate anchor seats (minimal set for quick testing)
    anchor_seats = get_anchor_seats(all_seats)
    anchor_path = venue_dir / "anchor_seats.json"
    with open(anchor_path, 'w') as f:
        json.dump(anchor_seats, f, indent=2)
    print(f"Saved {len(anchor_seats)} anchor seats to {anchor_path}")

    # Print summary
    print("\nSummary by tier:")
    tier_counts = {}
    for seat in all_seats:
        tier = seat["tier"]
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    for tier, count in sorted(tier_counts.items()):
        print(f"  {tier}: {count} seats")

    print(f"\nSuccess! Generated {len(all_seats)} seats for {args.venue}")


if __name__ == "__main__":
    main()
