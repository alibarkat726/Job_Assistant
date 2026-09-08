import json
import uuid
import logging
from typing import Set, List

from app.shared.middleware.error_handler import NotFoundError, AppException
from app.core_schema.models import CoverLetter, CV
from app.cover_letters.repository import CoverLetterRepository
from app.cover_letters.cover_letter_agent import ICoverLetterAgent, verify_grounded
from app.cover_letters.schemas import CoverLetterResponse, CoverLetterGenerateRequest, CoverLetterEditRequest
from app.tailoring.repository import JobApplicationRepository
from app.tailoring.matching import build_matching_report
from app.tailoring.schemas import StructuredJDRequirement
from app.skills.repository import SkillRepository
from app.projects.repository import ProjectRepository
from app.cv.repository import CVRepository

logger = logging.getLogger(__name__)


class CoverLetterService:
    def __init__(
        self,
        cl_repo: CoverLetterRepository,
        app_repo: JobApplicationRepository,
        cv_repo: CVRepository,
        skill_repo: SkillRepository,
        project_repo: ProjectRepository,
        agent: ICoverLetterAgent
    ):
        self.cl_repo = cl_repo
        self.app_repo = app_repo
        self.cv_repo = cv_repo
        self.skill_repo = skill_repo
        self.project_repo = project_repo
        self.agent = agent

    def _build_allowed_facts(self, cv: CV, skills, projects, company: str, job_title: str) -> Set[str]:
        """
        Build the set of grounded entity strings from the user's stored data.
        These are the only terms the cover letter is allowed to reference.
        """
        facts: Set[str] = set()
        if company:
            facts.update(company.split())
            facts.add(company)
        if job_title:
            facts.update(job_title.split())
            facts.add(job_title)

        # CV contact fields
        if cv.full_name:
            facts.update(cv.full_name.split())
            facts.add(cv.full_name)

        # Work history
        for wh in cv.work_histories:
            facts.add(wh.company)
            facts.update(wh.company.split())
            facts.add(wh.role)
            facts.update(wh.role.split())

        # Education
        for edu in cv.education_entries:
            facts.add(edu.institution)
            facts.update(edu.institution.split())
            if edu.degree:
                facts.add(edu.degree)
                facts.update(edu.degree.split())

        # Skills (Module 3)
        for s in skills:
            facts.add(s.name)
            facts.update(s.name.split())

        # Projects (Module 3)
        for p in projects:
            facts.add(p.title)
            facts.update(p.title.split())

        # Remove empty strings
        facts.discard("")
        return facts

    async def generate_cover_letter(
        self, application_id: uuid.UUID, dto: CoverLetterGenerateRequest
    ) -> CoverLetterResponse:
        """Generate a new cover letter draft, replacing any existing draft."""
        app = await self.app_repo.get_with_children(application_id)
        if not app:
            raise NotFoundError(f"Job application '{application_id}' not found.")

        cv = await self.cv_repo.get_active_canonical_cv()
        if not cv:
            raise AppException("A finalized canonical CV is required to generate a cover letter.", "NO_CV", 400)

        user_skills = await self.skill_repo.find_all()
        user_projects = await self.project_repo.find_all_with_skills()

        jd_requirements = [
            StructuredJDRequirement(
                skill_name=r.skill_name,
                is_required=r.is_required,
                seniority=r.seniority
            )
            for r in app.requirements
        ]

        matching_report = build_matching_report(jd_requirements, user_skills, user_projects)
        top_project_ids = {p.project_id for p in matching_report.project_rankings[:3]}
        top_projects = [p for p in user_projects if p.id in top_project_ids]

        # 1. Generate letter text from the agent
        letter_text = await self.agent.generate(
            job_title=app.job_title,
            company=app.company or "",
            cv=cv,
            matched_skills=matching_report.skill_matches,
            projects=top_projects,
            tone=dto.tone,
            length=dto.length
        )

        # 2. Run post-generation grounding check
        allowed_facts = self._build_allowed_facts(
            cv, user_skills, user_projects, app.company or "", app.job_title
        )
        unverified_claims = verify_grounded(letter_text, allowed_facts)
        if unverified_claims:
            logger.warning(
                "Cover letter grounding check flagged potential hallucinations for application %s: %s",
                application_id, unverified_claims
            )

        # 3. Persist — overwrite any existing draft (regenerate semantics)
        await self.cl_repo.delete_by_application_id(application_id)

        cl = CoverLetter(
            job_application_id=application_id,
            user_id=app.user_id,
            content=letter_text,
            tone=dto.tone,
            length=dto.length,
            status="draft",
            unverified_claims=json.dumps(unverified_claims) if unverified_claims else None
        )
        created = await self.cl_repo.create(cl)
        return self._map_to_response(created)

    async def get_cover_letter(self, application_id: uuid.UUID) -> CoverLetterResponse:
        cl = await self.cl_repo.get_by_application_id(application_id)
        if not cl:
            raise NotFoundError(f"No cover letter found for application '{application_id}'.")
        return self._map_to_response(cl)

    async def edit_cover_letter(
        self, application_id: uuid.UUID, dto: CoverLetterEditRequest
    ) -> CoverLetterResponse:
        cl = await self.cl_repo.get_by_application_id(application_id)
        if not cl:
            raise NotFoundError(f"No cover letter found for application '{application_id}'.")

        if cl.status == "finalized":
            raise AppException("Cannot edit a finalized cover letter.", "ALREADY_FINALIZED", 400)

        cl.content = dto.content
        updated = await self.cl_repo.update(cl)
        return self._map_to_response(updated)

    async def finalize_cover_letter(self, application_id: uuid.UUID) -> CoverLetterResponse:
        cl = await self.cl_repo.get_by_application_id(application_id)
        if not cl:
            raise NotFoundError(f"No cover letter found for application '{application_id}'.")

        cl.status = "finalized"
        updated = await self.cl_repo.update(cl)
        return self._map_to_response(updated)

    async def export_cover_letter(self, application_id: uuid.UUID) -> str:
        cl = await self.cl_repo.get_by_application_id(application_id)
        if not cl:
            raise NotFoundError(f"No cover letter found for application '{application_id}'.")
        return cl.content

    def _map_to_response(self, cl: CoverLetter) -> CoverLetterResponse:
        unverified = json.loads(cl.unverified_claims) if cl.unverified_claims else None
        return CoverLetterResponse(
            id=cl.id,
            job_application_id=cl.job_application_id,
            content=cl.content,
            tone=cl.tone,
            length=cl.length,
            status=cl.status,
            unverified_claims=unverified,
            created_at=cl.created_at,
            updated_at=cl.updated_at
        )
