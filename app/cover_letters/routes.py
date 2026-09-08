import uuid
from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
import bleach

from app.shared.db.session import get_db
from app.users.models import User
from app.auth.dependencies import get_current_user
from app.cover_letters.repository import CoverLetterRepository
from app.cover_letters.cover_letter_agent import HeuristicCoverLetterAgent
from app.cover_letters.services import CoverLetterService
from app.cover_letters.schemas import (
    CoverLetterGenerateRequest,
    CoverLetterEditRequest,
    CoverLetterResponse
)
from app.tailoring.repository import JobApplicationRepository
from app.skills.repository import SkillRepository
from app.projects.repository import ProjectRepository
from app.cv.repository import CVRepository

router = APIRouter(prefix="/api/v1/applications", tags=["Cover Letters"])


async def get_cover_letter_service(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CoverLetterService:
    return CoverLetterService(
        cl_repo=CoverLetterRepository(db=db, tenant_id=current_user.id),
        app_repo=JobApplicationRepository(db=db, tenant_id=current_user.id),
        cv_repo=CVRepository(db=db, tenant_id=current_user.id),
        skill_repo=SkillRepository(db=db, tenant_id=current_user.id),
        project_repo=ProjectRepository(db=db, tenant_id=current_user.id),
        agent=HeuristicCoverLetterAgent()
    )


@router.post("/{app_id}/cover-letter", response_model=CoverLetterResponse, status_code=status.HTTP_201_CREATED)
async def generate_cover_letter(
    app_id: uuid.UUID,
    dto: CoverLetterGenerateRequest,
    svc: CoverLetterService = Depends(get_cover_letter_service)
):
    """Generate a targeted cover letter draft for the job application."""
    return await svc.generate_cover_letter(app_id, dto)


@router.get("/{app_id}/cover-letter", response_model=CoverLetterResponse)
async def get_cover_letter(
    app_id: uuid.UUID,
    svc: CoverLetterService = Depends(get_cover_letter_service)
):
    """Get the current cover letter draft or finalized version."""
    return await svc.get_cover_letter(app_id)


@router.put("/{app_id}/cover-letter", response_model=CoverLetterResponse)
async def edit_cover_letter(
    app_id: uuid.UUID,
    dto: CoverLetterEditRequest,
    svc: CoverLetterService = Depends(get_cover_letter_service)
):
    """Edit the cover letter content inline before finalizing."""
    dto.content = bleach.clean(dto.content, strip=True)
    return await svc.edit_cover_letter(app_id, dto)


@router.post("/{app_id}/cover-letter/finalize", response_model=CoverLetterResponse)
async def finalize_cover_letter(
    app_id: uuid.UUID,
    svc: CoverLetterService = Depends(get_cover_letter_service)
):
    """Finalize the cover letter to lock it from edits."""
    return await svc.finalize_cover_letter(app_id)


@router.get("/{app_id}/cover-letter/export", response_class=PlainTextResponse)
async def export_cover_letter(
    app_id: uuid.UUID,
    svc: CoverLetterService = Depends(get_cover_letter_service)
):
    """Export the cover letter as a raw plain text file."""
    content = await svc.export_cover_letter(app_id)
    headers = {"Content-Disposition": f'attachment; filename="cover_letter_{app_id}.txt"'}
    return PlainTextResponse(content=content, headers=headers)
