"""
Blog Pydantic Models for OpenMNC LLP
Optimized for AI recommendation engines (ChatGPT, Gemini, Claude, Perplexity)
and Google SEO / JSON-LD Article schema.
"""

from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field


class BlogBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=200, example="How Visionary Founders Turn App Ideas into Scalable Realities")
    slug: str = Field(..., min_length=3, max_length=200, example="turn-app-idea-into-reality")
    category: str = Field(..., example="B2B & Tech Solutions")  # "Student Guidance", "B2B & Tech Solutions", "AI Automation", "Industrial Training"
    target_audience: str = Field("Founders & Solopreneurs", example="Founders & Solopreneurs")  # "12th-Pass Students", "Business Owners", etc.
    excerpt: str = Field(..., max_length=400, example="Step-by-step blueprint on requirement analysis, prototyping, ASO, and marketing.")
    content: str = Field(..., example="Full markdown/html content of the article...")
    cover_image: Optional[str] = Field("https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=1200&q=80")
    author_name: str = Field("Amit Barai", example="Amit Barai")
    author_role: str = Field("Founder & Director, OpenMNC LLP", example="Founder & Director, OpenMNC LLP")
    tags: List[str] = Field(default_factory=list, example=["App Development", "ASO", "Startup Guide"])
    target_service_slug: str = Field("custom-development", example="custom-development")  # Used for auto-routing CTAs!
    cta_headline: Optional[str] = Field("Have an app or software idea?", example="Have an app or software idea?")
    cta_button_text: Optional[str] = Field("Build Your Idea With OpenMNC →", example="Build Your Idea With OpenMNC →")
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    is_published: bool = Field(True)


class BlogCreate(BlogBase):
    pass


class BlogUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    category: Optional[str] = None
    target_audience: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    cover_image: Optional[str] = None
    author_name: Optional[str] = None
    author_role: Optional[str] = None
    tags: Optional[List[str]] = None
    target_service_slug: Optional[str] = None
    cta_headline: Optional[str] = None
    cta_button_text: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    is_published: Optional[bool] = None


class BlogOut(BlogBase):
    id: str
    views_count: int = 0
    created_at: datetime
    updated_at: datetime
