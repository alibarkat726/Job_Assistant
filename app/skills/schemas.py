from datetime import datetime
from typing import List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


# Valid source values — extensible when Module 4 (learning) and CV import are added
SkillSource = Literal["manual", "cv_import", "learning"]


class SkillCreate(BaseModel):
    """Request schema for creating a new profile skill."""

    name: str = Field(..., min_length=1, max_length=255, description="Display skill name, e.g. 'React.js'")
    category: Optional[str] = Field(None, max_length=100, description="Optional category: language, framework, tool, soft-skill, etc.")
    proficiency: int = Field(default=3, ge=1, le=5, description="Self-assessed proficiency 1 (novice) to 5 (expert)")
    source: SkillSource = Field(default="manual", description="How the skill was added")

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Skill name cannot be blank.")
        return stripped


class SkillUpdate(BaseModel):
    """Request schema for updating an existing skill — all fields optional (PATCH semantics)."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    proficiency: Optional[int] = Field(None, ge=1, le=5)
    source: Optional[SkillSource] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Skill name cannot be blank.")
            return stripped
        return v


class SkillResponse(BaseModel):
    """Full skill response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    name_slug: str
    category: Optional[str] = None
    proficiency: int
    source: str
    created_at: datetime
    updated_at: datetime
