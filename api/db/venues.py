import re
from typing import Optional
from uuid import uuid4
from .client import get_supabase_client


def generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from a name."""
    # Convert to lowercase, replace non-alphanumeric with hyphens
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', name.lower())
    # Remove leading/trailing hyphens
    return slug.strip('-')


class VenuesDB:
    """Database operations for venues."""

    @staticmethod
    def _format_venue(row: dict) -> dict:
        """Format a venue row for API response."""
        # Generate slug from name if not present in DB (backwards compatibility)
        slug = row.get("slug")
        if not slug:
            slug = generate_slug(row["name"])

        return {
            "venue_id": row["id"],
            "slug": slug,
            "name": row["name"],
            "location": row.get("location"),
            "sections_count": row["sections"][0]["count"] if row.get("sections") else 0,
            "images_count": row["images"][0]["count"] if row.get("images") else 0,
            "event_types_count": row["event_types"][0]["count"] if row.get("event_types") else 0,
            "has_seatmap": row.get("has_seatmap", False),
            "has_model": row.get("has_model", False),
            "created_at": row.get("created_at"),
        }

    @staticmethod
    def list(limit: int = 100, offset: int = 0):
        """List all venues with counts."""
        client = get_supabase_client()

        # Try with event_types, fall back to without if table doesn't exist
        try:
            response = client.table("venues").select(
                "*, sections:sections(count), images:images(count), event_types:event_types(count)"
            ).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        except Exception:
            # Fallback if event_types table doesn't exist
            response = client.table("venues").select(
                "*, sections:sections(count), images:images(count)"
            ).order("created_at", desc=True).range(offset, offset + limit - 1).execute()

        venues = [VenuesDB._format_venue(row) for row in response.data]

        # Get total count
        count_response = client.table("venues").select("*", count="exact").execute()
        total = count_response.count or len(venues)

        return {"venues": venues, "total": total}

    @staticmethod
    def get(venue_id: str):
        """Get a single venue by ID or slug."""
        client = get_supabase_client()

        # Try by UUID first, then by slug
        is_uuid = len(venue_id) == 36 and '-' in venue_id

        try:
            if is_uuid:
                response = client.table("venues").select(
                    "*, sections:sections(count), images:images(count), event_types:event_types(count)"
                ).eq("id", venue_id).single().execute()
            else:
                # Try by slug
                response = client.table("venues").select(
                    "*, sections:sections(count), images:images(count), event_types:event_types(count)"
                ).eq("slug", venue_id).single().execute()
        except Exception:
            # Fallback without event_types
            if is_uuid:
                response = client.table("venues").select(
                    "*, sections:sections(count), images:images(count)"
                ).eq("id", venue_id).single().execute()
            else:
                response = client.table("venues").select(
                    "*, sections:sections(count), images:images(count)"
                ).eq("slug", venue_id).single().execute()

        if not response.data:
            return None

        return VenuesDB._format_venue(response.data)

    @staticmethod
    def get_by_slug(slug: str):
        """Get a single venue by slug."""
        client = get_supabase_client()

        response = client.table("venues").select(
            "*, sections:sections(count), images:images(count), event_types:event_types(count)"
        ).eq("slug", slug).single().execute()

        if not response.data:
            return None

        return VenuesDB._format_venue(response.data)

    @staticmethod
    def create(name: str, location: Optional[str] = None):
        """Create a new venue."""
        client = get_supabase_client()

        venue_id = str(uuid4())
        slug = generate_slug(name)

        # Ensure slug is unique
        existing = client.table("venues").select("id").eq("slug", slug).execute()
        if existing.data:
            slug = f"{slug}-{venue_id[:8]}"

        data = {
            "id": venue_id,
            "slug": slug,
            "name": name,
            "location": location,
            "has_seatmap": False,
            "has_model": False,
        }

        response = client.table("venues").insert(data).execute()
        row = response.data[0] if response.data else data

        return {
            "venue_id": venue_id,
            "slug": slug,
            "name": name,
            "location": location,
            "sections_count": 0,
            "images_count": 0,
            "event_types_count": 0,
            "has_seatmap": False,
            "has_model": False,
        }

    @staticmethod
    def delete(venue_id: str):
        """Delete a venue and its related data."""
        client = get_supabase_client()

        # Delete related images first
        client.table("images").delete().eq("venue_id", venue_id).execute()

        # Delete related sections
        client.table("sections").delete().eq("venue_id", venue_id).execute()

        # Delete the venue
        client.table("venues").delete().eq("id", venue_id).execute()

        return True

    @staticmethod
    def update(venue_id: str, **kwargs):
        """Update venue fields."""
        client = get_supabase_client()

        allowed_fields = {"name", "location", "has_seatmap", "has_model"}
        update_data = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if update_data:
            client.table("venues").update(update_data).eq("id", venue_id).execute()

        return VenuesDB.get(venue_id)

    @staticmethod
    def get_sections(venue_id: str):
        """Get all sections for a venue."""
        client = get_supabase_client()

        response = client.table("sections").select("*").eq("venue_id", venue_id).execute()

        sections = {}
        for row in response.data:
            sections[row["section_id"]] = {
                "section_id": row["section_id"],
                "tier": row["tier"],
                "angle": row["angle"],
                "inner_radius": row["inner_radius"],
                "rows": row["rows"],
                "row_depth": row["row_depth"],
                "row_rise": row["row_rise"],
                "base_height": row["base_height"],
            }

        return {"sections": sections}

    @staticmethod
    def update_sections(venue_id: str, sections: dict):
        """Update sections for a venue (replaces all)."""
        client = get_supabase_client()

        # Delete existing sections
        client.table("sections").delete().eq("venue_id", venue_id).execute()

        # Insert new sections
        for section_id, section_data in sections.items():
            data = {
                "venue_id": venue_id,
                "section_id": section_id,
                "tier": section_data.get("tier", "Standard"),
                "angle": section_data.get("angle", 0),
                "inner_radius": section_data.get("inner_radius", 20),
                "rows": section_data.get("rows", 10),
                "row_depth": section_data.get("row_depth", 0.8),
                "row_rise": section_data.get("row_rise", 0.3),
                "base_height": section_data.get("base_height", 0),
            }
            client.table("sections").insert(data).execute()

        return {"sections": sections}
