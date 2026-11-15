"""
Career & Applicant Tracking Models for OpenMNC LLP
Includes Google Jobs SEO schema fields, Zero-Storage resume handling,
and real-time candidate application status tracking.
"""

from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Job Postings (Public & Admin HR)
# ---------------------------------------------------------------------------

class CareerBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=150, example="Senior Full-Stack AI Engineer")
    department: str = Field(..., example="Engineering")  # "Engineering", "AI & Robotics", "Marketing & Growth", "Design", "EdTech & Operations"
    location: str = Field("Remote, India", example="Remote, India")
    type: str = Field("full-time", example="full-time")  # "full-time", "part-time", "contract", "internship", "remote"
    experience_level: str = Field("Mid-Senior", example="Mid-Senior")  # "Entry-Level", "Mid-Level", "Senior", "Internship"
    salary_range: Optional[str] = Field("Competitive + Performance Bonuses", example="₹6,00,000 - ₹12,00,000 / year")
    description: str = Field(..., example="We are looking for an ambitious engineer to lead client AI integrations and in-house product development.")
    responsibilities: List[str] = Field(default_factory=list, example=["Architect scalable backend microservices", "Deploy LLM agents"])
    requirements: List[str] = Field(default_factory=list, example=["3+ years Python / React experience", "Experience with FastAPI & MongoDB"])
    benefits: List[str] = Field(default_factory=lambda: ["100% Remote flexibility", "Learning stipend for AI certifications", "High growth equity options"])
    is_active: bool = Field(True)
    google_jobs_eligible: bool = Field(True)


class CareerCreate(CareerBase):
    pass


class CareerUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    type: Optional[str] = None
    experience_level: Optional[str] = None
    salary_range: Optional[str] = None
    description: Optional[str] = None
    responsibilities: Optional[List[str]] = None
    requirements: Optional[List[str]] = None
    benefits: Optional[List[str]] = None
    is_active: Optional[bool] = None
    google_jobs_eligible: Optional[bool] = None


class CareerOut(CareerBase):
    id: str
    posted_at: datetime
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Candidate Applications (Zero-Storage in MongoDB: Resume in Google Drive)
# ---------------------------------------------------------------------------

class JobApplicationCreate(BaseModel):
    job_id: str
    job_title: str
    candidate_name: str = Field(..., min_length=2, max_length=100)
    candidate_email: EmailStr
    candidate_phone: Optional[str] = None
    
    # Zero Storage in Mongo: Resume stored in Google Drive or external link
    resume_google_drive_url: str = Field(..., example="https://drive.google.com/file/d/xyz/view")
    portfolio_or_github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    cover_note: Optional[str] = Field(None, max_length=2000)
    
    # Candidate Auth Info (Google OAuth sub / ID)
    google_oauth_sub: Optional[str] = None


class JobApplicationStatusUpdate(BaseModel):
    status: str = Field(..., example="Under Review")  # "Applied", "Under Review", "Shortlisted", "Interview Scheduled", "Offer", "Rejected"
    hr_internal_notes: Optional[str] = None
    interview_date: Optional[str] = None


class JobApplicationOut(BaseModel):
    id: str
    job_id: str
    job_title: str
    candidate_name: str
    candidate_email: str
    candidate_phone: Optional[str] = None
    resume_google_drive_url: str
    portfolio_or_github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    cover_note: Optional[str] = None
    google_oauth_sub: Optional[str] = None
    status: str = "Applied"
    hr_internal_notes: Optional[str] = None
    interview_date: Optional[str] = None
    applied_at: datetime
    updated_at: Optional[datetime] = None
