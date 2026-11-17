"""
Pydantic v2 models for Services with AEO (AI Engine Optimization) fields.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SubService(BaseModel):
    slug: str
    title: str
    tagline: Optional[str] = None
    problem_statement: Optional[str] = None
    technical_solution: Optional[str] = None
    expected_outcome: Optional[str] = None
    features: Optional[List[str]] = None


class ServiceFAQ(BaseModel):
    question: str
    answer: str


class ServiceBase(BaseModel):
    slug: str
    title: str
    tagline: str
    description: str
    icon: str
    features: List[str]
    category: Optional[str] = "B2B Enterprise"  # "B2B Enterprise" or "B2C Academy"
    
    # AEO (AI Engine Optimization) Fields for ChatGPT, Gemini, Grok, Perplexity
    problem_statement: Optional[str] = None
    technical_solution: Optional[str] = None
    expected_outcome: Optional[str] = None
    
    # Dynamic FAQs & Sub-services for Deep Linking & Rich Snippets
    faqs: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    sub_services: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    
    order: int
    is_active: bool = True


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    slug: Optional[str] = None
    title: Optional[str] = None
    tagline: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    features: Optional[List[str]] = None
    category: Optional[str] = None
    problem_statement: Optional[str] = None
    technical_solution: Optional[str] = None
    expected_outcome: Optional[str] = None
    faqs: Optional[List[Dict[str, str]]] = None
    sub_services: Optional[List[Dict[str, Any]]] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None


class ServiceOut(ServiceBase):
    id: str
    updated_at: datetime

    model_config = {"from_attributes": True}
