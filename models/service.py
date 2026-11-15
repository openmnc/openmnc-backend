"""
Pydantic v2 models for Services.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ServiceBase(BaseModel):
    slug: str
    title: str
    tagline: str
    description: str
    icon: str
    features: list[str]
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
    features: Optional[list[str]] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None


class ServiceOut(ServiceBase):
    id: str
    updated_at: datetime

    model_config = {"from_attributes": True}
