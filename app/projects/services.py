import logging
from typing import List
import uuid
from app.shared.middleware.error_handler import NotFoundError, AppException
from app.core_schema.models import Project, Skill
from app.projects.repository import ProjectRepository
from app.skills.repository import SkillRepository
from app.projects.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectUrlSchema,
    ProjectSkillBriefResponse,
)
from app.skills.schemas import SkillResponse

logger = logging.getLogger(__name__)


class ProjectsService:
    """
    Service layer for portfolio project CRUD and skill attachment management.
    All operations are tenant-scoped via injected repositories.
    """

    def __init__(
        self,
        project_repo: ProjectRepository,
        skill_repo: SkillRepository,
    ):
        self.project_repo = project_repo
        self.skill_repo = skill_repo

    async def create_project(self, dto: ProjectCreate) -> ProjectResponse:
        """Create a new portfolio project."""
        project = Project(
            title=dto.title.strip(),
            description=dto.description,
            urls=[u.model_dump() for u in dto.urls],
            start_date=dto.start_date,
            end_date=dto.end_date,
            is_ongoing=dto.is_ongoing,
        )
        created = await self.project_repo.create(project)
        return self._map_to_response(created)

    async def get_project(self, project_id: uuid.UUID) -> ProjectResponse:
        """Fetch a single project with its skills. Raises 404 if not found."""
        project = await self.project_repo.get_with_skills(project_id)
        if not project:
            raise NotFoundError(f"Project with ID '{project_id}' not found.")
        return self._map_to_response(project)

    async def list_projects(self) -> List[ProjectResponse]:
        """List all projects for the current tenant, with skills embedded."""
        projects = await self.project_repo.find_all_with_skills()
        return [self._map_to_response(p) for p in projects]

    async def update_project(self, project_id: uuid.UUID, dto: ProjectUpdate) -> ProjectResponse:
        """Update project fields. Only provided fields are updated."""
        project = await self.project_repo.get_with_skills(project_id)
        if not project:
            raise NotFoundError(f"Project with ID '{project_id}' not found.")

        if dto.title is not None:
            project.title = dto.title.strip()
        if dto.description is not None:
            project.description = dto.description or None
        if dto.urls is not None:
            project.urls = [u.model_dump() for u in dto.urls]
        if dto.start_date is not None:
            project.start_date = dto.start_date or None
        if dto.end_date is not None:
            project.end_date = dto.end_date or None
        if dto.is_ongoing is not None:
            project.is_ongoing = dto.is_ongoing

        updated = await self.project_repo.update(project)
        # Re-fetch with skills for full response
        refreshed = await self.project_repo.get_with_skills(updated.id)
        return self._map_to_response(refreshed)

    async def delete_project(self, project_id: uuid.UUID) -> None:
        """Delete a project and its skill associations. Raises 404 if not found."""
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundError(f"Project with ID '{project_id}' not found.")
        await self.project_repo.delete(project)

    async def attach_skill(self, project_id: uuid.UUID, skill_id: uuid.UUID) -> ProjectResponse:
        """
        Attach a profile skill to a project.

        - Raises 404 if the project or skill doesn't belong to the current tenant.
        - Raises 409 if the skill is already attached to the project.
        """
        project = await self.project_repo.get_with_skills(project_id)
        if not project:
            raise NotFoundError(f"Project with ID '{project_id}' not found.")

        skill = await self.skill_repo.get_by_id(skill_id)
        if not skill:
            raise NotFoundError(
                f"Skill with ID '{skill_id}' not found. Only skills in your profile can be attached."
            )

        existing_link = await self.project_repo.get_project_skill_link(project_id, skill_id)
        if existing_link:
            raise AppException(
                message=f"Skill '{skill.name}' is already attached to this project.",
                code="SKILL_ALREADY_ATTACHED",
                status_code=409,
            )

        await self.project_repo.add_skill(project_id, skill_id)
        refreshed = await self.project_repo.get_with_skills(project_id)
        return self._map_to_response(refreshed)

    async def detach_skill(self, project_id: uuid.UUID, skill_id: uuid.UUID) -> ProjectResponse:
        """
        Detach a skill from a project.

        - Raises 404 if project doesn't belong to tenant.
        - Raises 404 if skill is not currently attached.
        """
        project = await self.project_repo.get_with_skills(project_id)
        if not project:
            raise NotFoundError(f"Project with ID '{project_id}' not found.")

        existing_link = await self.project_repo.get_project_skill_link(project_id, skill_id)
        if not existing_link:
            raise NotFoundError(
                f"Skill with ID '{skill_id}' is not attached to this project."
            )

        await self.project_repo.remove_skill(project_id, skill_id)
        refreshed = await self.project_repo.get_with_skills(project_id)
        return self._map_to_response(refreshed)

    async def list_project_skills(self, project_id: uuid.UUID) -> List[SkillResponse]:
        """
        List all skills attached to a project.
        Raises 404 if the project doesn't belong to the current tenant.
        """
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundError(f"Project with ID '{project_id}' not found.")

        skills = await self.project_repo.get_project_skills(project_id)
        return [
            SkillResponse(
                id=s.id,
                user_id=s.user_id,
                name=s.name,
                name_slug=s.name_slug,
                category=s.category,
                proficiency=s.proficiency,
                source=s.source,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in skills
        ]

    def _map_to_response(self, project: Project) -> ProjectResponse:
        """Map a Project ORM model to the full response schema."""
        skills: List[ProjectSkillBriefResponse] = []
        if project.project_skills:
            for ps in project.project_skills:
                if ps.skill:
                    skills.append(
                        ProjectSkillBriefResponse(
                            id=ps.skill.id,
                            name=ps.skill.name,
                            name_slug=ps.skill.name_slug,
                            category=ps.skill.category,
                            proficiency=ps.skill.proficiency,
                        )
                    )

        # Deserialize JSONB urls list to Pydantic objects
        raw_urls = project.urls or []
        url_schemas = [ProjectUrlSchema(**u) if isinstance(u, dict) else u for u in raw_urls]

        return ProjectResponse(
            id=project.id,
            user_id=project.user_id,
            title=project.title,
            description=project.description,
            urls=url_schemas,
            start_date=project.start_date,
            end_date=project.end_date,
            is_ongoing=project.is_ongoing,
            skills=skills,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
