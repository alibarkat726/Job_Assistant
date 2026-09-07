import uuid
from typing import List
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
import bleach
from app.shared.db.session import get_db
from app.users.models import User
from app.auth.dependencies import get_current_user
from app.cv.repository import CVRepository
from app.skills.repository import SkillRepository
from app.projects.repository import ProjectRepository
from app.tailoring.repository import JobApplicationRepository, TailoredCVRepository
from app.tailoring.services import TailoringService
from app.tailoring.jd_parser import HeuristicJDParser
from app.tailoring.tailoring_agent import HeuristicTailoringAgent
from app.tailoring.schemas import (
    JobApplicationCreate,
    JobApplicationStatusUpdate,
    JobApplicationResponse,
    TailoredCVEditRequest,
    TailoredCVResponse,
    MatchingReport,
)

router = APIRouter(prefix="/api/v1/applications", tags=["Job Applications & CV Tailoring"])


async def get_tailoring_service(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TailoringService:
    """Dependency: tenant-scoped TailoringService."""
    return TailoringService(
        app_repo=JobApplicationRepository(db=db, tenant_id=current_user.id),
        tailored_cv_repo=TailoredCVRepository(db=db, tenant_id=current_user.id),
        cv_repo=CVRepository(db=db, tenant_id=current_user.id),
        skill_repo=SkillRepository(db=db, tenant_id=current_user.id),
        project_repo=ProjectRepository(db=db, tenant_id=current_user.id),
        jd_parser=HeuristicJDParser(),
        tailoring_agent=HeuristicTailoringAgent(),
    )


# ------------------------------------------------------------------ #
# Job Application Routes
# ------------------------------------------------------------------ #

@router.post("", response_model=JobApplicationResponse, status_code=status.HTTP_201_CREATED)
async def submit_job_description(
    dto: JobApplicationCreate,
    svc: TailoringService = Depends(get_tailoring_service),
):
    """
    Submit a pasted job description. The system parses it, extracts required skills,
    and stores the record as a draft job application for the user.
    """
    dto.jd_raw_text = bleach.clean(dto.jd_raw_text, strip=True)
    dto.job_title = bleach.clean(dto.job_title, strip=True)
    if dto.company:
        dto.company = bleach.clean(dto.company, strip=True)
    return await svc.submit_job_description(dto)


@router.get("", response_model=List[JobApplicationResponse])
async def list_applications(
    svc: TailoringService = Depends(get_tailoring_service),
):
    """List all job applications for the current user."""
    return await svc.list_applications()


@router.get("/{app_id}", response_model=JobApplicationResponse)
async def get_application(
    app_id: uuid.UUID,
    svc: TailoringService = Depends(get_tailoring_service),
):
    """Get a single job application with its parsed requirements."""
    return await svc.get_application(app_id)


@router.put("/{app_id}/status", response_model=JobApplicationResponse)
async def update_application_status(
    app_id: uuid.UUID,
    dto: JobApplicationStatusUpdate,
    svc: TailoringService = Depends(get_tailoring_service),
):
    """
    Manually flip the application status (draft → tailored → applied).
    The 'applied' status is set by the user once they've submitted externally.
    This system never auto-submits to third-party sites.
    """
    return await svc.update_status(app_id, dto)


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    app_id: uuid.UUID,
    svc: TailoringService = Depends(get_tailoring_service),
):
    """Delete a job application and its associated tailored CV."""
    await svc.delete_application(app_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ #
# Matching Report
# ------------------------------------------------------------------ #

@router.get("/{app_id}/match", response_model=MatchingReport)
async def get_matching_report(
    app_id: uuid.UUID,
    svc: TailoringService = Depends(get_tailoring_service),
):
    """
    Run the matching engine: compares parsed JD requirements against the user's
    skill graph and portfolio projects. Returns a ranked relevance report.
    Scoring is deterministic slug-overlap — no LLM call required.
    """
    return await svc.get_matching_report(app_id)


# ------------------------------------------------------------------ #
# Tailored CV — Draft / Edit / Finalize flow
# ------------------------------------------------------------------ #

@router.post("/{app_id}/tailor", response_model=TailoredCVResponse, status_code=status.HTTP_201_CREATED)
async def generate_tailored_draft(
    app_id: uuid.UUID,
    svc: TailoringService = Depends(get_tailoring_service),
):
    """
    Run the Tailoring Agent to produce a tailored CV draft for this job application.
    Requires the user to have a finalized canonical CV.
    The agent reorders/reweights existing data ONLY — it never invents facts.
    """
    return await svc.generate_tailored_draft(app_id)


@router.get("/{app_id}/tailor", response_model=TailoredCVResponse)
async def get_tailored_cv(
    app_id: uuid.UUID,
    svc: TailoringService = Depends(get_tailoring_service),
):
    """Retrieve the tailored CV draft for a job application."""
    return await svc.get_tailored_cv(app_id)


@router.put("/{app_id}/tailor", response_model=TailoredCVResponse)
async def edit_tailored_draft(
    app_id: uuid.UUID,
    dto: TailoredCVEditRequest,
    svc: TailoringService = Depends(get_tailoring_service),
):
    """Edit the tailored CV draft content or selected projects before finalizing."""
    return await svc.edit_tailored_draft(app_id, dto)


@router.post("/{app_id}/tailor/finalize", response_model=TailoredCVResponse)
async def finalize_tailored_cv(
    app_id: uuid.UUID,
    svc: TailoringService = Depends(get_tailoring_service),
):
    """
    Finalize the tailored CV for this job application.
    The finalized version is permanently linked to the application record,
    providing a history of what was sent for each job.
    """
    return await svc.finalize_tailored_cv(app_id)
