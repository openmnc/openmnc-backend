"""
Media Router — /api/media
Handles Cloudinary image uploads for CMS (Blog covers, service icons, author photos).
Zero binary files stored in MongoDB.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from auth import get_current_admin, require_author
from cloudinary_service import is_cloudinary_configured, upload_image_to_cloudinary

router = APIRouter(prefix="/api/media", tags=["media"])


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    folder: str = Form("openmnc_cms"),
    user: dict = Depends(require_author),
):
    """
    Uploads an image file to Cloudinary CDN (admin/HR only).
    Returns the secure HTTPS URL to be saved in blog/service documents.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image files (JPEG, PNG, WebP, SVG, GIF) are accepted.",
        )

    # Read binary bytes into memory for upload
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image size exceeds 10MB limit.",
        )

    if not is_cloudinary_configured():
        # Helpful message for developer/admin
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cloudinary is not configured. Please add CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET to your environment variables.",
        )

    try:
        result = await upload_image_to_cloudinary(content, file.filename, folder=folder)
        return {
            "success": True,
            "url": result["url"],
            "public_id": result["public_id"],
            "format": result.get("format"),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload to Cloudinary failed: {str(e)}",
        )
