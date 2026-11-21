"""
Lead & Contact Submission Models for OpenMNC LLP
Intent-based lead capture, automated categorization, and AI-contextual tracking.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, EmailStr, Field


class LeadCaptureRequest(BaseModel):
    # Form Type & Intent
    lead_type: str = Field("b2b", example="b2b")  # "b2b", "student", "general"
    intent_tag: Optional[str] = None  # e.g., "B2B_AI_AUTOMATION", "B2B_CUSTOM_APP", "STUDENT_FREE_COUNSELING", "INDUSTRIAL_TRAINING_IOT", "SOCIAL_GROWTH"
    service_interest: Optional[str] = None

    # Contact Details
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: Optional[str] = None
    
    # B2B Specific Fields
    company_name: Optional[str] = None
    business_stage: Optional[str] = None  # "Idea Stage", "MVP / Early", "Established Business"
    budget_range: Optional[str] = None  # "< ₹50k", "₹50k - ₹2L", "₹2L - ₹10L", "₹10L+"
    project_timeline: Optional[str] = None  # "Immediate", "Within 1 Month", "Exploratory"
    wants_nda: Optional[bool] = False  # Request mutual NDA before technical discussion

    # Student / EdTech Specific Fields
    education_level: Optional[str] = None  # "12th Pass", "Undergraduate", "Graduate"
    passing_year: Optional[str] = None
    interested_in_college_subsidy: Optional[bool] = False  # eligible for ₹3,000–₹10,000 subsidy
    interested_in_training: Optional[bool] = False  # 3-month advanced IoT / Web / App training
    preferred_field: Optional[str] = None  # "Computer Science", "AI & Robotics", "IoT", "Management"

    # Message & Context
    message: Optional[str] = Field(None, max_length=3000)
    
    # AI & Attribution Context
    referrer_url: Optional[str] = None
    ai_source: Optional[str] = None  # e.g. "chatgpt", "gemini", "claude", "perplexity", "google"
    utm_source: Optional[str] = None
    utm_campaign: Optional[str] = None


class LeadUpdateStatus(BaseModel):
    status: str = Field(..., example="Qualified")  # "New", "Contacted", "Qualified", "In Discussion", "Converted", "Rejected"
    notes: Optional[str] = None
    assigned_to: Optional[str] = None


class LeadOut(BaseModel):
    id: str
    lead_type: str
    intent_tag: str
    category_label: str
    service_interest: Optional[str] = None
    name: str
    email: str
    phone: Optional[str] = None
    company_name: Optional[str] = None
    business_stage: Optional[str] = None
    budget_range: Optional[str] = None
    project_timeline: Optional[str] = None
    education_level: Optional[str] = None
    passing_year: Optional[str] = None
    interested_in_college_subsidy: bool = False
    interested_in_training: bool = False
    wants_nda: bool = False
    preferred_field: Optional[str] = None
    message: Optional[str] = None
    ai_source: Optional[str] = None
    referrer_url: Optional[str] = None
    status: str = "New"
    notes: Optional[str] = None
    submitted_at: datetime
    updated_at: Optional[datetime] = None


# Backward-compatible ContactSubmission alias for existing frontend forms
class ContactSubmission(LeadCaptureRequest):
    pass

class ContactOut(LeadOut):
    pass
