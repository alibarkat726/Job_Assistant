import uuid
from typing import Optional
from app.shared.middleware.error_handler import NotFoundError

from app.dashboard.repository import DashboardRepository
from app.dashboard.schemas import (
    DashboardApplicationListResponse,
    DashboardApplicationSummary,
    DashboardApplicationDetailResponse,
    SkillGapAnalyticsResponse,
    SkillFrequency,
    DashboardSkillMatch
)
from app.tailoring.schemas import JobApplicationResponse, JDRequirementResponse, TailoredCVResponse
from app.interview_prep.schemas import InterviewPrepSetResponse, InterviewQuestionResponse

class DashboardService:
    def __init__(self, repo: DashboardRepository):
        self.repo = repo

    async def list_applications(self, status: Optional[str] = None) -> DashboardApplicationListResponse:
        rows = await self.repo.list_applications(status_filter=status)
        items = []
        for app, required_count, matched_count in rows:
            items.append(DashboardApplicationSummary(
                id=app.id,
                job_title=app.job_title,
                company=app.company,
                status=app.status,
                parse_status=app.parse_status,
                matched_skills_count=matched_count,
                required_skills_count=required_count,
                created_at=app.created_at,
                updated_at=app.updated_at
            ))
        return DashboardApplicationListResponse(items=items)

    async def get_application_detail(self, app_id: uuid.UUID) -> DashboardApplicationDetailResponse:
        app = await self.repo.get_application_detail(app_id)
        if not app:
            raise NotFoundError(f"Job application '{app_id}' not found.")

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
        
        app_resp = JobApplicationResponse(
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

        matches = []
        if getattr(app, 'skill_matches', None):
            for m in app.skill_matches:
                matches.append(DashboardSkillMatch(
                    jd_skill_name=m.jd_skill_name,
                    jd_skill_slug=m.jd_skill_slug,
                    match_status=m.match_status,
                    is_required=m.is_required
                ))
        
        tailored_resp = None
        if app.tailored_cv:
            tailored_resp = TailoredCVResponse(
                id=app.tailored_cv.id,
                job_application_id=app.tailored_cv.job_application_id,
                source_cv_id=app.tailored_cv.source_cv_id,
                tailored_content=app.tailored_cv.tailored_content,
                diff_summary=app.tailored_cv.diff_summary,
                selected_project_ids=[uuid.UUID(pid) for pid in app.tailored_cv.selected_project_ids],
                status=app.tailored_cv.status,
                created_at=app.tailored_cv.created_at,
                updated_at=app.tailored_cv.updated_at,
            )

        prep_resp = None
        if app.interview_prep_set:
            qs = []
            if getattr(app.interview_prep_set, 'questions', None):
                for q in app.interview_prep_set.questions:
                    qs.append(InterviewQuestionResponse(
                        id=q.id,
                        prep_set_id=q.prep_set_id,
                        question_text=q.question_text,
                        category=q.category,
                        rationale=q.rationale,
                        suggested_answer_outline=q.suggested_answer_outline,
                        user_notes=q.user_notes,
                        is_practiced=q.is_practiced,
                        ordering=q.ordering
                    ))
            prep_resp = InterviewPrepSetResponse(
                id=app.interview_prep_set.id,
                job_application_id=app.interview_prep_set.job_application_id,
                status=app.interview_prep_set.status,
                generated_at=app.interview_prep_set.generated_at,
                questions=qs
            )

        return DashboardApplicationDetailResponse(
            application=app_resp,
            skill_matches=matches,
            tailored_cv=tailored_resp,
            interview_prep=prep_resp
        )

    async def get_skill_gap_analytics(self) -> SkillGapAnalyticsResponse:
        missing = await self.repo.get_missing_skills_frequency(limit=5)
        matched = await self.repo.get_matched_skills_frequency(limit=5)
        
        top_missing = [SkillFrequency(skill_slug=slug, skill_name=name, frequency_count=count) for slug, name, count in missing]
        top_matched = [SkillFrequency(skill_slug=slug, skill_name=name, frequency_count=count) for slug, name, count in matched]
        
        nudge = None
        if top_missing:
            highest_missing = top_missing[0]
            if highest_missing.frequency_count > 1:
                nudge = (
                    f"You've had '{highest_missing.skill_name}' flagged as a missing requirement "
                    f"in {highest_missing.frequency_count} applications. Consider logging learning progress on it."
                )
                
        return SkillGapAnalyticsResponse(
            top_missing_skills=top_missing,
            top_matched_skills=top_matched,
            learning_nudge=nudge
        )
