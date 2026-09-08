import uuid
from typing import Optional, List
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db.repository import BaseTenantRepository
from app.core_schema.models import InterviewPrepSet, InterviewQuestion


class InterviewPrepRepository(BaseTenantRepository[InterviewPrepSet]):
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(InterviewPrepSet, db, tenant_id)

    async def get_by_application_id(self, application_id: uuid.UUID) -> Optional[InterviewPrepSet]:
        """Fetch the prep set (and eagerly load questions) for a specific job application."""
        await self._set_rls_context()
        stmt = (
            select(InterviewPrepSet)
            .filter(
                InterviewPrepSet.job_application_id == application_id,
                InterviewPrepSet.user_id == self.tenant_id
            )
            .options(selectinload(InterviewPrepSet.questions))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_question(self, question_id: uuid.UUID) -> Optional[InterviewQuestion]:
        """Fetch a specific question by ID for updating."""
        await self._set_rls_context()
        stmt = select(InterviewQuestion).filter(
            InterviewQuestion.id == question_id,
            InterviewQuestion.user_id == self.tenant_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_question(self, question: InterviewQuestion) -> InterviewQuestion:
        """Update an existing question."""
        await self._set_rls_context()
        self.db.add(question)
        await self.db.flush()
        await self.db.refresh(question)
        return question

    async def delete_by_application_id(self, application_id: uuid.UUID) -> None:
        """Delete an existing prep set for regeneration."""
        await self._set_rls_context()
        stmt = delete(InterviewPrepSet).filter(
            InterviewPrepSet.job_application_id == application_id,
            InterviewPrepSet.user_id == self.tenant_id
        )
        await self.db.execute(stmt)
        await self.db.flush()
