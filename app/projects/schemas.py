from datetime import datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.skills.schemas import SkillResponse


class ProjectUrlSchema(BaseModel):
    """A single project URL with an optional human-readable label."""

    label: Optional[str] = Field(None, max_length=100, description="e.g. 'GitHub', 'Live Demo', 'Case Study'")
    url: str = Field(..., description="Valid HTTP/HTTPS URL")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        # Basic URL validation — must start with http:// or https://
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        if len(v) > 2048:
            raise ValueError("URL must not exceed 2048 characters.")
        return v


class ProjectCreate(BaseModel):
    """Request schema for creating a project."""

    title: str = Field(..., min_length=1, max_length=255, description="Project title")
    description: Optional[str] = Field(None, max_length=5000, description="Project description")
    urls: List[ProjectUrlSchema] = Field(
        default_factory=list,
        max_length=10,
        description="Up to 10 project URLs (repo, live demo, case study, etc.)",
    )
    start_date: Optional[str] = Field(None, max_length=100, description="Project start date (free-form string)")
    end_date: Optional[str] = Field(None, max_length=100, description="Project end date (free-form string)")
    is_ongoing: bool = Field(default=False, description="Whether the project is currently active")

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Project title cannot be blank.")
        return stripped


class ProjectUpdate(BaseModel):
    """Request schema for updating a project — all fields optional (PATCH semantics)."""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    urls: Optional[List[ProjectUrlSchema]] = Field(None, max_length=10)
    start_date: Optional[str] = Field(None, max_length=100)
    end_date: Optional[str] = Field(None, max_length=100)
    is_ongoing: Optional[bool] = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Project title cannot be blank.")
            return stripped
        return v


class ProjectSkillBriefResponse(BaseModel):
    """Brief skill info for embedding inside a project response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    name_slug: str
    category: Optional[str] = None
    proficiency: int


class ProjectResponse(BaseModel):
    """Full project response with embedded skills."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: Optional[str] = None
    urls: List[ProjectUrlSchema] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_ongoing: bool
    skills: List[ProjectSkillBriefResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
