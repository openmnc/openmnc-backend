"""
Services router — full CRUD for /api/services
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_admin
from database import get_collection
from models.service import ServiceCreate, ServiceOut, ServiceUpdate
from webhook_service import trigger_deploy_hook

router = APIRouter(prefix="/api/services", tags=["services"])


def _serialize(doc: dict) -> dict:
    """Convert MongoDB document to ServiceOut-compatible dict."""
    doc["id"] = str(doc.pop("_id"))
    if "updated_at" not in doc:
        doc["updated_at"] = datetime.now(timezone.utc)
    return doc


@router.get("", response_model=list[ServiceOut])
async def list_services():
    """Return all active services sorted by order."""
    col = get_collection("services")
    cursor = col.find({"is_active": True}).sort("order", 1)
    return [_serialize(doc) async for doc in cursor]


@router.get("/{slug}", response_model=ServiceOut)
async def get_service(slug: str):
    """Return a single service by slug."""
    col = get_collection("services")
    doc = await col.find_one({"slug": slug})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Service '{slug}' not found")
    return _serialize(doc)


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: ServiceCreate,
    admin: str = Depends(get_current_admin),
):
    """Create a new service (admin only)."""
    col = get_collection("services")
    existing = await col.find_one({"slug": payload.slug})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service with slug '{payload.slug}' already exists",
        )
    now = datetime.now(timezone.utc)
    data = payload.model_dump()
    data["updated_at"] = now
    result = await col.insert_one(data)
    created = await col.find_one({"_id": result.inserted_id})
    asyncio.create_task(trigger_deploy_hook(f"Service Created: {payload.slug}"))
    return _serialize(created)


@router.put("/{slug}", response_model=ServiceOut)
async def update_service(
    slug: str,
    payload: ServiceUpdate,
    admin: str = Depends(get_current_admin),
):
    """Update an existing service by slug (admin only)."""
    col = get_collection("services")
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    update_data["updated_at"] = datetime.now(timezone.utc)
    result = await col.find_one_and_update(
        {"slug": slug},
        {"$set": update_data},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Service '{slug}' not found")
    asyncio.create_task(trigger_deploy_hook(f"Service Updated: {slug}"))
    return _serialize(result)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(slug: str, admin: str = Depends(get_current_admin)):
    """Delete a service by slug (admin only)."""
    col = get_collection("services")
    result = await col.delete_one({"slug": slug})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Service '{slug}' not found")
    asyncio.create_task(trigger_deploy_hook(f"Service Deleted: {slug}"))
