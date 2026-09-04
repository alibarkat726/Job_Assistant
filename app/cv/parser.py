from abc import ABC, abstractmethod
import json
import logging
import re
from typing import List, Optional
from app.config.settings import settings
from app.cv.security import sanitize_text
from app.cv.schemas import (
    ContactInfoSchema,
    EducationSchema,
    StructuredCVSchema,
    WorkHistorySchema,
)

logger = logging.getLogger(__name__)


class ICVParser(ABC):
    """Abstract interface for CV Intake Agent parsing services."""

    @abstractmethod
    async def parse_cv_text(self, raw_text: str) -> StructuredCVSchema:
        """Parse raw text extracted from a CV into a validated StructuredCVSchema."""
        pass


class HeuristicCVParser(ICVParser):
    """
    Deterministic rule & regex-based CV parser.
    Extracts contact info, work experience blocks, education, and skill lists.
    """

    async def parse_cv_text(self, raw_text: str) -> StructuredCVSchema:
        sanitized_raw = sanitize_text(raw_text)
        lines = [line.strip() for line in sanitized_raw.split("\n") if line.strip()]

        # 1. Extract Contact Info
        email = self._extract_email(sanitized_raw)
        phone = self._extract_phone(sanitized_raw)
        name = self._extract_name(lines, email)
        summary = self._extract_summary(lines)

        # 2. Extract Work History, Education, and Skills
        work_history = self._extract_work_history(lines)
        education = self._extract_education(lines)
        skills = self._extract_skills(sanitized_raw, lines)

        # 3. Determine Confidence Score
        notes = []
        confidence = "high"
        if not work_history:
            notes.append("Could not automatically segment work history entries.")
            confidence = "medium"
        if not education:
            notes.append("Could not automatically segment education entries.")
        if not email and not phone:
            notes.append("Contact email or phone number was missing from document.")
            confidence = "low"

        return StructuredCVSchema(
            contact_info=ContactInfoSchema(
                full_name=name,
                email=email,
                phone=phone,
                location=None,
                summary=summary,
            ),
            work_history=work_history,
            education=education,
            skills=skills,
            parse_confidence=confidence,
            parsing_notes=notes,
        )

    def _extract_email(self, text: str) -> Optional[str]:
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        match = re.search(email_pattern, text)
        return match.group(0) if match else None

    def _extract_phone(self, text: str) -> Optional[str]:
        phone_pattern = r"(\+?\d{1,3}[-.\s]?)?(\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}"
        match = re.search(phone_pattern, text)
        return match.group(0).strip() if match else None

    def _extract_name(self, lines: List[str], email: Optional[str]) -> Optional[str]:
        for line in lines[:5]:
            if "@" not in line and not re.search(r"\d", line) and len(line.split()) in [2, 3, 4]:
                return line
        if email:
            return email.split("@")[0].replace(".", " ").replace("_", " ").title()
        return "Candidate Name"

    def _extract_summary(self, lines: List[str]) -> Optional[str]:
        summary_lines = []
        capturing = False
        for line in lines[:15]:
            lower = line.lower()
            if any(k in lower for k in ["summary", "profile", "about me", "objective"]):
                capturing = True
                continue
            if capturing:
                if any(k in lower for k in ["experience", "education", "skills", "projects"]):
                    break
                summary_lines.append(line)
        return " ".join(summary_lines).strip() if summary_lines else lines[0] if lines else None

    def _extract_work_history(self, lines: List[str]) -> List[WorkHistorySchema]:
        entries: List[WorkHistorySchema] = []
        in_experience = False
        current_company = ""
        current_role = ""
        current_desc = []

        for line in lines:
            lower = line.lower()
            if any(k in lower for k in ["experience", "work history", "employment"]):
                in_experience = True
                continue
            if in_experience and any(k in lower for k in ["education", "skills", "projects", "certifications"]):
                break

            if in_experience:
                if any(role_kw in lower for role_kw in ["developer", "engineer", "manager", "lead", "designer", "consultant", "intern", "analyst", "specialist"]):
                    if current_role and current_company:
                        entries.append(
                            WorkHistorySchema(
                                company=current_company,
                                role=current_role,
                                description=" ".join(current_desc),
                            )
                        )
                        current_desc = []
                    current_role = line
                elif not current_company:
                    current_company = line
                else:
                    current_desc.append(line)

        if current_role and current_company:
            entries.append(
                WorkHistorySchema(
                    company=current_company,
                    role=current_role,
                    description=" ".join(current_desc),
                )
            )

        if not entries and len(lines) > 3:
            # Fallback basic item if section markers were missing
            entries.append(
                WorkHistorySchema(
                    company="Company",
                    role="Professional Role",
                    description=" ".join(lines[1:5]),
                )
            )
        return entries

    def _extract_education(self, lines: List[str]) -> List[EducationSchema]:
        entries: List[EducationSchema] = []
        in_edu = False

        for line in lines:
            lower = line.lower()
            if "education" in lower or "academic" in lower:
                in_edu = True
                continue
            if in_edu and any(k in lower for k in ["experience", "skills", "projects", "certifications"]):
                break

            if in_edu:
                if any(degree_kw in lower for degree_kw in ["bachelor", "master", "phd", "b.s", "m.s", "degree", "university", "college"]):
                    entries.append(
                        EducationSchema(
                            institution=line,
                            degree="Degree / Higher Education",
                        )
                    )

        if not entries:
            for line in lines:
                lower = line.lower()
                if any(degree_kw in lower for degree_kw in ["university", "college", "bachelor", "master"]):
                    entries.append(
                        EducationSchema(
                            institution=line,
                            degree="Degree / Education",
                        )
                    )
                    break
        return entries

    def _extract_skills(self, text: str, lines: List[str]) -> List[str]:
        known_skills = [
            "Python", "FastAPI", "PostgreSQL", "SQL", "Docker", "Kubernetes",
            "JavaScript", "TypeScript", "React", "Node.js", "AWS", "Git",
            "REST API", "GraphQL", "CI/CD", "Linux", "Agile", "Scrum",
            "Java", "C++", "Go", "HTML", "CSS", "Tailwind"
        ]
        found_skills = set()
        for skill in known_skills:
            pattern = rf"\b{re.escape(skill)}\b"
            if re.search(pattern, text, re.IGNORECASE):
                found_skills.add(skill)

        # Also inspect explicit Skills section
        in_skills = False
        for line in lines:
            lower = line.lower()
            if "skills" in lower or "technologies" in lower:
                in_skills = True
                continue
            if in_skills and any(k in lower for k in ["experience", "education", "projects"]):
                break
            if in_skills:
                parts = re.split(r"[,;•|]", line)
                for part in parts:
                    cleaned_item = part.strip()
                    if cleaned_item and len(cleaned_item) < 30:
                        found_skills.add(cleaned_item.title())

        return sorted(list(found_skills))


