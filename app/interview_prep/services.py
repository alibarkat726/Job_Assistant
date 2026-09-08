import uuid
from typing import List
from datetime import datetime, timezone
import logging

from app.shared.middleware.error_handler import NotFoundError, AppException
from app.core_schema.models import InterviewPrepSet, InterviewQuestion, JobApplication, JDRequirement
from app.interview_prep.repository import InterviewPrepRepository
from app.interview_prep.prep_agent import IInterviewPrepAgent
from app.interview_prep.schemas import InterviewPrepSetResponse, InterviewQuestionResponse, InterviewQuestionUpdate
from app.tailoring.repository import JobApplicationRepository
from app.tailoring.matching import build_matching_report
from app.tailoring.schemas import StructuredJDRequirement
from app.skills.repository import SkillRepository
from app.projects.repository import ProjectRepository

logger = logging.getLogger(__name__)


class InterviewPrepService:
    def __init__(
        self,
        prep_repo: InterviewPrepRepository,
        app_repo: JobApplicationRepository,
        skill_repo: SkillRepository,
        project_repo: ProjectRepository,
        agent: IInterviewPrepAgent
    ):
        self.prep_repo = prep_repo
        self.app_repo = app_repo
        self.skill_repo = skill_repo
        self.project_repo = project_repo
        self.agent = agent

    async def generate_prep_set(self, application_id: uuid.UUID) -> InterviewPrepSetResponse:
        """
        Generate (or regenerate) a set of interview questions for the given application.
        Deletes any existing prep set for this application.
        """
        app = await self.app_repo.get_with_children(application_id)
        if not app:
            raise NotFoundError(f"Job application '{application_id}' not found.")
        
        if app.parse_status != "parsed":
            raise AppException("Job application must be fully parsed before generating prep.", "NOT_PARSED", 400)

        # 1. Clean up old prep set if regenerating
        await self.prep_repo.delete_by_application_id(application_id)

        # 2. Gather inputs for agent
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

        # Use the matching report to get the prioritized skills and projects
        matching_report = build_matching_report(jd_requirements, user_skills, user_projects)
        
        # Select top projects based on matching report ranking (up to 3)
        top_project_ids = {p.project_id for p in matching_report.project_rankings[:3]}
        top_projects = [p for p in user_projects if p.id in top_project_ids]

        # 3. Generate questions
        try:
            structured_set = await self.agent.generate(
                jd_requirements=jd_requirements,
                matched_skills=matching_report.skill_matches,
                projects=top_projects
            )
        except Exception as e:
            logger.error(f"Interview prep agent failed: {e}")
            # Insert a "needs_manual_review" stub if it failed
            prep_set = InterviewPrepSet(
                job_application_id=application_id,
                user_id=app.user_id,
                status="needs_manual_review"
            )
            created = await self.prep_repo.create(prep_set)
            return self._map_to_response(created)

        # 4. Persist
        prep_set = InterviewPrepSet(
            job_application_id=application_id,
            user_id=app.user_id,
            status="generated",
            generated_at=datetime.now(timezone.utc)
        )
        self.prep_repo.db.add(prep_set)
        await self.prep_repo.db.flush()

        for idx, q in enumerate(structured_set.questions):
            question = InterviewQuestion(
                prep_set_id=prep_set.id,
                user_id=app.user_id,
                question_text=q.question_text,
                category=q.category,
                rationale=q.rationale,
                suggested_answer_outline=q.suggested_answer_outline,
                ordering=idx
            )
            self.prep_repo.db.add(question)
        
        await self.prep_repo.db.commit()
        
        refreshed = await self.prep_repo.get_by_application_id(application_id)
        return self._map_to_response(refreshed)

    async def get_prep_set(self, application_id: uuid.UUID) -> InterviewPrepSetResponse:
        """Fetch the existing prep set for an application."""
        prep_set = await self.prep_repo.get_by_application_id(application_id)
        if not prep_set:
            raise NotFoundError(f"No interview prep set found for application '{application_id}'.")
        return self._map_to_response(prep_set)

    async def update_question(self, question_id: uuid.UUID, dto: InterviewQuestionUpdate) -> InterviewQuestionResponse:
        """Update notes or practice status for a specific question."""
        question = await self.prep_repo.get_question(question_id)
        if not question:
            raise NotFoundError(f"Interview question '{question_id}' not found.")
        
        if dto.user_notes is not None:
            question.user_notes = dto.user_notes
        if dto.is_practiced is not None:
            question.is_practiced = dto.is_practiced
            
        updated = await self.prep_repo.update_question(question)
        await self.prep_repo.db.commit()
        return self._map_question_to_response(updated)


    def _map_to_response(self, prep_set: InterviewPrepSet) -> InterviewPrepSetResponse:
        questions = []
        if getattr(prep_set, 'questions', None):
            for q in prep_set.questions:
                questions.append(self._map_question_to_response(q))
                
        return InterviewPrepSetResponse(
            id=prep_set.id,
            job_application_id=prep_set.job_application_id,
            status=prep_set.status,
            generated_at=prep_set.generated_at,
            questions=questions
        )

    def _map_question_to_response(self, q: InterviewQuestion) -> InterviewQuestionResponse:
        return InterviewQuestionResponse(
            id=q.id,
            prep_set_id=q.prep_set_id,
            question_text=q.question_text,
            category=q.category,
            rationale=q.rationale,
            suggested_answer_outline=q.suggested_answer_outline,
            user_notes=q.user_notes,
            is_practiced=q.is_practiced,
            ordering=q.ordering
        )
