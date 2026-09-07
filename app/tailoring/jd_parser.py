"""
JD Parser — Job Description text-to-structured-data extraction.

Interface: IJDParser.parse(jd_text: str) -> StructuredJDSchema
Implementations:
  - HeuristicJDParser: deterministic keyword/regex-based, used for testing and fallback
  - LLMJDParser: stub for future LangChain/LangGraph integration

Pattern mirrors Module 2 (ICVParser) and Module 4 (ITriageAgent):
  - Decoupled from HTTP handling and persistence
  - Output validated against StructuredJDSchema before returning
  - On validation failure, callers mark the application as needs_manual_review
"""
import re
from abc import ABC, abstractmethod
from typing import List
from app.tailoring.schemas import StructuredJDSchema, StructuredJDRequirement


# Known tech skills to recognize in JD text (extendable via config/database later)
_KNOWN_SKILLS = [
    "Python", "FastAPI", "Django", "Flask", "JavaScript", "TypeScript", "Node.js",
    "React", "Next.js", "Vue", "Angular", "PostgreSQL", "MySQL", "MongoDB",
    "Redis", "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Git", "CI/CD",
    "REST API", "GraphQL", "SQL", "Linux", "Agile", "Scrum", "Java", "C++",
    "Go", "Rust", "HTML", "CSS", "Tailwind", "LangChain", "LangGraph",
    "Pydantic", "SQLAlchemy", "Alembic", "pytest", "Machine Learning",
    "Deep Learning", "TensorFlow", "PyTorch", "Scikit-learn",
]

_SENIORITY_PATTERNS = {
    "junior": r"\b(junior|entry.level|0[\-–]2 years?|1[\-–]2 years?)\b",
    "mid-level": r"\b(mid.level|intermediate|2[\-–]5 years?|3[\-–]5 years?)\b",
    "senior": r"\b(senior|sr\.?|5\+|7\+|lead|principal)\b",
    "staff": r"\b(staff|principal|distinguished|fellow)\b",
}


class IJDParser(ABC):
    """Interface for job description parsers."""

    @abstractmethod
    async def parse(self, jd_text: str) -> StructuredJDSchema:
        pass


class HeuristicJDParser(IJDParser):
    """
    Deterministic rule-based JD parser for testing and fallback.
    Uses keyword matching to extract skills and heuristic patterns for seniority.
    """

    async def parse(self, jd_text: str) -> StructuredJDSchema:
        lower_text = jd_text.lower()

        # Extract skills by matching against known tech keywords
        found_skills: List[StructuredJDRequirement] = []
        seen_slugs = set()
        for skill in _KNOWN_SKILLS:
            pattern = rf"\b{re.escape(skill)}\b"
            if re.search(pattern, jd_text, re.IGNORECASE):
                slug = skill.lower()
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    # Classify as nice-to-have if mentioned in "bonus"/"preferred"/"nice to have" context
                    is_required = not bool(re.search(
                        rf"(bonus|preferred|nice.to.have|plus|desirable)[^\n]{{0,80}}{re.escape(skill)}",
                        jd_text, re.IGNORECASE
                    ))
                    found_skills.append(StructuredJDRequirement(
                        skill_name=skill,
                        is_required=is_required,
                    ))

        # Detect seniority level
        seniority_level = None
        for level, pattern in _SENIORITY_PATTERNS.items():
            if re.search(pattern, lower_text, re.IGNORECASE):
                seniority_level = level
                break

        # Attach seniority to all requirements if detected
        if seniority_level:
            for req in found_skills:
                req.seniority = seniority_level

        # Extract key responsibilities — lines that start with common action verbs
        responsibilities = []
        action_verbs = r"^[\s\-•–*]*(design|build|develop|implement|maintain|lead|own|manage|collaborate|create|architect|optimize|ensure|write|review|deploy)"
        for line in jd_text.split("\n"):
            if re.match(action_verbs, line.strip(), re.IGNORECASE) and len(line.strip()) > 15:
                responsibilities.append(line.strip().lstrip("-•–*").strip())
            if len(responsibilities) >= 10:  # Cap at 10 to avoid noise
                break

        return StructuredJDSchema(
            required_skills=found_skills,
            key_responsibilities=responsibilities,
            seniority_level=seniority_level,
        )


class LLMJDParser(IJDParser):
    """
    Stub for LLM-powered JD parser (future LangChain/LangGraph integration).
    Validates output against StructuredJDSchema before returning.
    """

    async def parse(self, jd_text: str) -> StructuredJDSchema:
        # When integrated: call LLM, then validate:
        # return StructuredJDSchema.model_validate_json(llm_response_json)
        raise NotImplementedError("LLM JD parser client is currently unconfigured.")
