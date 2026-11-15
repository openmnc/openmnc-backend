"""
Settings router — /api/settings
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_admin, require_admin
from database import get_collection
from models.settings import SiteSettingOut, SiteSettingUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=dict)
async def get_all_settings():
    """Return all site settings as a flat {key: value} dict (public)."""
    col = get_collection("site_settings")
    cursor = col.find({})
    result: dict = {}
    async for doc in cursor:
        result[doc["key"]] = doc["value"]
    return result


@router.put("/{key}", response_model=SiteSettingOut)
async def upsert_setting(
    key: str,
    payload: SiteSettingUpdate,
    user: dict = Depends(require_admin),
):
    """Create or update a site setting by key (admin only)."""
    col = get_collection("site_settings")
    now = datetime.now(timezone.utc)

    # Retrieve existing to keep section intact
    existing = await col.find_one({"key": key})
    section = existing["section"] if existing else "general"

    result = await col.find_one_and_update(
        {"key": key},
        {"$set": {"value": payload.value, "updated_at": now, "section": section}},
        upsert=True,
        return_document=True,
    )
    return SiteSettingOut(
        key=result["key"],
        value=result["value"],
        section=result["section"],
        updated_at=result["updated_at"],
    )
