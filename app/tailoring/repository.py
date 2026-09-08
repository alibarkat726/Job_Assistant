from typing import Optional, Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.repository import BaseTenantRepository
from app.core_schema.models import JobApplication, JDRequirement, TailoredCV


class JobApplicationRepository(BaseTenantRepository[JobApplication]):
    """Tenant-scoped repository for JobApplication with eager loading of children."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(JobApplication, db, tenant_id)

    async def get_with_children(self, app_id: uuid.UUID) -> Optional[JobApplication]:
        """Fetch application with eagerly loaded requirements and tailored_cv."""
        await self._set_rls_context()
        stmt = (
            select(JobApplication)
            .filter(JobApplication.id == app_id, JobApplication.user_id == self.tenant_id)
            .options(
                selectinload(JobApplication.requirements),
                selectinload(JobApplication.tailored_cv),
            )
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_all_with_children(self) -> Sequence[JobApplication]:
        """Fetch all applications for the user with eager loading."""
        await self._set_rls_context()
        stmt = (
            select(JobApplication)
            .filter(JobApplication.user_id == self.tenant_id)
            .options(
                selectinload(JobApplication.requirements),
                selectinload(JobApplication.tailored_cv),
            )
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()


class TailoredCVRepository(BaseTenantRepository[TailoredCV]):
    """Tenant-scoped repository for TailoredCV."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(TailoredCV, db, tenant_id)

    async def get_by_application_id(self, app_id: uuid.UUID) -> Optional[TailoredCV]:
        """Fetch the tailored CV associated with a job application."""
        await self._set_rls_context()
        stmt = (
            select(TailoredCV)
            .filter(
                TailoredCV.job_application_id == app_id,
                TailoredCV.user_id == self.tenant_id,
            )
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
