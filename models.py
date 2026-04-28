from pydantic import BaseModel, field_validator
import re
from typing import Optional


class LeadInput(BaseModel):
    name: Optional[str] = None
    contact: str  # Обязательное поле
    source: Optional[str] = None
    comment: Optional[str] = None

    @field_validator('contact')
    @classmethod
    def validate_contact(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Поле contact не может быть пустым')
        return v.strip()


class LeadResponse(BaseModel):
    status: str
    message: str
    id: int
    contact: str


class LeadData(BaseModel):
    id: int
    created_at: str
    name: Optional[str] = None
    contact: str
    source: Optional[str] = None
    comment: Optional[str] = None


class LeadListResponse(BaseModel):
    status: str
    total: int
    leads: list[LeadData]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str