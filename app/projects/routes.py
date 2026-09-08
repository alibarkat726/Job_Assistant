import uuid
from typing import List
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.session import get_db
from app.users.models import User
from app.auth.dependencies import get_current_user
from app.projects.repository import ProjectRepository
from app.skills.repository import SkillRepository
from app.projects.services import ProjectsService
from app.projects.schemas import ProjectCreate, ProjectUpdate, ProjectResponse
from app.skills.schemas import SkillResponse

router = APIRouter(prefix="/api/v1/projects", tags=["Projects"])


async def get_projects_service(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectsService:
    """Dependency: tenant-scoped ProjectsService."""
    project_repo = ProjectRepository(db=db, tenant_id=current_user.id)
    skill_repo = SkillRepository(db=db, tenant_id=current_user.id)
    return ProjectsService(project_repo=project_repo, skill_repo=skill_repo)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    dto: ProjectCreate,
    projects_service: ProjectsService = Depends(get_projects_service),
):
    """Create a new portfolio project."""
    return await projects_service.create_project(dto)


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    projects_service: ProjectsService = Depends(get_projects_service),
):
    """List all portfolio projects for the authenticated user, with skills embedded."""
    return await projects_service.list_projects()


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    projects_service: ProjectsService = Depends(get_projects_service),
):
    """Get a single project by ID, with skills embedded."""
    return await projects_service.get_project(project_id)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    dto: ProjectUpdate,
    projects_service: ProjectsService = Depends(get_projects_service),
):
    """Update project fields. Only provided fields are changed."""
    return await projects_service.update_project(project_id, dto)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    projects_service: ProjectsService = Depends(get_projects_service),
):
    """Delete a project and its skill associations."""
    await projects_service.delete_project(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/skills", response_model=List[SkillResponse])
async def list_project_skills(
    project_id: uuid.UUID,
    projects_service: ProjectsService = Depends(get_projects_service),
):
    """List all skills attached to a project."""
    return await projects_service.list_project_skills(project_id)


@router.post(
    "/{project_id}/skills/{skill_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
)
async def attach_skill_to_project(
    project_id: uuid.UUID,
    skill_id: uuid.UUID,
    projects_service: ProjectsService = Depends(get_projects_service),
):
    """
    Attach a profile skill to a project (many-to-many).
    Returns 409 if the skill is already attached.
    Returns 404 if the skill or project doesn't belong to the current user.
    """
    return await projects_service.attach_skill(project_id, skill_id)


@router.delete(
    "/{project_id}/skills/{skill_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
)
async def detach_skill_from_project(
    project_id: uuid.UUID,
    skill_id: uuid.UUID,
    projects_service: ProjectsService = Depends(get_projects_service),
):
    """
    Detach a skill from a project.
    Returns 404 if the project doesn't belong to the current user or the skill is not attached.
    """
    return await projects_service.detach_skill(project_id, skill_id)
