import uuid
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db.repository import BaseTenantRepository
from app.core_schema.models import CoverLetter


class CoverLetterRepository(BaseTenantRepository[CoverLetter]):
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(CoverLetter, db, tenant_id)

    async def get_by_application_id(self, application_id: uuid.UUID) -> Optional[CoverLetter]:
        await self._set_rls_context()
        stmt = select(CoverLetter).filter(
            CoverLetter.job_application_id == application_id,
            CoverLetter.user_id == self.tenant_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_by_application_id(self, application_id: uuid.UUID) -> None:
        await self._set_rls_context()
        stmt = delete(CoverLetter).filter(
            CoverLetter.job_application_id == application_id,
            CoverLetter.user_id == self.tenant_id
        )
        await self.db.execute(stmt)
        await self.db.flush()
