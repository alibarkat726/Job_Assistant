import uuid
from typing import List
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.session import get_db
from app.users.models import User
from app.auth.dependencies import get_current_user
from app.skills.repository import SkillRepository
from app.skills.services import SkillsService
from app.skills.schemas import SkillCreate, SkillUpdate, SkillResponse

router = APIRouter(prefix="/api/v1/skills", tags=["Skills"])


async def get_skills_service(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillsService:
    """Dependency: tenant-scoped SkillsService."""
    repo = SkillRepository(db=db, tenant_id=current_user.id)
    return SkillsService(skill_repo=repo)


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    dto: SkillCreate,
    skills_service: SkillsService = Depends(get_skills_service),
):
    """Create a new profile skill. Returns 409 if a skill with the same name already exists."""
    return await skills_service.create_skill(dto)


@router.get("", response_model=List[SkillResponse])
async def list_skills(
    skills_service: SkillsService = Depends(get_skills_service),
):
    """List all profile skills for the authenticated user."""
    return await skills_service.list_skills()


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: uuid.UUID,
    skills_service: SkillsService = Depends(get_skills_service),
):
    """Fetch a single profile skill by ID."""
    return await skills_service.get_skill(skill_id)


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: uuid.UUID,
    dto: SkillUpdate,
    skills_service: SkillsService = Depends(get_skills_service),
):
    """Update skill fields. Provide only the fields you want to change."""
    return await skills_service.update_skill(skill_id, dto)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: uuid.UUID,
    skills_service: SkillsService = Depends(get_skills_service),
):
    """Delete a profile skill."""
    await skills_service.delete_skill(skill_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
