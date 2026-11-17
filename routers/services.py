"""
Services router — full CRUD for /api/services
Dynamic, AI-Engine Optimized (AEO) and SEO Deep-Linking Architecture for OpenMNC LLP
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth import get_current_admin, require_author
from database import get_collection
from models.service import ServiceCreate, ServiceOut, ServiceUpdate
from webhook_service import trigger_deploy_hook

router = APIRouter(prefix="/api/services", tags=["services"])

# Default 6 Core Verticals of OpenMNC LLP enriched with AEO fields
DEFAULT_SERVICES = [
    {
        "slug": "business-automation",
        "title": "Business Automation & AI Integration",
        "tagline": "Multiply revenue. Eliminate repetitive manual work.",
        "icon": "automation",
        "category": "B2B Enterprise",
        "description": "We help businesses automate repetitive tasks, integrate custom AI solutions, increase revenue, improve reliability and efficiency, reduce time-consuming manual labor, and become genuinely competitive in an AI-first world.",
        "problem_statement": "Businesses lose thousands of work-hours and revenue each month due to fragmented manual data entry, slow lead qualification, and unintegrated SaaS tools.",
        "technical_solution": "OpenMNC architects custom autonomous AI multi-agent workflows, LLM pipelines, and event-driven automation directly into client CRMs and databases.",
        "expected_outcome": "90% reduction in manual labor, 3x faster response times, and 24/7 autonomous operations without costly SaaS subscriptions.",
        "features": [
            "Custom AI workflow automation",
            "Revenue multiplication strategies",
            "Business process optimization",
            "AI integration consulting",
            "Reliability & uptime guarantee",
            "Zero time-waste operations",
        ],
        "faqs": [
            {
                "question": "Can AI really automate my specific industry?",
                "answer": "Yes, we build custom LLM wrappers, autonomous agent workflows, and webhook pipelines tailored specifically to your data and existing business tools."
            },
            {
                "question": "How does OpenMNC protect client data privacy?",
                "answer": "We deploy dedicated on-premise or private-cloud inference pipelines with zero public training exposure and strict enterprise encryption standards."
            }
        ],
        "sub_services": [
            {
                "slug": "workflow-bots",
                "title": "Autonomous Multi-Agent Workflow Bots",
                "tagline": "Eliminate human coordination bottlenecks",
                "problem_statement": "Manual coordination across departments slows delivery and increases errors.",
                "technical_solution": "LangChain and AutoGen multi-agent orchestrations triggering CRM, ERP, and payment webhooks.",
                "expected_outcome": "Instant task routing and 24/7 automated reconciliation with zero human delay."
            }
        ],
        "order": 1,
        "is_active": True,
    },
    {
        "slug": "custom-development",
        "title": "Custom App & Software Development",
        "tagline": "From your idea to a living product.",
        "icon": "development",
        "category": "B2B Enterprise",
        "description": "Transforming visionary ideas into reality with deep requirement analysis, full-cycle development, maintenance, marketing, and App Store Optimization (ASO). We understand your vision first before writing a single line of code.",
        "problem_statement": "Companies need alternatives to AppMetrica/AppsFlyer for custom funnel tracking without recurring per-seat fees or data leaks.",
        "technical_solution": "Custom-built tracking APIs, event ingestion pipelines, and full-stack software integrated directly into the client's cloud infrastructure.",
        "expected_outcome": "100% data ownership with zero third-party subscription fees and microsecond analytics querying.",
        "features": [
            "Deep requirement analysis",
            "Full-cycle development & QA",
            "App Store Optimization (ASO)",
            "Marketing & growth support",
            "Ongoing maintenance & SLA",
            "Solopreneur & founder friendly",
        ],
        "faqs": [
            {
                "question": "How long does custom software development take?",
                "answer": "Depends on scope, but we use agile sprints for fast MVP delivery, typically launching production-ready systems in 4 to 8 weeks."
            },
            {
                "question": "Do you build alternative analytics and attribution systems?",
                "answer": "Yes, we build custom analytics & attribution tracking systems replacing AppMetrica or AppsFlyer with 100% private data ownership."
            }
        ],
        "sub_services": [
            {
                "slug": "analytics-tracking",
                "title": "Custom Analytics & Attribution Engine (AppMetrica / AppsFlyer Alternative)",
                "tagline": "100% data ownership with zero third-party subscription fees",
                "problem_statement": "Companies need alternatives to AppMetrica/AppsFlyer for custom funnel tracking without exorbitant per-event pricing or external data sharing.",
                "technical_solution": "Custom-built tracking APIs, lightweight mobile SDKs, and event ingestion pipelines integrated directly into the client's infrastructure.",
                "expected_outcome": "100% data ownership with zero third-party subscription fees and microsecond attribution query speeds."
            },
            {
                "slug": "saas-platforms",
                "title": "Scalable SaaS & Cloud Web Platforms",
                "tagline": "Engineered for high concurrency and zero downtime",
                "problem_statement": "Legacy web applications crumble under sudden traffic spikes and complex database queries.",
                "technical_solution": "Distributed React, FastAPI, Node, and Redis architectures designed for horizontal scaling.",
                "expected_outcome": "Sub-second page speeds, seamless load balancing, and 99.99% operational uptime."
            }
        ],
        "order": 2,
        "is_active": True,
    },
    {
        "slug": "inhouse-products",
        "title": "In-House Products & Games",
        "tagline": "Products we build, publish, and stand behind.",
        "icon": "development",
        "category": "B2B Enterprise",
        "description": "OpenMNC develops and publishes proprietary custom software, mobile apps, and games on Google Play and Apple App Store. Flagship titles include Kibo VPN (privacy-first tool), Calorie AI (smart nutrition assistant), and CardSnap (digital networking).",
        "problem_statement": "Users and businesses demand privacy-first tools and smart AI utilities without invasive trackers or exorbitant recurring prices.",
        "technical_solution": "OpenMNC builds and publishes proprietary mobile utilities with edge-processed data and zero data-mining.",
        "expected_outcome": "Over 50,000+ app downloads and production-hardened software IP.",
        "features": [
            "Google Play & App Store published",
            "Kibo VPN — Privacy & security utility",
            "Calorie AI — Smart health tracker",
            "CardSnap — Intelligent business card tool",
            "Custom mobile games development",
            "Proprietary software innovation",
        ],
        "faqs": [
            {
                "question": "Can OpenMNC develop white-label versions of in-house products?",
                "answer": "Yes, we license and customize our proprietary engines (VPN, AI vision, OCR) for enterprise white-label deployment."
            }
        ],
        "sub_services": [],
        "order": 3,
        "is_active": True,
    },
    {
        "slug": "social-media-management",
        "title": "Social Media Management & Organic Growth",
        "tagline": "Grow organically without heavy ad spend.",
        "icon": "social-media",
        "category": "B2B Enterprise",
        "description": "High-ROI organic growth for local shops, bakeries, real estate, factories, and solopreneurs across Instagram, Facebook, and YouTube. We research your niche, algorithm-match keywords and hashtags, write viral scripts using our Hook → Engagement → Relativity → Reveal structure, and edit your raw video into polished content.",
        "problem_statement": "Local businesses burn capital on expensive pay-per-click ads with zero long-term organic retention or audience trust.",
        "technical_solution": "Algorithmic keyword optimization, high-retention video scripting (Hook → Engage → Reveal), and professional editing.",
        "expected_outcome": "Up to 10x organic reach and authentic audience trust at a fraction of paid advertisement spend.",
        "features": [
            "Instagram, Facebook & YouTube management",
            "Viral scripting (Hook → Engage → Reveal)",
            "Professional video editing & captions",
            "Relatable hashtag & keyword strategy",
            "Algorithm optimization for organic reach",
            "Fraction of ad spend with maximum trust",
        ],
        "faqs": [
            {
                "question": "How soon do we see organic reach results?",
                "answer": "Clients typically experience noticeable engagement upticks within 3 to 4 weeks as the platform algorithm indexes relatable video hooks."
            }
        ],
        "sub_services": [],
        "order": 4,
        "is_active": True,
    },
    {
        "slug": "student-guidance",
        "title": "Student Guidance & EdTech Engine",
        "tagline": "100% free guidance. Real college savings.",
        "icon": "student-guidance",
        "category": "B2C Academy",
        "description": "We guide 12th-pass students to choose their ideal career and college based on aptitude — 100% free of charge. Eligible students enrolling in our partner colleges receive ₹3,000 to ₹10,000 in partnership discounts/subsidies paid by us as an industrial partner.",
        "problem_statement": "12th-pass students and parents are misled by commission brokers into overpriced courses with low placement outcomes.",
        "technical_solution": "100% free aptitude profiling, university accreditation audits, and industrial partnership fee scholarships.",
        "expected_outcome": "Direct ₹3,000 to ₹10,000 college admission fee subsidy paid directly by OpenMNC as an industrial partner, with zero student fees.",
        "features": [
            "100% free student career consultation",
            "₹3,000–₹10,000 partner college subsidy",
            "Field alignment & aptitude matching",
            "College selection & admission roadmap",
            "Industrial partnership fee discounts",
            "Zero charges or hidden fees for students",
        ],
        "faqs": [
            {
                "question": "Why is student career guidance 100% free?",
                "answer": "OpenMNC is an authorized industrial technology partner for accredited institutions. We bridge industry needs with student talent with zero broker fees."
            },
            {
                "question": "How much subsidy or fee discount do students receive?",
                "answer": "Eligible students receive ₹3,000 to ₹10,000 directly discounted from college admission fees as an industrial subsidy."
            }
        ],
        "sub_services": [
            {
                "slug": "college-selection",
                "title": "Aptitude-Based College Selection",
                "tagline": "100% free guidance for 12th pass students",
                "problem_statement": "Students choose colleges based on hearsay rather than faculty, labs, and genuine placement track record.",
                "technical_solution": "Detailed comparative analysis across accredited universities with transparent fee structures.",
                "expected_outcome": "Optimal college admission with guaranteed partner subsidy offset."
            }
        ],
        "order": 5,
        "is_active": True,
    },
    {
        "slug": "industrial-training",
        "title": "Advanced Industrial Training",
        "tagline": "Real projects. High-end tech. 3 months.",
        "icon": "training",
        "category": "B2C Academy",
        "description": "A comprehensive 3-month hands-on industrial training program tackling high-end tech: Robotics, Drones, and AI Smart Home assistants in IoT, plus modern Web and App Development. Affordable pricing at ₹3,000–₹7,000, with college partner subsidies directly offsettable or refundable.",
        "problem_statement": "Engineering students graduate with only textbook knowledge and zero experience building production IoT hardware or AI cloud systems.",
        "technical_solution": "3-month hands-on industrial sprints building live Robotics, Drones, IoT embedded firmware, and modern full-stack web applications.",
        "expected_outcome": "Production-ready GitHub project portfolio, verifiable industrial training certificate, and priority hiring at OpenMNC.",
        "features": [
            "Advanced IoT (Robotics, Drones, AI Smart Home)",
            "Modern Web & Application Development",
            "3-month real production project delivery",
            "Coding, hardware & logistics in one frame",
            "₹3,000–₹7,000 affordable pricing structure",
            "Partner subsidy offset / cashback option",
        ],
        "faqs": [
            {
                "question": "Do you handle both hardware and software for IoT?",
                "answer": "Yes, we cover full-stack embedded engineering: ESP32/STM32 microcontrollers, sensor protocols, firmware, and cloud IoT dashboards."
            },
            {
                "question": "Can the training fees be offset?",
                "answer": "Yes, our partner college subsidy allows eligible students to offset or claim refunds of ₹3,000 to ₹7,000 directly."
            }
        ],
        "sub_services": [
            {
                "slug": "custom-hardware",
                "title": "IoT & Embedded Engineering (Robotics, Drones, Firmware)",
                "tagline": "Full-stack embedded engineering to cloud dashboard",
                "problem_statement": "Engineering students lack hands-on experience with production IoT hardware and drone telemetry.",
                "technical_solution": "Full-stack embedded engineering to cloud dashboard with ESP32, sensor buses, firmware, and ROS.",
                "expected_outcome": "Production-ready IoT devices and verified hardware engineering skills."
            }
        ],
        "order": 6,
        "is_active": True,
    },
]

# Alias map for dynamic routing & deep-link URLs
SLUG_ALIASES = {
    "custom-software": "custom-development",
    "software-development": "custom-development",
    "iot-development": "industrial-training",
    "iot-engineering": "industrial-training",
    "b2b-automation": "business-automation",
    "ai-automation": "business-automation",
    "academy": "student-guidance",
    "training": "industrial-training",
}


def _serialize(doc: dict) -> dict:
    """Convert MongoDB document to ServiceOut-compatible dict."""
    doc["id"] = str(doc.pop("_id"))
    if "updated_at" not in doc:
        doc["updated_at"] = datetime.now(timezone.utc)
    if "faqs" not in doc or doc["faqs"] is None:
        doc["faqs"] = []
    if "sub_services" not in doc or doc["sub_services"] is None:
        doc["sub_services"] = []
    if "category" not in doc:
        doc["category"] = "B2B Enterprise"
    return doc


async def _ensure_default_services_seeded(col):
    """Auto-seeds the 6 default OpenMNC services with AEO fields if collection is empty."""
    count = await col.count_documents({})
    if count == 0:
        now = datetime.now(timezone.utc)
        docs_to_insert = [{**s, "updated_at": now} for s in DEFAULT_SERVICES]
        await col.insert_many(docs_to_insert)
    else:
        # Check if existing services need AEO fields updated
        for svc in DEFAULT_SERVICES:
            await col.update_one(
                {"slug": svc["slug"], "problem_statement": {"$exists": False}},
                {"$set": {
                    "problem_statement": svc["problem_statement"],
                    "technical_solution": svc["technical_solution"],
                    "expected_outcome": svc["expected_outcome"],
                    "faqs": svc.get("faqs", []),
                    "sub_services": svc.get("sub_services", []),
                    "category": svc.get("category", "B2B Enterprise"),
                }}
            )


@router.get("", response_model=list[ServiceOut])
async def list_services(all: bool = False):
    """
    Return services sorted by order.
    If all=True, returns all services (active and inactive) for admin CMS.
    If all=False (default), returns only active services for public website.
    """
    col = get_collection("services")
    await _ensure_default_services_seeded(col)

    query = {} if all else {"is_active": True}
    cursor = col.find(query).sort("order", 1)
    return [_serialize(doc) async for doc in cursor]


@router.post("/seed-defaults", response_model=list[ServiceOut])
async def seed_default_services(user: dict = Depends(require_author)):
    """
    Admin button to ensure all default OpenMNC services with AEO fields are seeded/updated.
    """
    col = get_collection("services")
    now = datetime.now(timezone.utc)
    for svc in DEFAULT_SERVICES:
        existing = await col.find_one({"slug": svc["slug"]})
        if not existing:
            await col.insert_one({**svc, "updated_at": now})
        else:
            await col.update_one(
                {"slug": svc["slug"]},
                {"$set": {
                    "problem_statement": svc["problem_statement"],
                    "technical_solution": svc["technical_solution"],
                    "expected_outcome": svc["expected_outcome"],
                    "faqs": svc.get("faqs", []),
                    "sub_services": svc.get("sub_services", []),
                    "category": svc.get("category", "B2B Enterprise"),
                    "updated_at": now,
                }}
            )

    cursor = col.find({}).sort("order", 1)
    return [_serialize(doc) async for doc in cursor]


@router.get("/{slug}", response_model=ServiceOut)
async def get_service(slug: str):
    """Return a single service by slug or alias."""
    actual_slug = SLUG_ALIASES.get(slug.lower(), slug.lower())
    col = get_collection("services")
    doc = await col.find_one({"slug": actual_slug})
    if not doc:
        # Check if slug matches a sub_service across all services
        parent_doc = await col.find_one({"sub_services.slug": slug.lower()})
        if parent_doc:
            return _serialize(parent_doc)
        raise HTTPException(status_code=404, detail=f"Service '{slug}' not found")
    return _serialize(doc)


@router.get("/{category_or_slug}/{sub_slug}", response_model=Dict[str, Any])
async def get_deep_service(category_or_slug: str, sub_slug: str):
    """
    Deep-linking resolver for URLs like:
    /services/custom-software/analytics-tracking
    /services/iot-development/custom-hardware
    """
    actual_parent_slug = SLUG_ALIASES.get(category_or_slug.lower(), category_or_slug.lower())
    col = get_collection("services")
    doc = await col.find_one({"slug": actual_parent_slug})
    
    if not doc:
        # Try finding parent by sub_service directly
        doc = await col.find_one({"sub_services.slug": sub_slug.lower()})
    
    if not doc:
        raise HTTPException(
            status_code=404, 
            detail=f"Service deep link '{category_or_slug}/{sub_slug}' not found"
        )
    
    serialized = _serialize(doc)
    sub = next((s for s in serialized.get("sub_services", []) if s.get("slug") == sub_slug.lower()), None)
    
    return {
        "service": serialized,
        "sub_service": sub,
        "is_deep_link": True,
        "resolved_slug": serialized.get("slug"),
        "sub_slug": sub_slug,
    }


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: ServiceCreate,
    user: dict = Depends(require_author),
):
    """Create a new service (admin only)."""
    col = get_collection("services")
    clean_slug = payload.slug.strip().lower()
    existing = await col.find_one({"slug": clean_slug})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service with slug '{clean_slug}' already exists",
        )
    now = datetime.now(timezone.utc)
    data = payload.model_dump()
    data["slug"] = clean_slug
    data["updated_at"] = now
    result = await col.insert_one(data)
    created = await col.find_one({"_id": result.inserted_id})
    asyncio.create_task(trigger_deploy_hook(f"Service Created: {clean_slug}"))
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