class LLMCVParser(ICVParser):
    """
    LLM-powered CV parser with structured output validation against StructuredCVSchema.
    Falls back to exception when API key is unconfigured or model output fails schema validation.
    """

    def __init__(self, api_key: str = settings.LLM_API_KEY, model: str = settings.LLM_MODEL):
        self.api_key = api_key
        self.model = model

    async def parse_cv_text(self, raw_text: str) -> StructuredCVSchema:
        if not self.api_key:
            raise ValueError("LLM API key is not configured.")

        # Stub / interface implementation for LLM invocation
        # If an LLM client library is integrated in the future, invoke it here and parse response JSON
        raise NotImplementedError("LLM parser client is currently unconfigured.")


class IntakeAgentService:
    """
    Orchestrates the Intake Agent CV parsing fallback chain:
    1. Attempt LLMCVParser (if enabled)
    2. Validate structured Pydantic schema
    3. On error / validation failure: Automatically fall back to HeuristicCVParser
    4. Sanitize all extracted string fields to prevent HTML/XSS injection
    """

    def __init__(
        self,
        heuristic_parser: HeuristicCVParser = HeuristicCVParser(),
        llm_parser: Optional[LLMCVParser] = None,
    ):
        self.heuristic_parser = heuristic_parser
        self.llm_parser = llm_parser or LLMCVParser()

    async def parse_raw_cv(self, raw_text: str) -> StructuredCVSchema:
        if not raw_text or not raw_text.strip():
            return StructuredCVSchema(
                contact_info=ContactInfoSchema(),
                parse_confidence="low",
                parsing_notes=["Uploaded document did not contain parseable text."],
            )

        parsed_schema = None

        # Step 1: Try LLM Parser if configured
        if settings.LLM_API_KEY:
            try:
                print("this is parsed by LLM parser")
                parsed_schema = await self.llm_parser.parse_cv_text(raw_text)
                logger.info("Successfully parsed CV via LLMCVParser.")
            except Exception as exc:
                logger.warning(f"LLM CV Parser failed or unconfigured ({str(exc)}). Falling back to HeuristicCVParser.")

        # Step 2: Fallback to Heuristic Parser if LLM parsing failed or was skipped
        if not parsed_schema:
            print("this is parsed by heuristic parser")
            parsed_schema = await self.heuristic_parser.parse_cv_text(raw_text)
            logger.info("Parsed CV via HeuristicCVParser fallback.")

        # Step 3: Sanitize all extracted fields
        return self._sanitize_structured_data(parsed_schema)

    def _sanitize_structured_data(self, data: StructuredCVSchema) -> StructuredCVSchema:
        if data.contact_info:
            data.contact_info.full_name = sanitize_text(data.contact_info.full_name or "") or None
            data.contact_info.email = sanitize_text(data.contact_info.email or "") or None
            data.contact_info.phone = sanitize_text(data.contact_info.phone or "") or None
            data.contact_info.location = sanitize_text(data.contact_info.location or "") or None
            data.contact_info.summary = sanitize_text(data.contact_info.summary or "") or None

        for item in data.work_history:
            item.company = sanitize_text(item.company or "")
            item.role = sanitize_text(item.role or "")
            item.location = sanitize_text(item.location or "") or None
            item.description = sanitize_text(item.description or "") or None

        for item in data.education:
            item.institution = sanitize_text(item.institution or "")
            item.degree = sanitize_text(item.degree or "") or None
            item.field_of_study = sanitize_text(item.field_of_study or "") or None

        data.skills = [sanitize_text(s) for s in data.skills if sanitize_text(s)]
        return data
