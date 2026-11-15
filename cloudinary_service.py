"""
Cloudinary Media Service for OpenMNC LLP
Handles zero-storage image and asset uploads.
Images are uploaded directly to Cloudinary CDN; only clean HTTPS URLs are saved to the database.
Zero binary blobs, zero base64 strings in MongoDB.
"""

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("openmnc.cloudinary_service")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")


def is_cloudinary_configured() -> bool:
    return bool(CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET)


async def upload_image_to_cloudinary(
    file_bytes: bytes,
    filename: str,
    folder: str = "openmnc_cms",
) -> Dict[str, Any]:
    """
    Uploads raw image bytes to Cloudinary.
    Returns dict with secure_url, public_id, width, height, format.
    """
    if not is_cloudinary_configured():
        logger.warning("[Cloudinary] Credentials not configured. Please set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET.")
        raise ValueError("Cloudinary credentials are not configured in environment variables.")

    try:
        import cloudinary
        import cloudinary.uploader

        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
            secure=True,
        )

        # Upload binary stream
        response = cloudinary.uploader.upload(
            file_bytes,
            folder=folder,
            resource_type="image",
            overwrite=True,
        )

        return {
            "url": response.get("secure_url"),
            "public_id": response.get("public_id"),
            "format": response.get("format"),
            "width": response.get("width"),
            "height": response.get("height"),
        }
    except Exception as e:
        logger.error(f"[Cloudinary] Upload failed: {e}")
        raise RuntimeError(f"Cloudinary upload failed: {str(e)}")
