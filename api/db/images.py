from typing import Optional
from .client import get_supabase_client


class ImagesDB:
    """Database operations for seat images."""

    @staticmethod
    def list(venue_id: str, tier: Optional[str] = None, section: Optional[str] = None):
        """List all images for a venue with optional filters."""
        client = get_supabase_client()

        query = client.table("images").select("*").eq("venue_id", venue_id)

        if tier:
            query = query.eq("tier", tier)
        if section:
            query = query.eq("section", section)

        response = query.execute()

        images = []
        for row in response.data:
            images.append({
                "seat_id": row["seat_id"],
                "section": row["section"],
                "row": row["row"],
                "seat": row["seat"],
                "tier": row["tier"],
                "depth_map_url": row.get("depth_map_url"),
                "final_image_url": row.get("final_image_url"),
            })

        return {
            "venue_id": venue_id,
            "images": images,
            "total": len(images),
        }

    @staticmethod
    def get(venue_id: str, seat_id: str):
        """Get a single image by venue and seat ID."""
        client = get_supabase_client()

        response = client.table("images").select("*").eq(
            "venue_id", venue_id
        ).eq("seat_id", seat_id).single().execute()

        if not response.data:
            return None

        row = response.data
        return {
            "seat_id": row["seat_id"],
            "section": row["section"],
            "row": row["row"],
            "seat": row["seat"],
            "tier": row["tier"],
            "depth_map_url": row.get("depth_map_url"),
            "final_image_url": row.get("final_image_url"),
        }

    @staticmethod
    def create(
        venue_id: str,
        seat_id: str,
        section: str,
        row: str,
        seat: int,
        tier: str,
        depth_map_url: Optional[str] = None,
        final_image_url: Optional[str] = None,
    ):
        """Create or update an image record."""
        client = get_supabase_client()

        data = {
            "venue_id": venue_id,
            "seat_id": seat_id,
            "section": section,
            "row": row,
            "seat": seat,
            "tier": tier,
            "depth_map_url": depth_map_url,
            "final_image_url": final_image_url,
        }

        # Upsert (insert or update)
        response = client.table("images").upsert(
            data, on_conflict="venue_id,seat_id"
        ).execute()

        return data

    @staticmethod
    def update(venue_id: str, seat_id: str, **kwargs):
        """Update image fields."""
        client = get_supabase_client()

        allowed_fields = {"depth_map_url", "final_image_url"}
        update_data = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if update_data:
            client.table("images").update(update_data).eq(
                "venue_id", venue_id
            ).eq("seat_id", seat_id).execute()

        return ImagesDB.get(venue_id, seat_id)

    @staticmethod
    def delete(venue_id: str, seat_id: Optional[str] = None):
        """Delete images. If seat_id is None, delete all images for venue."""
        client = get_supabase_client()

        query = client.table("images").delete().eq("venue_id", venue_id)

        if seat_id:
            query = query.eq("seat_id", seat_id)

        query.execute()
        return True

    @staticmethod
    def bulk_create(venue_id: str, images: list):
        """Bulk create image records."""
        client = get_supabase_client()

        records = []
        for img in images:
            records.append({
                "venue_id": venue_id,
                "seat_id": img["seat_id"],
                "section": img["section"],
                "row": img["row"],
                "seat": img["seat"],
                "tier": img["tier"],
                "depth_map_url": img.get("depth_map_url"),
                "final_image_url": img.get("final_image_url"),
            })

        if records:
            client.table("images").upsert(
                records, on_conflict="venue_id,seat_id"
            ).execute()

        return records
