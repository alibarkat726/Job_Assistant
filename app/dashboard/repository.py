import uuid
from typing import List, Optional, Tuple, Any
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db.repository import BaseTenantRepository
from app.core_schema.models import JobApplication, ApplicationSkillMatch, InterviewPrepSet


class DashboardRepository(BaseTenantRepository[JobApplication]):
    """Read-only repository for dashboard aggregation queries."""
    
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(JobApplication, db, tenant_id)

    async def list_applications(self, status_filter: Optional[str] = None) -> List[Any]:
        """Fetch all applications with joined counts for matched/required skills."""
        await self._set_rls_context()
        
        # Subquery for total required skills
        req_sq = (
            select(
                ApplicationSkillMatch.job_application_id,
                func.count().label("required_count")
            )
            .filter(
                ApplicationSkillMatch.is_required == True,
                ApplicationSkillMatch.user_id == self.tenant_id
            )
            .group_by(ApplicationSkillMatch.job_application_id)
            .subquery()
        )

        # Subquery for matched skills
        match_sq = (
            select(
                ApplicationSkillMatch.job_application_id,
                func.count().label("matched_count")
            )
            .filter(
                ApplicationSkillMatch.match_status == "matched",
                ApplicationSkillMatch.is_required == True,
                ApplicationSkillMatch.user_id == self.tenant_id
            )
            .group_by(ApplicationSkillMatch.job_application_id)
            .subquery()
        )

        stmt = (
            select(
                JobApplication,
                func.coalesce(req_sq.c.required_count, 0).label("required_skills_count"),
                func.coalesce(match_sq.c.matched_count, 0).label("matched_skills_count")
            )
            .outerjoin(req_sq, JobApplication.id == req_sq.c.job_application_id)
            .outerjoin(match_sq, JobApplication.id == match_sq.c.job_application_id)
            .filter(JobApplication.user_id == self.tenant_id)
            .order_by(JobApplication.created_at.desc())
        )
        
        if status_filter:
            stmt = stmt.filter(JobApplication.status == status_filter)

        result = await self.db.execute(stmt)
        return result.all()

    async def get_application_detail(self, application_id: uuid.UUID) -> Optional[JobApplication]:
        """Eagerly fetch the full application context."""
        await self._set_rls_context()
        stmt = (
            select(JobApplication)
            .filter(JobApplication.id == application_id, JobApplication.user_id == self.tenant_id)
            .options(
                selectinload(JobApplication.requirements),
                selectinload(JobApplication.skill_matches),
                selectinload(JobApplication.tailored_cv),
                selectinload(JobApplication.interview_prep_set).selectinload(InterviewPrepSet.questions)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_missing_skills_frequency(self, limit: int = 5) -> List[Tuple[str, str, int]]:
        """Get the most frequently missing *required* skills."""
        await self._set_rls_context()
        stmt = (
            select(
                ApplicationSkillMatch.jd_skill_slug,
                func.max(ApplicationSkillMatch.jd_skill_name).label("jd_skill_name"),
                func.count().label("frequency")
            )
            .filter(
                ApplicationSkillMatch.user_id == self.tenant_id,
                ApplicationSkillMatch.is_required == True,
                ApplicationSkillMatch.match_status == "missing"
            )
            .group_by(ApplicationSkillMatch.jd_skill_slug)
            .order_by(desc("frequency"))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [(r.jd_skill_slug, r.jd_skill_name, r.frequency) for r in result.all()]

    async def get_matched_skills_frequency(self, limit: int = 5) -> List[Tuple[str, str, int]]:
        """Get the most frequently matched *required* skills."""
        await self._set_rls_context()
        stmt = (
            select(
                ApplicationSkillMatch.jd_skill_slug,
                func.max(ApplicationSkillMatch.jd_skill_name).label("jd_skill_name"),
                func.count().label("frequency")
            )
            .filter(
                ApplicationSkillMatch.user_id == self.tenant_id,
                ApplicationSkillMatch.is_required == True,
                ApplicationSkillMatch.match_status == "matched"
            )
            .group_by(ApplicationSkillMatch.jd_skill_slug)
            .order_by(desc("frequency"))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [(r.jd_skill_slug, r.jd_skill_name, r.frequency) for r in result.all()]
