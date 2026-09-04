import pytest
from app.learning.triage_agent import HeuristicTriageAgent
from app.core_schema.models import Skill
import uuid


@pytest.fixture
def agent():
    return HeuristicTriageAgent()


@pytest.fixture
def existing_skills():
    # Helper to mock some existing skills
    def make_skill(name, slug):
        s = Skill()
        s.id = uuid.uuid4()
        s.name = name
        s.name_slug = slug
        return s
    return [
        make_skill("Python", "python"),
        make_skill("React", "react")
    ]


@pytest.mark.asyncio
async def test_classify_entry_not_skill_worthy(agent, existing_skills):
    text = "Today I read a blog post about FastAPI and watched a video on Docker."
    output = await agent.classify_entry(text, existing_skills)
    
    assert output.is_skill_worthy is False
    assert output.proposed_skills == []


@pytest.mark.asyncio
async def test_classify_entry_skill_worthy_create_new(agent, existing_skills):
    text = "I built a new microservice using FastAPI and Docker."
    output = await agent.classify_entry(text, existing_skills)
    
    assert output.is_skill_worthy is True
    assert len(output.proposed_skills) == 2
    
    skills = {ps.skill_name: ps for ps in output.proposed_skills}
    
    assert "FastAPI" in skills
    assert skills["FastAPI"].action == "create_new"
    assert skills["FastAPI"].matched_skill_id is None
    
    assert "Docker" in skills
    assert skills["Docker"].action == "create_new"
    assert skills["Docker"].matched_skill_id is None


@pytest.mark.asyncio
async def test_classify_entry_skill_worthy_reinforce_existing(agent, existing_skills):
    text = "I implemented a new feature in Python and React."
    output = await agent.classify_entry(text, existing_skills)
    
    assert output.is_skill_worthy is True
    assert len(output.proposed_skills) == 2
    
    skills = {ps.skill_name: ps for ps in output.proposed_skills}
    
    assert "Python" in skills
    assert skills["Python"].action == "reinforce_existing"
    assert skills["Python"].matched_skill_id is not None
    
    assert "React" in skills
    assert skills["React"].action == "reinforce_existing"
    assert skills["React"].matched_skill_id is not None
