"""
Pydantic v2 models for Site Settings.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SiteSettingBase(BaseModel):
    key: str
    value: str
    section: str


class SiteSettingUpdate(BaseModel):
    value: str


class SiteSettingOut(BaseModel):
    key: str
    value: str
    section: str
    updated_at: datetime

    model_config = {"from_attributes": True}
