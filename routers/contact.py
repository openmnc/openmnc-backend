"""
Contact & Smart Lead Generation Router — /api/contact
Supports intent-based capture, automated categorization, and sales/HR tracking.
"""

from datetime import datetime, timezone
from typing import Optional, List

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth import get_current_admin, require_editor
from database import get_collection
from models.contact import ContactSubmission, LeadCaptureRequest, LeadOut, LeadUpdateStatus

router = APIRouter(prefix="/api/contact", tags=["contact"])


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    if "submitted_at" not in doc:
        doc["submitted_at"] = datetime.now(timezone.utc)
    return doc


def _auto_categorize_lead(data: dict) -> tuple[str, str]:
    """
    Intelligently inspects fields, message text, and lead_type
    to assign an intent_tag and human-friendly category_label.
    """
    lead_type = data.get("lead_type", "b2b").lower()
    msg = (data.get("message") or "").lower()
    service_interest = (data.get("service_interest") or "").lower()
    is_subsidy = data.get("interested_in_college_subsidy", False)
    is_training = data.get("interested_in_training", False)

    if lead_type == "student" or is_subsidy or "student" in service_interest or "college" in msg:
        if is_training or "training" in msg or "iot" in msg or "robotics" in msg:
            return "INDUSTRIAL_TRAINING_IOT", "Industrial Training (3-Month)"
        return "STUDENT_SUBSIDY_EDTECH", "Student Career & College Subsidy"

    if "automation" in service_interest or "ai" in service_interest or "automate" in msg:
        return "B2B_AI_SOLUTIONS", "AI Automation & Revenue Optimization"

    if "app" in service_interest or "software" in service_interest or "custom" in service_interest or "developer" in msg or "build" in msg:
        return "B2B_CUSTOM_APP", "Custom App & Product Development"

    if "social" in service_interest or "instagram" in msg or "youtube" in msg or "video" in msg or "organic" in msg:
        return "ORGANIC_SOCIAL_MEDIA", "Organic Social Media & Video Growth"

    if is_training:
        return "INDUSTRIAL_TRAINING_IOT", "Industrial Training (3-Month)"

    return "GENERAL_INQUIRY", "General Tech & Business Inquiry"


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def submit_contact(payload: LeadCaptureRequest):
    """
    Save a contact or intent-based lead submission (public).
    Automatically tags and categorizes the lead so the sales/admissions team knows
    the exact context before following up.
    """
    col = get_collection("contact_submissions")
    now = datetime.now(timezone.utc)
    data = payload.model_dump()

    # Automatic categorization if not manually specified
    if not data.get("intent_tag"):
        intent_tag, category_label = _auto_categorize_lead(data)
        data["intent_tag"] = intent_tag
        data["category_label"] = category_label
    else:
        data["category_label"] = data["intent_tag"].replace("_", " ").title()

    data["status"] = "New"
    data["wants_nda"] = bool(payload.wants_nda)
    data["submitted_at"] = now
    data["updated_at"] = now

    result = await col.insert_one(data)
    created = await col.find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("", response_model=List[LeadOut])
async def list_contacts(
    lead_type: Optional[str] = Query(None, description="Filter by 'b2b', 'student', or 'general'"),
    lead_status: Optional[str] = Query(None, description="Filter by status ('New', 'Contacted', etc.)"),
    intent_tag: Optional[str] = Query(None, description="Filter by intent tag"),
    user: dict = Depends(require_editor),
):
    """Return all contact submissions & categorized leads, newest first (admin only)."""
    col = get_collection("contact_submissions")
    query: dict = {}
    if lead_type:
        query["lead_type"] = lead_type
    if lead_status:
        query["status"] = lead_status
    if intent_tag:
        query["intent_tag"] = intent_tag

    cursor = col.find(query).sort("submitted_at", -1)
    return [_serialize(doc) async for doc in cursor]


@router.put("/{lead_id}/status", response_model=LeadOut)
async def update_lead_status(
    lead_id: str,
    payload: LeadUpdateStatus,
    user: dict = Depends(require_editor),
):
    """Update lead status, internal notes, or team assignment (admin only)."""
    col = get_collection("contact_submissions")
    if not ObjectId.is_valid(lead_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid lead ID")

    now = datetime.now(timezone.utc)
    update_data = {
        "status": payload.status,
        "updated_at": now,
    }
    if payload.notes is not None:
        update_data["notes"] = payload.notes
    if payload.assigned_to is not None:
        update_data["assigned_to"] = payload.assigned_to

    doc = await col.find_one_and_update(
        {"_id": ObjectId(lead_id)},
        {"$set": update_data},
        return_document=True,
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return _serialize(doc)
