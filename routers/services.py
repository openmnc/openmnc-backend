"""
Services router — full CRUD for /api/services
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_admin, require_author
from database import get_collection
from models.service import ServiceCreate, ServiceOut, ServiceUpdate
from webhook_service import trigger_deploy_hook

router = APIRouter(prefix="/api/services", tags=["services"])

# Default 6 Core Verticals of OpenMNC LLP
DEFAULT_SERVICES = [
    {
        "slug": "business-automation",
        "title": "Business Automation & AI Integration",
        "tagline": "Multiply revenue. Eliminate manual work.",
        "icon": "automation",
        "description": "We help businesses automate repetitive tasks, integrate custom AI solutions, increase revenue, improve reliability and efficiency, reduce time-consuming manual labor, and become genuinely competitive in an AI-first world.",
        "features": [
            "Custom AI workflow automation",
            "Revenue multiplication strategies",
            "Business process optimization",
            "AI integration consulting",
            "Reliability & uptime guarantee",
            "Zero time-waste operations",
        ],
        "order": 1,
        "is_active": True,
    },
    {
        "slug": "custom-development",
        "title": "Custom App & Software Development",
        "tagline": "From your idea to a living product.",
        "icon": "development",
        "description": "Transforming visionary ideas into reality with deep requirement analysis, full-cycle development, maintenance, marketing, and App Store Optimization (ASO). We understand your vision first before writing a single line of code.",
        "features": [
            "Deep requirement analysis",
            "Full-cycle development & QA",
            "App Store Optimization (ASO)",
            "Marketing & growth support",
            "Ongoing maintenance & SLA",
            "Solopreneur & founder friendly",
        ],
        "order": 2,
        "is_active": True,
    },
    {
        "slug": "inhouse-products",
        "title": "In-House Products & Games",
        "tagline": "Products we build, publish, and stand behind.",
        "icon": "development",
        "description": "OpenMNC develops and publishes proprietary custom software, mobile apps, and games on Google Play and Apple App Store. Flagship titles include Kibo VPN (privacy-first tool), Calorie AI (smart nutrition assistant), and CardSnap (digital networking).",
        "features": [
            "Google Play & App Store published",
            "Kibo VPN — Privacy & security utility",
            "Calorie AI — Smart health tracker",
            "CardSnap — Intelligent business card tool",
            "Custom mobile games development",
            "Proprietary software innovation",
        ],
        "order": 3,
        "is_active": True,
    },
    {
        "slug": "social-media-management",
        "title": "Social Media Management & Organic Growth",
        "tagline": "Grow organically without heavy ad spend.",
        "icon": "social-media",
        "description": "High-ROI organic growth for local shops, bakeries, real estate, factories, and solopreneurs across Instagram, Facebook, and YouTube. We research your niche, algorithm-match keywords and hashtags, write viral scripts using our Hook → Engagement → Relativity → Reveal structure, and edit your raw video into polished content.",
        "features": [
            "Instagram, Facebook & YouTube management",
            "Viral scripting (Hook → Engage → Reveal)",
            "Professional video editing & captions",
            "Relatable hashtag & keyword strategy",
            "Algorithm optimization for organic reach",
            "Fraction of ad spend with maximum trust",
        ],
        "order": 4,
        "is_active": True,
    },
    {
        "slug": "student-guidance",
        "title": "Student Guidance & EdTech Engine",
        "tagline": "100% free guidance. Real college savings.",
        "icon": "student-guidance",
        "description": "We guide 12th-pass students to choose their ideal career and college based on aptitude — 100% free of charge. Eligible students enrolling in our partner colleges receive ₹3,000 to ₹10,000 in partnership discounts/subsidies paid by us as an industrial partner.",
        "features": [
            "100% free student career consultation",
            "₹3,000–₹10,000 partner college subsidy",
            "Field alignment & aptitude matching",
            "College selection & admission roadmap",
            "Industrial partnership fee discounts",
            "Zero charges or hidden fees for students",
        ],
        "order": 5,
        "is_active": True,
    },
    {
        "slug": "industrial-training",
        "title": "Advanced Industrial Training",
        "tagline": "Real projects. High-end tech. 3 months.",
        "icon": "training",
        "description": "A comprehensive 3-month hands-on industrial training program tackling high-end tech: Robotics, Drones, and AI Smart Home assistants in IoT, plus modern Web and App Development. Affordable pricing at ₹3,000–₹7,000, with college partner subsidies directly offsettable or refundable.",
        "features": [
            "Advanced IoT (Robotics, Drones, AI Smart Home)",
            "Modern Web & Application Development",
            "3-month real production project delivery",
            "Coding, hardware & logistics in one frame",
            "₹3,000–₹7,000 affordable pricing structure",
            "Partner subsidy offset / cashback option",
        ],
        "order": 6,
        "is_active": True,
    },
]


def _serialize(doc: dict) -> dict:
    """Convert MongoDB document to ServiceOut-compatible dict."""
    doc["id"] = str(doc.pop("_id"))
    if "updated_at" not in doc:
        doc["updated_at"] = datetime.now(timezone.utc)
    return doc


async def _ensure_default_services_seeded(col):
    """Auto-seeds the 6 default OpenMNC services if collection is empty."""
    count = await col.count_documents({})
    if count == 0:
        now = datetime.now(timezone.utc)
        docs_to_insert = [{**s, "updated_at": now} for s in DEFAULT_SERVICES]
        await col.insert_many(docs_to_insert)


@router.get("", response_model=list[ServiceOut])
async def list_services(all: bool = False):
    """
    Return services sorted by order.
    If all=True, returns all services (active and inactive) for admin CMS.
    If all=False (default), returns only active services for public website.
    Auto-populates the 6 standard services if database is initially empty.
    """
    col = get_collection("services")
    await _ensure_default_services_seeded(col)

    query = {} if all else {"is_active": True}
    cursor = col.find(query).sort("order", 1)
    return [_serialize(doc) async for doc in cursor]


@router.post("/seed-defaults", response_model=list[ServiceOut])
async def seed_default_services(user: dict = Depends(require_author)):
    """
    Admin button to ensure all 6 default OpenMNC services are seeded in the database.
    Does not delete any existing custom services.
    """
    col = get_collection("services")
    now = datetime.now(timezone.utc)
    for svc in DEFAULT_SERVICES:
        existing = await col.find_one({"slug": svc["slug"]})
        if not existing:
            await col.insert_one({**svc, "updated_at": now})

    cursor = col.find({}).sort("order", 1)
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
    user: dict = Depends(require_author),
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
    user: dict = Depends(require_author),
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
async def delete_service(slug: str, user: dict = Depends(require_author)):
    """Delete a service by slug (admin only)."""
    col = get_collection("services")
    result = await col.delete_one({"slug": slug})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Service '{slug}' not found")
    asyncio.create_task(trigger_deploy_hook(f"Service Deleted: {slug}"))
