#!/usr/bin/env python3
"""
01_extract_sections.py

Extract section positions from a venue seating map image.
This creates a mapping between section numbers and their pixel/angular positions.

For PNC Arena, we're manually defining positions based on the seating chart.
In production, you could use CV to detect sections automatically.
"""

import json
import math
from pathlib import Path


def create_pnc_arena_sections():
    """
    Manually define PNC Arena section positions based on the seating map.
    
    The arena is roughly elliptical. We define each section by:
    - angle_center: degrees from center ice (0 = facing main camera side)
    - tier: lower (100s), mid (200s), upper (300s)
    - radius_offset: how far from the default tier radius
    """
    
    sections = {}
    
    # Lower bowl - 100 level (24 sections: 101-124)
    # Based on Lenovo Center seating map
    # 0° = center ice (camera side), sections wrap counter-clockwise
    lower_sections = {
        # Behind goal (bottom of map)
        "101": {"angle": 172, "tier": "lower"},
        "102": {"angle": 157, "tier": "lower"},
        "103": {"angle": 142, "tier": "lower"},
        "104": {"angle": 127, "tier": "lower"},
        # Side (left of map, behind goal end)
        "105": {"angle": 112, "tier": "lower"},
        "106": {"angle": 97, "tier": "lower"},
        "107": {"angle": 82, "tier": "lower"},
        "108": {"angle": 67, "tier": "lower"},
        "109": {"angle": 52, "tier": "lower"},
        # Center ice (top of map, camera side)
        "110": {"angle": 37, "tier": "lower"},
        "111": {"angle": 22, "tier": "lower"},
        "112": {"angle": 7, "tier": "lower"},
        "113": {"angle": -8, "tier": "lower"},
        "114": {"angle": -23, "tier": "lower"},
        # Side (right of map)
        "115": {"angle": -38, "tier": "lower"},
        "116": {"angle": -53, "tier": "lower"},
        "117": {"angle": -68, "tier": "lower"},
        "118": {"angle": -83, "tier": "lower"},
        "119": {"angle": -98, "tier": "lower"},
        "120": {"angle": -113, "tier": "lower"},
        # Behind other goal
        "121": {"angle": -128, "tier": "lower"},
        "122": {"angle": -143, "tier": "lower"},
        "123": {"angle": -158, "tier": "lower"},
        "124": {"angle": -173, "tier": "lower"},
    }
    
    # Upper bowl - 200 level (club level, 28 sections: 201-228)
    # Based on Lenovo Center seating map
    upper_200_sections = {
        # Behind goal (bottom of map)
        "201": {"angle": 174, "tier": "mid"},
        "202": {"angle": 161, "tier": "mid"},
        "203": {"angle": 148, "tier": "mid"},
        "204": {"angle": 135, "tier": "mid"},
        "205": {"angle": 122, "tier": "mid"},
        # Side (left of map)
        "206": {"angle": 109, "tier": "mid"},
        "207": {"angle": 96, "tier": "mid"},
        "208": {"angle": 83, "tier": "mid"},
        "209": {"angle": 70, "tier": "mid"},
        "210": {"angle": 57, "tier": "mid"},
        "211": {"angle": 44, "tier": "mid"},
        # Center ice (top of map, camera side)
        "212": {"angle": 31, "tier": "mid"},
        "213": {"angle": 18, "tier": "mid"},
        "214": {"angle": 5, "tier": "mid"},
        "215": {"angle": -8, "tier": "mid"},
        "216": {"angle": -21, "tier": "mid"},
        "217": {"angle": -34, "tier": "mid"},
        # Side (right of map)
        "218": {"angle": -47, "tier": "mid"},
        "219": {"angle": -60, "tier": "mid"},
        "220": {"angle": -73, "tier": "mid"},
        "221": {"angle": -86, "tier": "mid"},
        "222": {"angle": -99, "tier": "mid"},
        "223": {"angle": -112, "tier": "mid"},
        # Behind other goal
        "224": {"angle": -125, "tier": "mid"},
        "225": {"angle": -138, "tier": "mid"},
        "226": {"angle": -151, "tier": "mid"},
        "227": {"angle": -164, "tier": "mid"},
        "228": {"angle": -177, "tier": "mid"},
    }
    
    # Upper deck - 300 level (28 sections: 301-328)
    # Based on Lenovo Center seating map
    upper_300_sections = {
        # Behind goal (bottom of map)
        "301": {"angle": 174, "tier": "upper"},
        "302": {"angle": 161, "tier": "upper"},
        "303": {"angle": 148, "tier": "upper"},
        "304": {"angle": 135, "tier": "upper"},
        "305": {"angle": 122, "tier": "upper"},
        # Side (left of map)
        "306": {"angle": 109, "tier": "upper"},
        "307": {"angle": 96, "tier": "upper"},
        "308": {"angle": 83, "tier": "upper"},
        "309": {"angle": 70, "tier": "upper"},
        "310": {"angle": 57, "tier": "upper"},
        "311": {"angle": 44, "tier": "upper"},
        # Center ice (top of map, camera side)
        "312": {"angle": 31, "tier": "upper"},
        "313": {"angle": 18, "tier": "upper"},
        "314": {"angle": 5, "tier": "upper"},
        "315": {"angle": -8, "tier": "upper"},
        "316": {"angle": -21, "tier": "upper"},
        "317": {"angle": -34, "tier": "upper"},
        # Side (right of map)
        "318": {"angle": -47, "tier": "upper"},
        "319": {"angle": -60, "tier": "upper"},
        "320": {"angle": -73, "tier": "upper"},
        "321": {"angle": -86, "tier": "upper"},
        "322": {"angle": -99, "tier": "upper"},
        "323": {"angle": -112, "tier": "upper"},
        # Behind other goal
        "324": {"angle": -125, "tier": "upper"},
        "325": {"angle": -138, "tier": "upper"},
        "326": {"angle": -151, "tier": "upper"},
        "327": {"angle": -164, "tier": "upper"},
        "328": {"angle": -177, "tier": "upper"},
    }
    
    # Combine all sections
    sections.update(lower_sections)
    sections.update(upper_200_sections)
    sections.update(upper_300_sections)
    
    # Add tier-specific parameters
    tier_params = {
        "lower": {
            "inner_radius": 18,
            "rows": 21,
            "seats_per_row": 22,
            "row_depth": 0.85,
            "row_rise": 0.40,
            "base_height": 2.0
        },
        "mid": {
            "inner_radius": 32,
            "rows": 12,
            "seats_per_row": 24,
            "row_depth": 0.82,
            "row_rise": 0.50,
            "base_height": 14.0
        },
        "upper": {
            "inner_radius": 40,
            "rows": 14,
            "seats_per_row": 26,
            "row_depth": 0.78,
            "row_rise": 0.58,
            "base_height": 24.0
        }
    }
    
    # Enrich each section with tier parameters
    for section_id, section_data in sections.items():
        tier = section_data["tier"]
        section_data.update(tier_params[tier])
        section_data["section_id"] = section_id
    
    return sections


def save_sections(sections: dict, output_path: Path):
    """Save sections to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(sections, f, indent=2)
    print(f"Saved {len(sections)} sections to {output_path}")


def main():
    # Define paths
    venue_dir = Path(__file__).parent.parent / "venues" / "pnc_arena"
    output_path = venue_dir / "sections.json"
    
    # Extract sections
    print("Extracting PNC Arena sections...")
    sections = create_pnc_arena_sections()
    
    # Save
    save_sections(sections, output_path)
    
    # Print summary
    tiers = {}
    for section_id, data in sections.items():
        tier = data["tier"]
        tiers[tier] = tiers.get(tier, 0) + 1
    
    print(f"\nSection summary:")
    for tier, count in sorted(tiers.items()):
        print(f"  {tier}: {count} sections")


if __name__ == "__main__":
    main()
