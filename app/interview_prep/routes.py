import uuid
import bleach
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db.session import get_db
from app.users.models import User
from app.auth.dependencies import get_current_user
from app.interview_prep.repository import InterviewPrepRepository
from app.interview_prep.prep_agent import HeuristicInterviewPrepAgent
from app.interview_prep.services import InterviewPrepService
from app.interview_prep.schemas import InterviewPrepSetResponse, InterviewQuestionUpdate, InterviewQuestionResponse
from app.tailoring.repository import JobApplicationRepository
from app.skills.repository import SkillRepository
from app.projects.repository import ProjectRepository

router = APIRouter(prefix="/api/v1/applications", tags=["Interview Prep"])


async def get_interview_prep_service(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewPrepService:
    """Dependency for tenant-scoped InterviewPrepService."""
    return InterviewPrepService(
        prep_repo=InterviewPrepRepository(db=db, tenant_id=current_user.id),
        app_repo=JobApplicationRepository(db=db, tenant_id=current_user.id),
        skill_repo=SkillRepository(db=db, tenant_id=current_user.id),
        project_repo=ProjectRepository(db=db, tenant_id=current_user.id),
        agent=HeuristicInterviewPrepAgent(),
    )


@router.post("/{app_id}/interview-prep", response_model=InterviewPrepSetResponse, status_code=status.HTTP_201_CREATED)
async def generate_interview_prep(
    app_id: uuid.UUID,
    svc: InterviewPrepService = Depends(get_interview_prep_service),
):
    """
    Generate or regenerate interview preparation questions for this job application.
    Grounded in the matched skills and projects for the application.
    Regenerating will delete the old prep set and its notes!
    """
    return await svc.generate_prep_set(app_id)


@router.get("/{app_id}/interview-prep", response_model=InterviewPrepSetResponse)
async def get_interview_prep(
    app_id: uuid.UUID,
    svc: InterviewPrepService = Depends(get_interview_prep_service),
):
    """
    Retrieve the generated interview prep set for this job application.
    """
    return await svc.get_prep_set(app_id)


@router.put("/{app_id}/interview-prep/questions/{question_id}", response_model=InterviewQuestionResponse)
async def update_interview_question(
    app_id: uuid.UUID,
    question_id: uuid.UUID,
    dto: InterviewQuestionUpdate,
    svc: InterviewPrepService = Depends(get_interview_prep_service),
):
    """
    Update a specific interview question (e.g. adding user notes, toggling practice status).
    """
    if dto.user_notes:
        dto.user_notes = bleach.clean(dto.user_notes, strip=True)
    return await svc.update_question(question_id, dto)
