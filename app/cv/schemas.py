from datetime import datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, EmailStr


class ContactInfoSchema(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None


class WorkHistorySchema(BaseModel):
    id: Optional[uuid.UUID] = None
    company: str
    role: str
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    description: Optional[str] = None


class EducationSchema(BaseModel):
    id: Optional[uuid.UUID] = None
    institution: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class CVSkillSchema(BaseModel):
    id: Optional[uuid.UUID] = None
    name: str
    category: Optional[str] = None


class StructuredCVSchema(BaseModel):
    contact_info: ContactInfoSchema
    work_history: List[WorkHistorySchema] = Field(default_factory=list)
    education: List[EducationSchema] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    parse_confidence: str = Field(default="high", description="high, medium, or low")
    parsing_notes: List[str] = Field(default_factory=list)


class CVUpdateRequest(BaseModel):
    title: Optional[str] = None
    variant_name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    work_history: Optional[List[WorkHistorySchema]] = None
    education: Optional[List[EducationSchema]] = None
    skills: Optional[List[str]] = None


class CVResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    variant_name: str
    job_id: Optional[uuid.UUID] = None
    is_canonical: bool
    raw_file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    parse_confidence: str
    work_histories: List[WorkHistorySchema] = Field(default_factory=list)
    education_entries: List[EducationSchema] = Field(default_factory=list)
    skills: List[CVSkillSchema] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CVUploadResponse(BaseModel):
    cv_id: uuid.UUID
    message: str
    is_canonical: bool
    parse_confidence: str
    parsing_notes: List[str] = Field(default_factory=list)
    parsed_data: StructuredCVSchema
