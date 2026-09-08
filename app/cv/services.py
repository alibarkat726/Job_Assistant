import logging
from typing import Tuple
import uuid
from app.shared.middleware.error_handler import NotFoundError, AppException
from app.core_schema.models import CV, WorkHistory, EducationEntry, CVSkill
from app.cv.storage import FileStorageService, LocalStorageService
from app.cv.security import validate_file_size, sniff_mime_type, sanitize_text
from app.cv.extractor import extract_text_from_file
from app.cv.parser import IntakeAgentService
from app.cv.repository import CVRepository
from app.cv.schemas import (
    CVResponse,
    CVUploadResponse,
    CVUpdateRequest,
    StructuredCVSchema,
    WorkHistorySchema,
    EducationSchema,
    CVSkillSchema,
    ContactInfoSchema,
)

logger = logging.getLogger(__name__)


class CVIntakeService:
    """Service layer encapsulating CV intake, raw file storage, parsing, review/edit, and finalization."""

    def __init__(
        self,
        cv_repo: CVRepository,
        storage_service: FileStorageService = LocalStorageService(),
        intake_agent: IntakeAgentService = IntakeAgentService(),
    ):
        self.cv_repo = cv_repo
        self.storage_service = storage_service
        self.intake_agent = intake_agent

    async def upload_and_parse_cv(
        self, user_id: uuid.UUID, filename: str, file_bytes: bytes
    ) -> CVUploadResponse:
        """Upload raw CV file, sniff MIME format, extract text, run Intake Agent, and save unfinalized draft."""
        # 1. Server-side File Security Checks
        validate_file_size(file_bytes)
        mime_type = sniff_mime_type(file_bytes, filename)

        # 2. Extract Raw Text
        raw_text = extract_text_from_file(file_bytes, mime_type)

        # 3. Store Raw File securely
        file_key = await self.storage_service.save_file(user_id, file_bytes, filename)

        # 4. Parse Structured CV via Intake Agent
        parsed_data = await self.intake_agent.parse_raw_cv(raw_text)

        # 5. Build Domain Models
        contact = parsed_data.contact_info
        cv_entity = CV(
            user_id=user_id,
            title=f"CV - {filename}",
            variant_name="Base Intake CV",
            is_canonical=False,  # Unfinalized draft for user review
            raw_file_key=file_key,
            raw_file_name=filename,
            mime_type=mime_type,
            file_size=len(file_bytes),
            raw_text=raw_text,
            full_name=contact.full_name,
            email=contact.email,
            phone=contact.phone,
            location=contact.location,
            summary=contact.summary,
            parse_confidence=parsed_data.parse_confidence,
        )

        work_entities = [
            WorkHistory(
                company=wh.company,
                role=wh.role,
                location=wh.location,
                start_date=wh.start_date,
                end_date=wh.end_date,
                is_current=wh.is_current,
                description=wh.description,
            )
            for wh in parsed_data.work_history
        ]

        edu_entities = [
            EducationEntry(
                institution=edu.institution,
                degree=edu.degree,
                field_of_study=edu.field_of_study,
                start_date=edu.start_date,
                end_date=edu.end_date,
            )
            for edu in parsed_data.education
        ]

        skill_entities = [
            CVSkill(name=skill)
            for skill in parsed_data.skills
        ]

        # 6. Save Draft CV & Child Records in DB
        saved_cv = await self.cv_repo.save_cv_with_children(
            cv_entity, work_entities, edu_entities, skill_entities
        )

        return CVUploadResponse(
            cv_id=saved_cv.id,
            message="CV uploaded and parsed successfully. Please review and finalize structured details.",
            is_canonical=saved_cv.is_canonical,
            parse_confidence=saved_cv.parse_confidence,
            parsing_notes=parsed_data.parsing_notes,
            parsed_data=parsed_data,
        )

    async def get_current_user_cv(self, user_id: uuid.UUID) -> CVResponse:
        """Fetch current user's active canonical or draft CV."""
        cv = await self.cv_repo.get_any_active_cv()
        if not cv:
            raise NotFoundError("No CV record found for current user.")

        return self._map_to_response(cv)

    async def update_cv_draft(self, user_id: uuid.UUID, dto: CVUpdateRequest) -> CVResponse:
        """Review and edit parsed structured CV details before or after finalization."""
        cv = await self.cv_repo.get_any_active_cv()
        if not cv:
            raise NotFoundError("No active CV draft found to edit. Please upload a CV first.")

        if dto.title is not None:
            cv.title = sanitize_text(dto.title)
        if dto.variant_name is not None:
            cv.variant_name = sanitize_text(dto.variant_name)
        if dto.full_name is not None:
            cv.full_name = sanitize_text(dto.full_name) or None
        if dto.email is not None:
            cv.email = sanitize_text(dto.email) or None
        if dto.phone is not None:
            cv.phone = sanitize_text(dto.phone) or None
        if dto.location is not None:
            cv.location = sanitize_text(dto.location) or None
        if dto.summary is not None:
            cv.summary = sanitize_text(dto.summary) or None

        work_entities = (
            [
                WorkHistory(
                    company=sanitize_text(wh.company),
                    role=sanitize_text(wh.role),
                    location=sanitize_text(wh.location or "") or None,
                    start_date=wh.start_date,
                    end_date=wh.end_date,
                    is_current=wh.is_current,
                    description=sanitize_text(wh.description or "") or None,
                )
                for wh in dto.work_history
            ]
            if dto.work_history is not None
            else [
                WorkHistory(
                    company=wh.company,
                    role=wh.role,
                    location=wh.location,
                    start_date=wh.start_date,
                    end_date=wh.end_date,
                    is_current=wh.is_current,
                    description=wh.description,
                )
                for wh in cv.work_histories
            ]
        )

        edu_entities = (
            [
                EducationEntry(
                    institution=sanitize_text(edu.institution),
                    degree=sanitize_text(edu.degree or "") or None,
                    field_of_study=sanitize_text(edu.field_of_study or "") or None,
                    start_date=edu.start_date,
                    end_date=edu.end_date,
                )
                for edu in dto.education
            ]
            if dto.education is not None
            else [
                EducationEntry(
                    institution=edu.institution,
                    degree=edu.degree,
                    field_of_study=edu.field_of_study,
                    start_date=edu.start_date,
                    end_date=edu.end_date,
                )
                for edu in cv.education_entries
            ]
        )

        skill_entities = (
            [
                CVSkill(name=sanitize_text(sk))
                for sk in dto.skills
                if sanitize_text(sk)
            ]
            if dto.skills is not None
            else [
                CVSkill(name=sk.name, category=sk.category)
                for sk in cv.skills
            ]
        )

        updated_cv = await self.cv_repo.save_cv_with_children(
            cv, work_entities, edu_entities, skill_entities
        )
        return self._map_to_response(updated_cv)

    async def finalize_cv(self, user_id: uuid.UUID) -> CVResponse:
        """Mark unfinalized draft CV as canonical baseline profile."""
        cv = await self.cv_repo.get_any_active_cv()
        if not cv:
            raise NotFoundError("No CV draft found to finalize. Please upload a CV first.")

        cv.is_canonical = True
        updated_cv = await self.cv_repo.update(cv)
        return self._map_to_response(updated_cv)

    async def delete_current_user_cv(self, user_id: uuid.UUID) -> None:
        """Delete active CV, raw storage file, and child records, returning user to no-CV state."""
        file_keys = await self.cv_repo.delete_all_user_cvs()
        for key in file_keys:
            try:
                await self.storage_service.delete_file(user_id, key)
            except Exception as exc:
                logger.warning(f"Failed to delete storage file {key}: {str(exc)}")

    async def download_raw_file(self, user_id: uuid.UUID) -> Tuple[bytes, str, str]:
        """Verify tenant ownership and stream original uploaded file bytes."""
        cv = await self.cv_repo.get_any_active_cv()
        if not cv or not cv.raw_file_key:
            raise NotFoundError("No raw file found for current user's CV.")

        file_bytes = await self.storage_service.get_file(user_id, cv.raw_file_key)
        return file_bytes, cv.raw_file_name or "cv_download", cv.mime_type or "application/octet-stream"

    def _map_to_response(self, cv: CV) -> CVResponse:
        return CVResponse(
            id=cv.id,
            user_id=cv.user_id,
            title=cv.title,
            variant_name=cv.variant_name,
            job_id=cv.job_id,
            is_canonical=cv.is_canonical,
            raw_file_name=cv.raw_file_name,
            mime_type=cv.mime_type,
            file_size=cv.file_size,
            full_name=cv.full_name,
            email=cv.email,
            phone=cv.phone,
            location=cv.location,
            summary=cv.summary,
            parse_confidence=cv.parse_confidence,
            work_histories=[
                WorkHistorySchema(
                    id=wh.id,
                    company=wh.company,
                    role=wh.role,
                    location=wh.location,
                    start_date=wh.start_date,
                    end_date=wh.end_date,
                    is_current=wh.is_current,
                    description=wh.description,
                )
                for wh in cv.work_histories
            ],
            education_entries=[
                EducationSchema(
                    id=edu.id,
                    institution=edu.institution,
                    degree=edu.degree,
                    field_of_study=edu.field_of_study,
                    start_date=edu.start_date,
                    end_date=edu.end_date,
                )
                for edu in cv.education_entries
            ],
            skills=[
                CVSkillSchema(
                    id=sk.id,
                    name=sk.name,
                    category=sk.category,
                )
                for sk in cv.skills
            ],
            created_at=cv.created_at,
            updated_at=cv.updated_at,
        )
