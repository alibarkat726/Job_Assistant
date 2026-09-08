import json
import logging
import uuid
from typing import List, Optional, Sequence
from app.shared.middleware.error_handler import NotFoundError, AppException
from app.core_schema.models import CV, JobApplication, JDRequirement, TailoredCV, Project
from app.tailoring.repository import JobApplicationRepository, TailoredCVRepository
from app.tailoring.jd_parser import IJDParser
from app.tailoring.tailoring_agent import ITailoringAgent
from app.tailoring.matching import build_matching_report
from app.tailoring.schemas import (
    JobApplicationCreate,
    JobApplicationStatusUpdate,
    JobApplicationResponse,
    JDRequirementResponse,
    TailoredCVDraft,
    TailoredCVEditRequest,
    TailoredCVResponse,
    MatchingReport,
    StructuredJDRequirement,
)
from app.cv.repository import CVRepository
from app.skills.repository import SkillRepository
from app.projects.repository import ProjectRepository

logger = logging.getLogger(__name__)


class TailoringService:
    """
    Service layer for Job Application intake, JD parsing, matching, and CV tailoring.
    Orchestrates JDParser → Matching Engine → TailoringAgent following the
    draft/review/finalize pattern from Module 2.
    """

    def __init__(
        self,
        app_repo: JobApplicationRepository,
        tailored_cv_repo: TailoredCVRepository,
        cv_repo: CVRepository,
        skill_repo: SkillRepository,
        project_repo: ProjectRepository,
        jd_parser: IJDParser,
        tailoring_agent: ITailoringAgent,
    ):
        self.app_repo = app_repo
        self.tailored_cv_repo = tailored_cv_repo
        self.cv_repo = cv_repo
        self.skill_repo = skill_repo
        self.project_repo = project_repo
        self.jd_parser = jd_parser
        self.tailoring_agent = tailoring_agent

    # ------------------------------------------------------------------ #
    # Job Application CRUD
    # ------------------------------------------------------------------ #

    async def submit_job_description(self, dto: JobApplicationCreate) -> JobApplicationResponse:
        """
        Accept a pasted job description, parse it, score it, and produce a tailored CV draft.
        Follows the same pattern as Module 2 upload: parse → draft → review → finalize.
        """
        job_app = JobApplication(
            job_title=dto.job_title,
            company=dto.company,
            jd_raw_text=dto.jd_raw_text,
            source_url=dto.source_url,
            status="draft",
            parse_status="pending_parse",
        )
        created = await self.app_repo.create(job_app)

        # Parse JD and store requirements as normalized child rows
        await self._parse_and_store_requirements(created)

        # Re-fetch with requirements loaded
        refreshed = await self.app_repo.get_with_children(created.id)
        return self._map_app_to_response(refreshed)

    async def list_applications(self) -> List[JobApplicationResponse]:
        apps = await self.app_repo.find_all_with_children()
        return [self._map_app_to_response(a) for a in apps]

    async def get_application(self, app_id: uuid.UUID) -> JobApplicationResponse:
        app = await self.app_repo.get_with_children(app_id)
        if not app:
            raise NotFoundError(f"Job application '{app_id}' not found.")
        return self._map_app_to_response(app)

    async def update_status(self, app_id: uuid.UUID, dto: JobApplicationStatusUpdate) -> JobApplicationResponse:
        """Manually set status to 'applied' (or back to 'tailored'/'draft')."""
        app = await self.app_repo.get_with_children(app_id)
        if not app:
            raise NotFoundError(f"Job application '{app_id}' not found.")
        app.status = dto.status
        updated = await self.app_repo.update(app)
        refreshed = await self.app_repo.get_with_children(updated.id)
        return self._map_app_to_response(refreshed)

    async def delete_application(self, app_id: uuid.UUID) -> None:
        app = await self.app_repo.get_by_id(app_id)
        if not app:
            raise NotFoundError(f"Job application '{app_id}' not found.")
        await self.app_repo.delete(app)

    # ------------------------------------------------------------------ #
    # Matching (read-only, no mutation)
    # ------------------------------------------------------------------ #

    async def get_matching_report(self, app_id: uuid.UUID) -> MatchingReport:
        """Run matching engine against user's current skill graph and projects."""
        app = await self.app_repo.get_with_children(app_id)
        if not app:
            raise NotFoundError(f"Job application '{app_id}' not found.")
        if app.parse_status == "pending_parse":
            raise AppException("JD has not been parsed yet.", "JD_NOT_PARSED", 400)

        user_skills = await self.skill_repo.find_all()
        user_projects = await self.project_repo.find_all_with_skills()
        jd_requirements = [
            _jd_req_to_structured(r) for r in app.requirements
        ]

        return build_matching_report(jd_requirements, user_skills, user_projects)

    # ------------------------------------------------------------------ #
    # Tailoring — Draft/Edit/Finalize flow (mirrors Module 2)
    # ------------------------------------------------------------------ #

    async def generate_tailored_draft(self, app_id: uuid.UUID) -> TailoredCVResponse:
        """
        Run the Tailoring Agent and produce a tailored CV draft.
        Requires the user to have a finalized canonical CV (Module 2).
        Only reorders/reweights — never invents facts.
        """
        app = await self.app_repo.get_with_children(app_id)
        if not app:
            raise NotFoundError(f"Job application '{app_id}' not found.")

        canonical_cv = await self.cv_repo.get_active_canonical_cv()
        if not canonical_cv:
            raise AppException(
                "No finalized canonical CV found. Please finalize your CV in the CV module first.",
                "NO_CANONICAL_CV", 400,
            )
        # Eager-load work histories for the CV
        canonical_cv_full = await self.cv_repo.get_cv_with_children(canonical_cv.id)

        user_skills = await self.skill_repo.find_all()
        user_projects = await self.project_repo.find_all_with_skills()

        jd_requirements = [_jd_req_to_structured(r) for r in app.requirements]
        matching_report = build_matching_report(jd_requirements, user_skills, user_projects)

        # Top projects for tailoring (pass in sorted order)
        top_projects = list(user_projects)
        top_projects.sort(
            key=lambda p: next(
                (r.relevance_score for r in matching_report.project_rankings if r.project_id == p.id), 0.0
            ),
            reverse=True
        )

        # Run tailoring agent (immutable facts rule enforced inside)
        try:
            draft: TailoredCVDraft = await self.tailoring_agent.tailor(
                cv=canonical_cv_full,
                matching_report=matching_report,
                top_projects=top_projects,
            )
        except Exception as e:
            logger.error(f"Tailoring agent failed for app {app_id}: {e}")
            raise AppException("Tailoring agent failed to produce a draft.", "TAILORING_FAILED", 500)

        # Persist draft (upsert — only one TailoredCV per application)
        existing = await self.tailored_cv_repo.get_by_application_id(app_id)
        if existing:
            existing.tailored_content = json.dumps(draft.tailored_work_history)
            existing.diff_summary = draft.diff_summary
            existing.selected_project_ids = [str(pid) for pid in draft.selected_project_ids]
            existing.source_cv_id = canonical_cv.id
            existing.status = "draft"
            updated = await self.tailored_cv_repo.update(existing)
            return self._map_tailored_to_response(updated)
        else:
            tailored = TailoredCV(
                job_application_id=app_id,
                source_cv_id=canonical_cv.id,
                tailored_content=json.dumps(draft.tailored_work_history),
                diff_summary=draft.diff_summary,
                selected_project_ids=[str(pid) for pid in draft.selected_project_ids],
                status="draft",
            )
            created = await self.tailored_cv_repo.create(tailored)

            # Mark the application as tailored
            app.status = "tailored"
            await self.app_repo.update(app)

            return self._map_tailored_to_response(created)

    async def edit_tailored_draft(self, app_id: uuid.UUID, dto: TailoredCVEditRequest) -> TailoredCVResponse:
        """User edits the tailored CV draft content or selected projects."""
        draft = await self.tailored_cv_repo.get_by_application_id(app_id)
        if not draft:
            raise NotFoundError(f"No tailored CV draft found for application '{app_id}'.")
        if draft.status == "finalized":
            raise AppException("Tailored CV is already finalized.", "ALREADY_FINALIZED", 400)

        if dto.tailored_content is not None:
            draft.tailored_content = dto.tailored_content
        if dto.selected_project_ids is not None:
            draft.selected_project_ids = [str(pid) for pid in dto.selected_project_ids]

        updated = await self.tailored_cv_repo.update(draft)
        return self._map_tailored_to_response(updated)

    async def finalize_tailored_cv(self, app_id: uuid.UUID) -> TailoredCVResponse:
        """Finalize the tailored CV — makes it the stored version for this application."""
        draft = await self.tailored_cv_repo.get_by_application_id(app_id)
        if not draft:
            raise NotFoundError(f"No tailored CV draft found for application '{app_id}'.")
        if draft.status == "finalized":
            raise AppException("Tailored CV is already finalized.", "ALREADY_FINALIZED", 400)

        draft.status = "finalized"
        updated = await self.tailored_cv_repo.update(draft)
        return self._map_tailored_to_response(updated)

    async def get_tailored_cv(self, app_id: uuid.UUID) -> TailoredCVResponse:
        draft = await self.tailored_cv_repo.get_by_application_id(app_id)
        if not draft:
            raise NotFoundError(f"No tailored CV found for application '{app_id}'.")
        return self._map_tailored_to_response(draft)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def _parse_and_store_requirements(self, app: JobApplication) -> None:
        """Run JD parser and insert normalized JDRequirement rows."""
        try:
            structured_jd = await self.jd_parser.parse(app.jd_raw_text)
            jd_reqs_for_match = []
            
            for req in structured_jd.required_skills:
                from app.skills.services import normalize_skill_name
                skill_slug = normalize_skill_name(req.skill_name)
                item = JDRequirement(
                    job_application_id=app.id,
                    user_id=app.user_id,
                    skill_name=req.skill_name,
                    skill_slug=skill_slug,
                    is_required=req.is_required,
                    seniority=req.seniority,
                )
                self.app_repo.db.add(item)
                jd_reqs_for_match.append(
                    StructuredJDRequirement(
                        skill_name=item.skill_name,
                        is_required=item.is_required,
                        seniority=item.seniority
                    )
                )
            
            # Immediately run matching and persist results for analytics
            if jd_reqs_for_match:
                user_skills = await self.skill_repo.find_all()
                from app.tailoring.matching import build_matching_report
                match_results = build_matching_report(jd_reqs_for_match, user_skills, [])
                
                from app.core_schema.models import ApplicationSkillMatch
                for match in match_results.skill_matches:
                    match_record = ApplicationSkillMatch(
                        job_application_id=app.id,
                        user_id=app.user_id,
                        jd_skill_name=match.jd_skill_name,
                        jd_skill_slug=match.jd_skill_slug,
                        match_status=match.match_status,
                        is_required=match.is_required
                    )
                    self.app_repo.db.add(match_record)

            await self.app_repo.db.commit()
            app.parse_status = "parsed"
            await self.app_repo.update(app)
        except Exception as e:
            logger.error(f"JD parse failed for application {app.id}: {e}")
            app.parse_status = "needs_manual_review"
            await self.app_repo.update(app)

    def _map_app_to_response(self, app: JobApplication) -> JobApplicationResponse:
        reqs = []
        if app.requirements:
            for r in app.requirements:
                reqs.append(JDRequirementResponse(
                    id=r.id,
                    skill_name=r.skill_name,
                    skill_slug=r.skill_slug,
                    is_required=r.is_required,
                    seniority=r.seniority,
                ))
        return JobApplicationResponse(
            id=app.id,
            user_id=app.user_id,
            job_title=app.job_title,
            company=app.company,
            source_url=app.source_url,
            status=app.status,
            parse_status=app.parse_status,
            requirements=reqs,
            created_at=app.created_at,
            updated_at=app.updated_at,
        )

    def _map_tailored_to_response(self, t: TailoredCV) -> TailoredCVResponse:
        return TailoredCVResponse(
            id=t.id,
            job_application_id=t.job_application_id,
            source_cv_id=t.source_cv_id,
            tailored_content=t.tailored_content,
            diff_summary=t.diff_summary,
            status=t.status,
            selected_project_ids=t.selected_project_ids,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )


def _jd_req_to_structured(r: JDRequirement):
    from app.tailoring.schemas import StructuredJDRequirement
    return StructuredJDRequirement(
        skill_name=r.skill_name,
        is_required=r.is_required,
        seniority=r.seniority,
    )
