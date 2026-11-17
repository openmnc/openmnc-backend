"""
Blogs router — /api/blogs
Dynamic, AI-optimized blogging engine for OpenMNC LLP.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, List

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth import get_current_admin, require_author
from database import get_collection
from models.blog import BlogCreate, BlogOut, BlogUpdate
from webhook_service import trigger_deploy_hook

router = APIRouter(prefix="/api/blogs", tags=["blogs"])


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    if "faqs" not in doc or doc["faqs"] is None:
        doc["faqs"] = []
    return doc


@router.get("", response_model=List[BlogOut])
async def list_blogs(
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search in title or content"),
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
):
    """
    Return all published blog posts (public).
    Used by public blog hub, AI search crawlers, and RSS/Sitemaps.
    """
    col = get_collection("blogs")
    query: dict = {"is_published": True}

    if category and category.lower() != "all":
        query["category"] = {"$regex": f"^{category}$", "$options": "i"}

    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"excerpt": {"$regex": search, "$options": "i"}},
            {"tags": {"$in": [search]}},
        ]

    cursor = col.find(query).sort("created_at", -1).skip(skip).limit(limit)
    return [_serialize(doc) async for doc in cursor]


@router.get("/admin/all", response_model=List[BlogOut])
async def list_all_blogs_admin(
    user: dict = Depends(require_author),
):
    """Return all blog posts including drafts for HR/Admin CMS."""
    col = get_collection("blogs")
    cursor = col.find({}).sort("created_at", -1)
    return [_serialize(doc) async for doc in cursor]


@router.get("/{slug}", response_model=BlogOut)
async def get_blog_by_slug(slug: str):
    """
    Retrieve single blog post by slug.
    Automatically increments views_count.
    """
    col = get_collection("blogs")
    doc = await col.find_one_and_update(
        {"slug": slug},
        {"$inc": {"views_count": 1}},
        return_document=True,
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blog post with slug '{slug}' not found",
        )
    return _serialize(doc)


@router.post("", response_model=BlogOut, status_code=status.HTTP_201_CREATED)
async def create_blog(
    payload: BlogCreate,
    user: dict = Depends(require_author),
):
    """Create a new blog post (admin/HR only)."""
    col = get_collection("blogs")

    # Check for slug collision
    existing = await col.find_one({"slug": payload.slug})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Blog post with slug '{payload.slug}' already exists",
        )

    now = datetime.now(timezone.utc)
    data = payload.model_dump()
    data["views_count"] = 0
    data["created_at"] = now
    data["updated_at"] = now

    result = await col.insert_one(data)
    created = await col.find_one({"_id": result.inserted_id})
    asyncio.create_task(trigger_deploy_hook(f"Blog Published: {payload.slug}"))
    return _serialize(created)


@router.put("/{slug}", response_model=BlogOut)
async def update_blog(
    slug: str,
    payload: BlogUpdate,
    user: dict = Depends(require_author),
):
    """Update an existing blog post (admin/HR only)."""
    col = get_collection("blogs")
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided to update",
        )

    update_data["updated_at"] = datetime.now(timezone.utc)

    # Check slug conflict if slug is being updated
    if "slug" in update_data and update_data["slug"] != slug:
        conflict = await col.find_one({"slug": update_data["slug"]})
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Blog with slug '{update_data['slug']}' already exists",
            )

    doc = await col.find_one_and_update(
        {"slug": slug},
        {"$set": update_data},
        return_document=True,
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blog post with slug '{slug}' not found",
        )
    asyncio.create_task(trigger_deploy_hook(f"Blog Updated: {slug}"))
    return _serialize(doc)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog(
    slug: str,
    user: dict = Depends(require_author),
):
    """Delete a blog post (admin/HR only)."""
    col = get_collection("blogs")
    result = await col.delete_one({"slug": slug})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blog post with slug '{slug}' not found",
        )
    asyncio.create_task(trigger_deploy_hook(f"Blog Deleted: {slug}"))
    return None
