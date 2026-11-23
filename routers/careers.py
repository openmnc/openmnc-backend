"""
Careers & HR Application Portal Router — /api/careers
Features:
1. Public job listings with Google Jobs Schema support
2. Zero-Storage resume handling (Google Drive URLs)
3. Direct sync with Google Sheets for HR operations
4. Candidate status tracker API (tracking by email / OAuth sub)
5. Full admin HR applicant management
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, List

import os
import re
import uuid
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, status
from pydantic import EmailStr

from auth import get_current_admin, require_editor
from database import get_collection
from google_service import append_candidate_to_google_sheet
from webhook_service import trigger_deploy_hook
from cloudinary_service import is_cloudinary_configured, upload_document_to_cloudinary
from cache import get_cached, set_cached, invalidate_cache
from models.career import (
    CareerCreate,
    CareerOut,
    CareerUpdate,
    JobApplicationCreate,
    JobApplicationOut,
    JobApplicationStatusUpdate,
)

router = APIRouter(prefix="/api/careers", tags=["careers"])


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


# ---------------------------------------------------------------------------
# Public Job Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=List[CareerOut])
async def list_jobs(
    response: Response,
    department: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
):
    """Return all active job openings (public), cached in RAM."""
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
    cache_key = f"careers:{department}:{job_type}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    col = get_collection("careers")
    query: dict = {"is_active": True}
    if department:
        query["department"] = {"$regex": f"^{department}$", "$options": "i"}
    if job_type:
        query["type"] = {"$regex": f"^{job_type}$", "$options": "i"}

    cursor = col.find(query).sort("posted_at", -1)
    data = [_serialize(doc) async for doc in cursor]
    set_cached(cache_key, data)
    return data


@router.get("/all", response_model=List[CareerOut])
async def list_all_jobs_admin(user: dict = Depends(require_editor)):
    """Return all jobs including inactive for HR management (admin only)."""
    col = get_collection("careers")
    cursor = col.find({}).sort("posted_at", -1)
    return [_serialize(doc) async for doc in cursor]


@router.get("/{job_id}", response_model=CareerOut)
async def get_job(job_id: str):
    """Return a single job posting by ID (public)."""
    col = get_collection("careers")
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job ID")

    doc = await col.find_one({"_id": ObjectId(job_id)})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job opening not found")
    return _serialize(doc)


# ---------------------------------------------------------------------------
# Admin HR Job Management Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=CareerOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: CareerCreate,
    user: dict = Depends(require_editor),
):
    """Post a new job opening (admin/HR only)."""
    col = get_collection("careers")
    now = datetime.now(timezone.utc)
    data = payload.model_dump()
    data["posted_at"] = now
    data["updated_at"] = now

    result = await col.insert_one(data)
    created = await col.find_one({"_id": result.inserted_id})
    asyncio.create_task(trigger_deploy_hook(f"Job Opening Created: {payload.title}"))
    return _serialize(created)


@router.put("/{job_id}", response_model=CareerOut)
async def update_job(
    job_id: str,
    payload: CareerUpdate,
    user: dict = Depends(require_editor),
):
    """Update an existing job opening (admin/HR only)."""
    col = get_collection("careers")
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job ID")

    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update")

    update_data["updated_at"] = datetime.now(timezone.utc)
    doc = await col.find_one_and_update(
        {"_id": ObjectId(job_id)},
        {"$set": update_data},
        return_document=True,
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job opening not found")
    asyncio.create_task(trigger_deploy_hook(f"Job Opening Updated: {job_id}"))
    return _serialize(doc)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    user: dict = Depends(require_editor),
):
    """Delete a job opening (admin/HR only)."""
    col = get_collection("careers")
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job ID")

    result = await col.delete_one({"_id": ObjectId(job_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job opening not found")
    asyncio.create_task(trigger_deploy_hook(f"Job Opening Deleted: {job_id}"))
    return None


# ---------------------------------------------------------------------------
# Candidate Applications (Zero-Storage, Google Sheets Sync, Status Tracking)
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}
MAX_RESUME_SIZE = 10 * 1024 * 1024  # 10 MB limit


@router.post("/upload-resume")
async def upload_candidate_resume(file: UploadFile = File(...)):
    """
    Direct candidate resume upload endpoint.
    Accepts PDF, DOC, DOCX up to 10MB.
    Uploads directly to Cloudinary CDN or saves safely to local storage,
    returning a clean secure URL.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Please upload a PDF or Word document (.pdf, .doc, .docx)."
        )

    content = await file.read()
    if len(content) > MAX_RESUME_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds 10MB limit. Please compress or link via Google Drive."
        )

    clean_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", os.path.splitext(file.filename or "resume")[0])
    safe_filename = f"{clean_base}_{uuid.uuid4().hex[:8]}{ext}"

    # 1. Cloudinary upload if configured
    if is_cloudinary_configured():
        try:
            result = await upload_document_to_cloudinary(content, safe_filename)
            return {"url": result["url"], "filename": safe_filename, "storage": "cloudinary"}
        except Exception as e:
            # Fall back to local storage if Cloudinary fails
            pass

    # 2. Local uploads folder fallback
    local_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "resumes")
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, safe_filename)
    with open(local_path, "wb") as f:
        f.write(content)

    return {
        "url": f"/uploads/resumes/{safe_filename}",
        "filename": safe_filename,
        "storage": "local",
    }


