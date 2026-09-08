"""
Unit tests for Cover Letter Generation Agent and Grounding Logic.
"""
import pytest
from unittest.mock import MagicMock

from app.cover_letters.cover_letter_agent import verify_grounded, HeuristicCoverLetterAgent
from app.tailoring.schemas import SkillMatchResult


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def make_mock_cv(full_name="Jane Doe", companies=None, roles=None, institutions=None):
    """Build a mock CV SQLAlchemy model for testing."""
    cv = MagicMock()
    cv.full_name = full_name
    cv.work_histories = []
    for company, role in zip(companies or [], roles or []):
        wh = MagicMock()
        wh.company = company
        wh.role = role
        cv.work_histories.append(wh)
    cv.education_entries = []
    for inst in (institutions or []):
        edu = MagicMock()
        edu.institution = inst
        edu.degree = "B.Sc"
        cv.education_entries.append(edu)
    return cv


def make_mock_project(title: str):
    proj = MagicMock()
    proj.title = title
    proj.description = "A real project"
    return proj


# ------------------------------------------------------------------ #
# verify_grounded tests
# ------------------------------------------------------------------ #

def test_verify_grounded_clean():
    """A letter containing only allowed facts should return no unverified claims."""
    letter = "I worked at Google using Python and FastAPI."
    allowed_facts = {"Google", "Python", "FastAPI", "worked"}
    unverified = verify_grounded(letter, allowed_facts)
    assert unverified == []


def test_verify_grounded_flags_hallucination():
    """A letter containing an entity not in allowed_facts should return it."""
    letter = "I worked at Google using Python and Docker."
    allowed_facts = {"Google", "Python", "FastAPI"}
    unverified = verify_grounded(letter, allowed_facts)
    # "Docker" is a Capitalized named entity not in allowed_facts
    assert "Docker" in unverified


def test_verify_grounded_ignores_common_words():
    """Common English sentence-starters should not be flagged."""
    letter = "Dear Hiring Manager, I am looking forward to discussing this opportunity. Sincerely, Jane"
    allowed_facts = {"Jane"}
    unverified = verify_grounded(letter, allowed_facts)
    # None of the common words (Dear, Hiring, Manager, Sincerely) should be flagged
    # Hiring and Manager are common, not in ignore set but also not named entities
    # The implementation checks against allowed facts; 'Hiring' and 'Manager' should be in ignore set
    assert "Dear" not in unverified
    assert "Sincerely" not in unverified


def test_verify_grounded_handles_empty_letter():
    unverified = verify_grounded("", {"Python"})
    assert unverified == []


def test_verify_grounded_deduplicates():
    """Same unverified claim repeated multiple times should only appear once."""
    letter = "I used Docker and Docker and Docker for deployment."
    allowed_facts = {"Python"}
    unverified = verify_grounded(letter, allowed_facts)
    assert unverified.count("Docker") == 1


# ------------------------------------------------------------------ #
# HeuristicCoverLetterAgent tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_agent_formal_short_tone():
    agent = HeuristicCoverLetterAgent()
    cv = make_mock_cv(full_name="Jane Doe", companies=["Acme Corp"], roles=["Developer"])
    matched = [
        SkillMatchResult(jd_skill_name="Python", jd_skill_slug="python", match_status="matched", is_required=True),
        SkillMatchResult(jd_skill_name="Docker", jd_skill_slug="docker", match_status="missing", is_required=True),
    ]
    projects = [make_mock_project("Auth Service")]

    result = await agent.generate(
        job_title="Backend Engineer",
        company="Acme Corp",
        cv=cv,
        matched_skills=matched,
        projects=projects,
        tone="formal",
        length="short"
    )

    assert "Dear Hiring Manager at Acme Corp" in result
    assert "Backend Engineer" in result
    assert "Python" in result
    # Missing skills must NOT appear
    assert "Docker" not in result
    assert "Auth Service" in result
    assert "Jane Doe" in result
    assert "Sincerely," in result


@pytest.mark.asyncio
async def test_agent_conversational_standard_tone():
    agent = HeuristicCoverLetterAgent()
    cv = make_mock_cv(full_name="Bob Smith")

    result = await agent.generate(
        job_title="Frontend Dev",
        company="TechCo",
        cv=cv,
        matched_skills=[],
        projects=[],
        tone="conversational",
        length="standard"
    )

    assert "Hi TechCo team," in result
    assert "Best," in result
    assert "Bob Smith" in result
    assert "look forward" in result


@pytest.mark.asyncio
async def test_agent_no_company_fallback():
    agent = HeuristicCoverLetterAgent()
    cv = make_mock_cv(full_name="Alice")

    result = await agent.generate(
        job_title="Engineer",
        company="",
        cv=cv,
        matched_skills=[],
        projects=[],
        tone="formal",
        length="short"
    )

    assert "your company" in result
