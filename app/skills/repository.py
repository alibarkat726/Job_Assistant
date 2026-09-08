from typing import Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.repository import BaseTenantRepository
from app.core_schema.models import Skill


class SkillRepository(BaseTenantRepository[Skill]):
    """Tenant-scoped repository for canonical profile skills."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(Skill, db, tenant_id)

    async def get_by_slug(self, name_slug: str) -> Optional[Skill]:
        """Fetch a skill by its normalized slug for the current tenant."""
        await self._set_rls_context()
        stmt = (
            select(Skill)
            .filter(Skill.user_id == self.tenant_id)
            .filter(Skill.name_slug == name_slug)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
