import uuid
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

# ------------------------------------------------------------------ #
# Application List/Summary
# ------------------------------------------------------------------ #

class DashboardApplicationSummary(BaseModel):
    id: uuid.UUID
    job_title: str
    company: Optional[str]
    status: str
    parse_status: str
    matched_skills_count: int
    required_skills_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DashboardApplicationListResponse(BaseModel):
    items: List[DashboardApplicationSummary]


# ------------------------------------------------------------------ #
# Application Detail Aggregation
# ------------------------------------------------------------------ #

class DashboardSkillMatch(BaseModel):
    jd_skill_name: str
    jd_skill_slug: str
    match_status: str
    is_required: bool

    class Config:
        from_attributes = True

# We can reuse schemas from other modules for the detail endpoint,
# but we will wrap them in a large aggregate response.
from app.tailoring.schemas import JobApplicationResponse, TailoredCVResponse
from app.interview_prep.schemas import InterviewPrepSetResponse

class DashboardApplicationDetailResponse(BaseModel):
    application: JobApplicationResponse
    skill_matches: List[DashboardSkillMatch]
    tailored_cv: Optional[TailoredCVResponse]
    interview_prep: Optional[InterviewPrepSetResponse]


# ------------------------------------------------------------------ #
# Analytics
# ------------------------------------------------------------------ #

class SkillFrequency(BaseModel):
    skill_slug: str
    skill_name: str
    frequency_count: int


class SkillGapAnalyticsResponse(BaseModel):
    top_missing_skills: List[SkillFrequency]
    top_matched_skills: List[SkillFrequency]
    learning_nudge: Optional[str] = None
