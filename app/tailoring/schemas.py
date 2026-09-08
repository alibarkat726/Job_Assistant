from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator, HttpUrl


# ------------------------------------------------------------------ #
# Job Application Schemas
# ------------------------------------------------------------------ #

ApplicationStatus = Literal["draft", "tailored", "applied"]
ParseStatus = Literal["pending_parse", "parsed", "needs_manual_review"]


class JobApplicationCreate(BaseModel):
    """Request schema for submitting a new job description."""
    job_title: str = Field(..., max_length=255, min_length=1)
    company: Optional[str] = Field(None, max_length=255)
    jd_raw_text: str = Field(..., min_length=20, max_length=50000, description="Full text of the job description")
    source_url: Optional[str] = Field(None, max_length=2048, description="Optional URL of the job posting — for user reference only, never fetched")

    @field_validator("jd_raw_text")
    @classmethod
    def strip_jd_text(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Job description text cannot be blank.")
        return stripped


class JobApplicationStatusUpdate(BaseModel):
    """Allows user to manually flip status to 'applied'."""
    status: ApplicationStatus


class JDRequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    skill_name: str
    skill_slug: str
    is_required: bool
    seniority: Optional[str] = None


class JobApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    job_title: str
    company: Optional[str] = None
    source_url: Optional[str] = None
    status: ApplicationStatus
    parse_status: ParseStatus
    requirements: List[JDRequirementResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ #
# JD Parsing Internal Schemas
# ------------------------------------------------------------------ #

class StructuredJDRequirement(BaseModel):
    """A single requirement extracted from the JD."""
    skill_name: str
    is_required: bool = True
    seniority: Optional[str] = None


class StructuredJDSchema(BaseModel):
    """Full structured output from the JD Parser."""
    required_skills: List[StructuredJDRequirement] = Field(default_factory=list)
    key_responsibilities: List[str] = Field(default_factory=list)
    seniority_level: Optional[str] = None


# ------------------------------------------------------------------ #
# Matching Schemas
# ------------------------------------------------------------------ #

MatchStatus = Literal["matched", "partial", "missing"]


class SkillMatchResult(BaseModel):
    """Result of matching a single JD requirement against user's skill graph."""
    jd_skill_name: str
    jd_skill_slug: str
    match_status: MatchStatus
    matched_skill_id: Optional[uuid.UUID] = None
    matched_skill_name: Optional[str] = None
    user_proficiency: Optional[int] = None  # 1-5, None if missing
    is_required: bool


class ProjectRelevanceResult(BaseModel):
    """Relevance score of a user project against a parsed JD."""
    project_id: uuid.UUID
    project_title: str
    matched_skill_count: int
    total_jd_skills: int
    relevance_score: float  # 0.0 - 1.0
    matched_skill_names: List[str] = Field(default_factory=list)


class MatchingReport(BaseModel):
    """Full matching report linking JD requirements to user's profile."""
    skill_matches: List[SkillMatchResult] = Field(default_factory=list)
    project_rankings: List[ProjectRelevanceResult] = Field(default_factory=list)
    overall_match_score: float  # 0.0 - 1.0, based on required skills only
    missing_required_count: int
    matched_required_count: int


# ------------------------------------------------------------------ #
# Tailored CV Schemas
# ------------------------------------------------------------------ #

TailoredCVStatus = Literal["draft", "finalized"]


class TailoredCVDraft(BaseModel):
    """Internal model produced by the Tailoring Agent (before DB persistence)."""
    tailored_summary: Optional[str] = None
    tailored_work_history: List[Dict[str, Any]] = Field(default_factory=list)
    selected_project_ids: List[uuid.UUID] = Field(default_factory=list)
    diff_summary: str = ""


class TailoredCVEditRequest(BaseModel):
    """User edits to the tailored CV draft."""
    tailored_content: Optional[str] = None
    selected_project_ids: Optional[List[uuid.UUID]] = None


class TailoredCVResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_application_id: uuid.UUID
    source_cv_id: Optional[uuid.UUID] = None
    tailored_content: Optional[str] = None
    diff_summary: Optional[str] = None
    status: TailoredCVStatus
    selected_project_ids: Optional[list] = None
    created_at: datetime
    updated_at: datetime
