from typing import List, Optional, Sequence
import uuid
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.repository import BaseTenantRepository
from app.core_schema.models import Project, ProjectSkill, Skill


class ProjectRepository(BaseTenantRepository[Project]):
    """Tenant-scoped repository for user projects."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(Project, db, tenant_id)

    async def get_with_skills(self, project_id: uuid.UUID) -> Optional[Project]:
        """Fetch project with eagerly loaded skills for the current tenant."""
        await self._set_rls_context()
        stmt = (
            select(Project)
            .filter(Project.id == project_id, Project.user_id == self.tenant_id)
            .options(
                selectinload(Project.project_skills).selectinload(ProjectSkill.skill)
            )
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_all_with_skills(self, limit: int = 100, offset: int = 0) -> Sequence[Project]:
        """Fetch all projects with eagerly loaded skills for the current tenant."""
        await self._set_rls_context()
        stmt = (
            select(Project)
            .filter(Project.user_id == self.tenant_id)
            .options(
                selectinload(Project.project_skills).selectinload(ProjectSkill.skill)
            )
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_project_skill_link(
        self, project_id: uuid.UUID, skill_id: uuid.UUID
    ) -> Optional[ProjectSkill]:
        """Check whether a skill is already attached to a project for this tenant."""
        await self._set_rls_context()
        stmt = select(ProjectSkill).filter(
            ProjectSkill.project_id == project_id,
            ProjectSkill.skill_id == skill_id,
            ProjectSkill.user_id == self.tenant_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def add_skill(self, project_id: uuid.UUID, skill_id: uuid.UUID) -> ProjectSkill:
        """Attach a skill to a project. Caller must check for duplicates first."""
        await self._set_rls_context()
        link = ProjectSkill(
            project_id=project_id,
            skill_id=skill_id,
            user_id=self.tenant_id,
        )
        self.db.add(link)
        await self.db.flush()
        return link

    async def remove_skill(self, project_id: uuid.UUID, skill_id: uuid.UUID) -> None:
        """Detach a skill from a project."""
        await self._set_rls_context()
        stmt = delete(ProjectSkill).where(
            ProjectSkill.project_id == project_id,
            ProjectSkill.skill_id == skill_id,
            ProjectSkill.user_id == self.tenant_id,
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def get_project_skills(self, project_id: uuid.UUID) -> List[Skill]:
        """List skills attached to a specific project for the current tenant."""
        await self._set_rls_context()
        stmt = (
            select(Skill)
            .join(ProjectSkill, ProjectSkill.skill_id == Skill.id)
            .filter(
                ProjectSkill.project_id == project_id,
                ProjectSkill.user_id == self.tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
