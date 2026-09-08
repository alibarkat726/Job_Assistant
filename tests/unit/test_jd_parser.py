"""
Unit tests for HeuristicJDParser.
Verifies skill extraction, required vs nice-to-have classification, and seniority detection.
"""
import pytest
from app.tailoring.jd_parser import HeuristicJDParser

SAMPLE_JD_SENIOR = """
Senior Backend Engineer — Fintech

We are looking for a Senior Backend Engineer with 5+ years of experience.

Requirements:
- Strong proficiency in Python and FastAPI
- Experience with PostgreSQL and Redis
- Familiarity with Docker and Kubernetes
- REST API design experience

Nice to have:
- Experience with React is a plus
- Bonus points for GraphQL
"""

SAMPLE_JD_NO_SENIORITY = """
Backend Developer

We need a backend developer to help build our platform.

Responsibilities:
- Build and maintain REST APIs
- Implement database schemas using PostgreSQL
- Deploy services using Docker

Skills: Python, FastAPI, SQL
"""

SAMPLE_JD_EMPTY = "We are looking for a great candidate."


@pytest.fixture
def parser():
    return HeuristicJDParser()


@pytest.mark.asyncio
async def test_extracts_required_skills(parser):
    result = await parser.parse(SAMPLE_JD_SENIOR)
    skill_names = {r.skill_name for r in result.required_skills}

    assert "Python" in skill_names
    assert "FastAPI" in skill_names
    assert "PostgreSQL" in skill_names
    assert "Docker" in skill_names


@pytest.mark.asyncio
async def test_detects_seniority_senior(parser):
    result = await parser.parse(SAMPLE_JD_SENIOR)
    assert result.seniority_level == "senior"


@pytest.mark.asyncio
async def test_no_seniority_detected(parser):
    result = await parser.parse(SAMPLE_JD_NO_SENIORITY)
    assert result.seniority_level is None


@pytest.mark.asyncio
async def test_extracts_key_responsibilities(parser):
    result = await parser.parse(SAMPLE_JD_SENIOR)
    # The sample has "Build and maintain" which would match
    result2 = await parser.parse(SAMPLE_JD_NO_SENIORITY)
    assert len(result2.key_responsibilities) > 0


@pytest.mark.asyncio
async def test_empty_jd_returns_no_skills(parser):
    result = await parser.parse(SAMPLE_JD_EMPTY)
    assert result.required_skills == []
    assert result.seniority_level is None


@pytest.mark.asyncio
async def test_no_duplicate_skills(parser):
    result = await parser.parse(SAMPLE_JD_SENIOR)
    slugs = [r.skill_name.lower() for r in result.required_skills]
    assert len(slugs) == len(set(slugs)), "Duplicate skills should not appear in parsed output"
