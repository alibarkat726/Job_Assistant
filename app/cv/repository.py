from typing import List, Optional
import uuid
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.repository import BaseTenantRepository
from app.core_schema.models import CV, WorkHistory, EducationEntry, CVSkill


class CVRepository(BaseTenantRepository[CV]):
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(CV, db, tenant_id)

    async def get_active_canonical_cv(self) -> Optional[CV]:
        """Fetch active canonical CV for current tenant."""
        await self._set_rls_context()
        stmt = (
            select(CV)
            .filter(CV.user_id == self.tenant_id)
            .filter(CV.is_canonical.is_(True))
            .filter(CV.job_id.is_(None))
            .order_by(CV.updated_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_draft_cv(self) -> Optional[CV]:
        """Fetch current unfinalized draft CV for tenant."""
        await self._set_rls_context()
        stmt = (
            select(CV)
            .filter(CV.user_id == self.tenant_id)
            .filter(CV.is_canonical.is_(False))
            .filter(CV.job_id.is_(None))
            .order_by(CV.updated_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_any_active_cv(self) -> Optional[CV]:
        """Fetch draft CV if present, otherwise active canonical CV."""
        draft = await self.get_draft_cv()
        if draft:
            return draft
        return await self.get_active_canonical_cv()

    async def get_cv_with_children(self, cv_id: uuid.UUID) -> Optional[CV]:
        """Fetch a CV with eagerly loaded work histories for the tailoring agent."""
        from sqlalchemy.orm import selectinload
        await self._set_rls_context()
        stmt = (
            select(CV)
            .filter(CV.id == cv_id, CV.user_id == self.tenant_id)
            .options(
                selectinload(CV.work_histories),
                selectinload(CV.education_entries),
                selectinload(CV.skills),
            )
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def save_cv_with_children(
        self,
        cv: CV,
        work_histories: List[WorkHistory],
        education_entries: List[EducationEntry],
        skills: List[CVSkill],
    ) -> CV:
        """Create or replace CV record along with normalized child entities."""
        await self._set_rls_context()
        cv.user_id = self.tenant_id
        self.db.add(cv)
        await self.db.flush()

        target_cv_id = cv.id

        # Clear old child records for this CV if updating
        await self.db.execute(delete(WorkHistory).where(WorkHistory.cv_id == target_cv_id, WorkHistory.user_id == self.tenant_id))
        await self.db.execute(delete(EducationEntry).where(EducationEntry.cv_id == target_cv_id, EducationEntry.user_id == self.tenant_id))
        await self.db.execute(delete(CVSkill).where(CVSkill.cv_id == target_cv_id, CVSkill.user_id == self.tenant_id))

        for wh in work_histories:
            wh.user_id = self.tenant_id
            wh.cv_id = target_cv_id
            self.db.add(wh)

        for edu in education_entries:
            edu.user_id = self.tenant_id
            edu.cv_id = target_cv_id
            self.db.add(edu)

        for sk in skills:
            sk.user_id = self.tenant_id
            sk.cv_id = target_cv_id
            self.db.add(sk)

        await self.db.flush()

        stmt = select(CV).filter(CV.id == target_cv_id, CV.user_id == self.tenant_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def delete_all_user_cvs(self) -> List[str]:
        """Delete all CV records for current tenant and return list of file keys to delete."""
        await self._set_rls_context()
        stmt = select(CV).filter(CV.user_id == self.tenant_id)
        result = await self.db.execute(stmt)
        cv_list = result.scalars().all()
        file_keys = [cv.raw_file_key for cv in cv_list if cv.raw_file_key]

        for cv in cv_list:
            await self.db.delete(cv)

        await self.db.flush()
        await self.db.commit()
        return file_keys
