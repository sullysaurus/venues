"""
Supabase Storage operations for images.
"""

import os
from typing import Optional
from pathlib import Path
from .client import get_supabase_client

BUCKET_NAME = "IMAGES"


class StorageDB:
    """Storage operations for venue images."""

    @staticmethod
    def upload_image(
        venue_id: str,
        seat_id: str,
        image_data: bytes,
        image_type: str = "final",  # "final" or "depth"
    ) -> str:
        """
        Upload an image to Supabase Storage.
        Returns the public URL.
        """
        client = get_supabase_client()

        # Determine file extension and content type
        if image_type == "depth":
            file_ext = "png"
            content_type = "image/png"
            file_path = f"{venue_id}/depth_maps/{seat_id}_depth.{file_ext}"
        else:
            file_ext = "jpg"
            content_type = "image/jpeg"
            file_path = f"{venue_id}/final_images/{seat_id}_final.{file_ext}"

        # Upload to storage
        response = client.storage.from_(BUCKET_NAME).upload(
            file_path,
            image_data,
            file_options={"content-type": content_type, "upsert": "true"}
        )

        # Get public URL
        public_url = client.storage.from_(BUCKET_NAME).get_public_url(file_path)
        return public_url

    @staticmethod
    def get_image_url(venue_id: str, seat_id: str, image_type: str = "final") -> str:
        """Get the public URL for an image."""
        client = get_supabase_client()

        if image_type == "depth":
            file_path = f"{venue_id}/depth_maps/{seat_id}_depth.png"
        else:
            file_path = f"{venue_id}/final_images/{seat_id}_final.jpg"

        return client.storage.from_(BUCKET_NAME).get_public_url(file_path)

    @staticmethod
    def download_image(venue_id: str, seat_id: str, image_type: str = "final") -> Optional[bytes]:
        """Download an image from Supabase Storage."""
        client = get_supabase_client()

        if image_type == "depth":
            file_path = f"{venue_id}/depth_maps/{seat_id}_depth.png"
        else:
            file_path = f"{venue_id}/final_images/{seat_id}_final.jpg"

        try:
            response = client.storage.from_(BUCKET_NAME).download(file_path)
            return response
        except Exception:
            return None

    @staticmethod
    def delete_image(venue_id: str, seat_id: str, image_type: str = "final") -> bool:
        """Delete an image from Supabase Storage."""
        client = get_supabase_client()

        if image_type == "depth":
            file_path = f"{venue_id}/depth_maps/{seat_id}_depth.png"
        else:
            file_path = f"{venue_id}/final_images/{seat_id}_final.jpg"

        try:
            client.storage.from_(BUCKET_NAME).remove([file_path])
            return True
        except Exception:
            return False

    @staticmethod
    def delete_venue_images(venue_id: str) -> bool:
        """Delete all images for a venue."""
        client = get_supabase_client()

        try:
            # List and delete all files in the venue folder
            depth_files = client.storage.from_(BUCKET_NAME).list(f"{venue_id}/depth_maps")
            final_files = client.storage.from_(BUCKET_NAME).list(f"{venue_id}/final_images")

            files_to_delete = []
            for f in depth_files:
                files_to_delete.append(f"{venue_id}/depth_maps/{f['name']}")
            for f in final_files:
                files_to_delete.append(f"{venue_id}/final_images/{f['name']}")

            if files_to_delete:
                client.storage.from_(BUCKET_NAME).remove(files_to_delete)

            return True
        except Exception:
            return False

    @staticmethod
    def upload_preview(venue_id: str, image_data: bytes) -> str:
        """Upload a 3D model preview image."""
        client = get_supabase_client()

        file_path = f"{venue_id}/preview.png"

        client.storage.from_(BUCKET_NAME).upload(
            file_path,
            image_data,
            file_options={"content-type": "image/png", "upsert": "true"}
        )

        return client.storage.from_(BUCKET_NAME).get_public_url(file_path)

    @staticmethod
    def get_preview_url(venue_id: str) -> Optional[str]:
        """Get the public URL for a venue's 3D model preview."""
        client = get_supabase_client()
        file_path = f"{venue_id}/preview.png"
        return client.storage.from_(BUCKET_NAME).get_public_url(file_path)

    @staticmethod
    def upload_seatmap(venue_id: str, event_type: str, image_data: bytes) -> str:
        """Upload a seatmap image."""
        client = get_supabase_client()

        file_path = f"{venue_id}/seatmaps/{event_type}.png"

        client.storage.from_(BUCKET_NAME).upload(
            file_path,
            image_data,
            file_options={"content-type": "image/png", "upsert": "true"}
        )

        return client.storage.from_(BUCKET_NAME).get_public_url(file_path)

    @staticmethod
    def get_seatmap_url(venue_id: str, event_type: str = "default") -> Optional[str]:
        """Get the public URL for a seatmap."""
        client = get_supabase_client()
        file_path = f"{venue_id}/seatmaps/{event_type}.png"
        return client.storage.from_(BUCKET_NAME).get_public_url(file_path)