@router.post("/apply", response_model=JobApplicationOut, status_code=status.HTTP_201_CREATED)
async def submit_job_application(payload: JobApplicationCreate):
    """
    Candidate submits an application.
    - Zero-Storage: Resume URL points to Cloudinary CDN or Google Drive.
    - Automatically synced to HR Google Sheet.
    - Status set to 'Applied'.
    """
    data = payload.model_dump()

    # Validation: Must have either uploaded resume or Google Drive link
    if not data.get("resume_google_drive_url") and not data.get("resume_file_url"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide your resume by uploading a file or pasting a Google Drive link."
        )

    app_col = get_collection("job_applications")
    now = datetime.now(timezone.utc)
    data["status"] = "Applied"
    data["applied_at"] = now
    data["updated_at"] = now

    result = await app_col.insert_one(data)
    created = await app_col.find_one({"_id": result.inserted_id})

    # Trigger non-blocking sync to Google Sheets
    try:
        await append_candidate_to_google_sheet(data)
    except Exception:
        pass

    return _serialize(created)


@router.get("/track/my-applications", response_model=List[JobApplicationOut])
async def track_candidate_applications(
    email: EmailStr = Query(..., description="Candidate email used when applying"),
    oauth_sub: Optional[str] = Query(None, description="Optional Google OAuth sub identifier"),
):
    """
    Public candidate status tracker.
    Candidates can track real-time status of their applications (Applied, Under Review, Shortlisted, etc.).
    """
    app_col = get_collection("job_applications")
    query: dict = {"candidate_email": email}
    if oauth_sub:
        query["$or"] = [{"candidate_email": email}, {"google_oauth_sub": oauth_sub}]

    cursor = app_col.find(query).sort("applied_at", -1)
    return [_serialize(doc) async for doc in cursor]


@router.get("/admin/applications", response_model=List[JobApplicationOut])
async def list_all_applications_admin(
    job_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    user: dict = Depends(require_editor),
):
    """HR view of all job applications with status filters (admin only)."""
    app_col = get_collection("job_applications")
    query: dict = {}
    if job_id:
        query["job_id"] = job_id
    if status_filter:
        query["status"] = status_filter

    cursor = app_col.find(query).sort("applied_at", -1)
    return [_serialize(doc) async for doc in cursor]


@router.put("/admin/applications/{application_id}/status", response_model=JobApplicationOut)
async def update_application_status_admin(
    application_id: str,
    payload: JobApplicationStatusUpdate,
    user: dict = Depends(require_editor),
):
    """HR updates candidate application status, notes, or interview dates (admin only)."""
    app_col = get_collection("job_applications")
    if not ObjectId.is_valid(application_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid application ID")

    now = datetime.now(timezone.utc)
    update_data = {
        "status": payload.status,
        "updated_at": now,
    }
    if payload.hr_internal_notes is not None:
        update_data["hr_internal_notes"] = payload.hr_internal_notes
    if payload.interview_date is not None:
        update_data["interview_date"] = payload.interview_date

    doc = await app_col.find_one_and_update(
        {"_id": ObjectId(application_id)},
        {"$set": update_data},
        return_document=True,
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return _serialize(doc)


@router.delete("/admin/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application_admin(
    application_id: str,
    user: dict = Depends(require_editor),
):
    """Permanently delete a candidate job application (admin/HR only)."""
    app_col = get_collection("job_applications")
    if not ObjectId.is_valid(application_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid application ID")

    result = await app_col.delete_one({"_id": ObjectId(application_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return None
