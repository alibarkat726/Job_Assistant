from typing import Optional, Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.repository import BaseTenantRepository
from app.core_schema.models import LearningEntry, LearningProposal, ProposedSkillItem


class LearningEntryRepository(BaseTenantRepository[LearningEntry]):
    """Tenant-scoped repository for LearningEntry."""
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(LearningEntry, db, tenant_id)


class LearningProposalRepository(BaseTenantRepository[LearningProposal]):
    """Tenant-scoped repository for LearningProposal with eager loading for children."""
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(LearningProposal, db, tenant_id)

    async def get_with_items(self, proposal_id: uuid.UUID) -> Optional[LearningProposal]:
        """Fetch proposal with eagerly loaded proposed_skill_items."""
        await self._set_rls_context()
        stmt = (
            select(LearningProposal)
            .filter(LearningProposal.id == proposal_id, LearningProposal.user_id == self.tenant_id)
            .options(selectinload(LearningProposal.proposed_skills))
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_pending_with_items(self) -> Sequence[LearningProposal]:
        """Fetch all pending proposals for the user."""
        await self._set_rls_context()
        stmt = (
            select(LearningProposal)
            .filter(LearningProposal.user_id == self.tenant_id, LearningProposal.status == "pending")
            .options(selectinload(LearningProposal.proposed_skills))
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_by_entry_id(self, entry_id: uuid.UUID) -> Optional[LearningProposal]:
        """Fetch proposal for a given learning entry."""
        await self._set_rls_context()
        stmt = (
            select(LearningProposal)
            .filter(LearningProposal.entry_id == entry_id, LearningProposal.user_id == self.tenant_id)
            .options(selectinload(LearningProposal.proposed_skills))
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
