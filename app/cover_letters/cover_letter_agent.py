import re
from abc import ABC, abstractmethod
from typing import List, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core_schema.models import CV as CVModel, Project
    from app.tailoring.schemas import SkillMatchResult


def verify_grounded(letter_text: str, allowed_facts: Set[str]) -> List[str]:
    """
    Post-generation anti-hallucination check.

    Scans the letter for Capitalized words/phrases and verifies each is
    traceable to an entry in `allowed_facts` (the set of real entities drawn
    from the user's stored CV, skills, projects and the JD metadata).

    Returns a list of unverified tokens for the caller to surface to the user.
    This is a heuristic guardrail; an LLM-based checker can be dropped in
    behind the same interface later.
    """
    # Extract Capitalized words — these are likely named entities
    words = re.findall(r'\b[A-Z][a-z]{2,}\b', letter_text)

    # Common English sentence-starters that are not named entities
    ignore_set = {
        "The", "This", "That", "These", "Those", "There",
        "Dear", "Hiring", "Manager", "Team", "Sir", "Madam",
        "Sincerely", "Best", "Regards",
        "For", "With", "And", "But", "Not",
        "My", "Your", "Our", "Their", "Its",
        "Also", "Below", "Above", "Such",
        "Please", "Thank", "Yours",
        "Looking", "Forward", "Hope",
        "While", "When", "Where", "During",
        "Given", "Since", "Because",
        "Both", "Each", "More", "Most",
        "Which", "Who", "What",
    }

    allowed_lower = {fact.lower() for fact in allowed_facts}
    unverified = []

    for w in words:
        if w in ignore_set:
            continue
        # Case-insensitive substring check: the word must appear in at least
        # one allowed fact (e.g., "Python" matches fact "Python" or "Python3")
        if not any(w.lower() in fact for fact in allowed_lower):
            unverified.append(w)

    # Deduplicate while preserving first-occurrence order
    seen: Set[str] = set()
    result = []
    for item in unverified:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


class ICoverLetterAgent(ABC):
    """
    Interface for the Cover Letter Generation Agent.
    Decoupled from HTTP / persistence — accepts only domain objects.
    """
    @abstractmethod
    async def generate(
        self,
        job_title: str,
        company: str,
        cv: "CVModel",
        matched_skills: List["SkillMatchResult"],
        projects: List["Project"],
        tone: str,
        length: str
    ) -> str:
        pass


class HeuristicCoverLetterAgent(ICoverLetterAgent):
    """
    Heuristic (non-LLM) implementation.
    Composes a structured letter from real user data only — never invents facts.
    Replace with an LLMCoverLetterAgent behind the same interface later.
    """

    async def generate(
        self,
        job_title: str,
        company: str,
        cv: "CVModel",
        matched_skills: List["SkillMatchResult"],
        projects: List["Project"],
        tone: str,
        length: str
    ) -> str:
        company_display = company if company else "your company"

        if tone == "formal":
            greeting = f"Dear Hiring Manager at {company_display},"
            signoff = "Sincerely,"
        else:
            greeting = f"Hi {company_display} team,"
            signoff = "Best,"

        intro = f"I am writing to express my strong interest in the {job_title} position."

        matched_only = [m.jd_skill_name for m in matched_skills if m.match_status == "matched"]
        skills_str = ", ".join(matched_only)
        if skills_str:
            body1 = f"My background includes hands-on experience with {skills_str}."
        else:
            body1 = "My background aligns closely with the requirements outlined in the job description."

        body2 = ""
        if projects:
            proj = projects[0]
            body2 = (
                f"One relevant example is my work on {proj.title}, "
                f"where I applied these skills to deliver tangible results that translate directly to this role."
            )

        name = cv.full_name or "Applicant"
        company_experience = ""
        if cv.work_histories:
            latest = cv.work_histories[0]
            company_experience = (
                f"Most recently, I served as {latest.role} at {latest.company}, "
                f"which gave me direct experience relevant to this opportunity."
            )

        if length == "short":
            body = f"{intro} {body1} {body2}"
            letter = f"{greeting}\n\n{body}\n\n{signoff}\n{name}"
        else:
            paragraphs = [intro, body1]
            if company_experience:
                paragraphs.append(company_experience)
            if body2:
                paragraphs.append(body2)
            paragraphs.append("I look forward to the opportunity to discuss how my experience aligns with your team's goals.")
            letter = f"{greeting}\n\n" + "\n\n".join(paragraphs) + f"\n\n{signoff}\n{name}"

        return letter
