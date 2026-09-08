"""
Unit tests for HeuristicInterviewPrepAgent.
Verifies that generated questions cover required categories and are correctly
grounded in the specific matched skills and projects.
"""
import uuid
import pytest
from unittest.mock import MagicMock

from app.interview_prep.prep_agent import HeuristicInterviewPrepAgent
from app.tailoring.schemas import StructuredJDRequirement, SkillMatchResult


def make_jd_requirement(name: str, is_required: bool = True, seniority: str = None):
    return StructuredJDRequirement(skill_name=name, is_required=is_required, seniority=seniority)


def make_skill_match(name: str, status: str, is_required: bool = True):
    return SkillMatchResult(
        jd_skill_name=name,
        jd_skill_slug=name.lower(),
        match_status=status,
        is_required=is_required
    )


def make_project(title: str, skills: list[str]):
    p = MagicMock()
    p.id = uuid.uuid4()
    p.title = title
    
    ps_list = []
    for skill_name in skills:
        ps = MagicMock()
        ps.skill = MagicMock()
        ps.skill.name = skill_name
        ps_list.append(ps)
    
    p.project_skills = ps_list
    return p


@pytest.fixture
def agent():
    return HeuristicInterviewPrepAgent()


@pytest.mark.asyncio
async def test_agent_generates_technical_questions(agent):
    jd_reqs = [make_jd_requirement("Python")]
    matched_skills = [
        make_skill_match("Python", "matched"),
        make_skill_match("Kubernetes", "missing", is_required=True)
    ]
    projects = []

    result = await agent.generate(jd_reqs, matched_skills, projects)
    
    # Expect 2 technical questions (1 matched, 1 missing required), 1 behavioral question
    assert len(result.questions) == 3
    
    tech_questions = [q for q in result.questions if q.category == "technical"]
    assert len(tech_questions) == 2
    
    # Check grounding in rationale
    assert any("Python" in q.rationale for q in tech_questions)
    assert any("Kubernetes" in q.rationale for q in tech_questions)


@pytest.mark.asyncio
async def test_agent_generates_project_questions(agent):
    jd_reqs = []
    matched_skills = []
    projects = [make_project("ShopLedger", ["React", "Node"])]

    result = await agent.generate(jd_reqs, matched_skills, projects)
    
    proj_questions = [q for q in result.questions if q.category == "project"]
    assert len(proj_questions) == 1
    
    q = proj_questions[0]
    assert "ShopLedger" in q.question_text
    assert "ShopLedger" in q.rationale
    assert "React" in q.rationale


@pytest.mark.asyncio
async def test_agent_generates_behavioral_based_on_seniority(agent):
    jd_reqs = [make_jd_requirement("Python", seniority="senior")]
    matched_skills = []
    projects = []

    result = await agent.generate(jd_reqs, matched_skills, projects)
    
    behavioral_qs = [q for q in result.questions if q.category == "behavioral"]
    assert len(behavioral_qs) == 1
    
    q = behavioral_qs[0]
    # The heuristic generates a mentoring question for "senior"
    assert "mentor" in q.question_text.lower() or "lead" in q.question_text.lower()
    assert "senior role" in q.rationale.lower()
